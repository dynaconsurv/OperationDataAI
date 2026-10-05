"""PI Web API Client for OSIsoft PI AF Telemetry Ingestion.
Supports Basic and NTLM Authentication, SSL toggle, Batch streaming,
Interpolated and Recorded data extraction, WebID resolution, and Mock fallback.
"""

from __future__ import annotations

import datetime as dt
import pickle
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib3
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

try:
    from requests_ntlm import HttpNtlmAuth  # type: ignore
    HAS_NTLM = True
except ImportError:
    HAS_NTLM = False

from src.utils.logger import get_logger
from src.utils.mock_generator import generate_mock_telemetry

logger = get_logger("PIClient")


class PIWebApiClient:
    """Client for querying PI System via PI Web API."""

    def __init__(self, config: Dict[str, Any], sensors: List[Dict[str, Any]]) -> None:
        self.config = config
        self.sensors = sensors
        pi_cfg = config.get("pi_web_api", {})

        self.base_url = pi_cfg.get("url", "https://kul-pivision.pttep.com/piwebapi/").rstrip("/")
        self.af_db = pi_cfg.get("af_db", r"\\KUL-PIAF\GEG RPM\\").strip("\\")
        self.username = pi_cfg.get("username", "zaqeelahr")
        self.password = pi_cfg.get("password", "Welcome@1234567")
        self.auth_type = pi_cfg.get("auth_type", "basic").lower()
        self.verify_ssl = pi_cfg.get("verify_ssl", False)
        self.timeout = pi_cfg.get("timeout_seconds", 30)
        self.mock_mode = pi_cfg.get("mock_mode", True)
        self.query_mode = pi_cfg.get("query_mode", "interpolated")
        self.sample_interval = pi_cfg.get("sample_interval", "1h")
        self.batch_size = pi_cfg.get("batch_size", 25)

        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.session = self._create_session()
        self._webid_cache: Dict[str, str] = {}

    def _create_session(self) -> requests.Session:
        """Create and configure requests Session with authentication."""
        session = requests.Session()
        session.verify = self.verify_ssl

        if self.auth_type == "ntlm" and HAS_NTLM:
            session.auth = HttpNtlmAuth(self.username, self.password)
        else:
            session.auth = HTTPBasicAuth(self.username, self.password)

        session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "PIWebApiClient",
        })
        return session

    def resolve_attribute_webid(self, parent_path: str, attribute_name: str = "Parameter") -> Optional[str]:
        """Resolve PI AF Attribute WebId using PI Web API path syntax."""
        cache_key = f"{parent_path}|{attribute_name}"
        if cache_key in self._webid_cache:
            return self._webid_cache[cache_key]

        # Construct full AF path
        clean_af_db = self.af_db.strip("\\")
        clean_parent = parent_path.strip("\\")
        full_path = f"\\\\{clean_af_db}\\{clean_parent}|{attribute_name}"

        url = f"{self.base_url}/attributes"
        params = {"path": full_path}

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                web_id = data.get("WebId")
                if web_id:
                    self._webid_cache[cache_key] = web_id
                    return web_id
            logger.warning(f"Could not resolve WebID for {full_path}: Status {resp.status_code}")
        except Exception as e:
            logger.error(f"Error querying attribute path {full_path}: {e}")

        return None

    def fetch_stream_data_live(
        self,
        web_id: str,
        start_time_str: str,
        end_time_str: str,
        interval: str = "1h",
    ) -> List[Tuple[str, float]]:
        """Fetch interpolated stream data for a single WebID."""
        url = f"{self.base_url}/streams/{web_id}/{self.query_mode}"
        params: Dict[str, Any] = {
            "startTime": start_time_str,
            "endTime": end_time_str,
        }
        if self.query_mode == "interpolated":
            params["interval"] = interval

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                items = resp.json().get("Items", [])
                results = []
                for item in items:
                    val = item.get("Value")
                    ts = item.get("Timestamp")
                    if val is not None and not isinstance(val, dict):
                        try:
                            results.append((ts, float(val)))
                        except (ValueError, TypeError):
                            continue
                return results
            else:
                logger.error(f"Stream query failed for {web_id}: HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"Stream query error for {web_id}: {e}")

        return []

    def fetch_batch_data_live(
        self,
        tag_webid_map: Dict[str, str],
        start_time_str: str,
        end_time_str: str,
        interval: str = "1h",
        progress_callback: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, pd.Series]:
        """Fetch data using PI Web API Batch request for multiple WebIDs with progress feedback."""
        batch_url = f"{self.base_url}/batch"
        results: Dict[str, pd.Series] = {}

        tag_items = list(tag_webid_map.items())
        total_tags = len(tag_items)
        total_batches = (total_tags + self.batch_size - 1) // self.batch_size if self.batch_size > 0 else 1
        batch_idx = 0
        t_start = time.time()

        if progress_callback:
            progress_callback(
                0.0,
                f"Starting batch download for {total_tags} tags ({total_batches} batches)...",
                {
                    "batch": 0,
                    "total_batches": total_batches,
                    "tags_completed": 0,
                    "total_tags": total_tags,
                    "elapsed": 0.0,
                    "eta": None,
                    "points_collected": 0,
                },
            )

        for i in range(0, len(tag_items), self.batch_size):
            chunk = tag_items[i : i + self.batch_size]
            batch_idx += 1
            subrequests: Dict[str, Any] = {}

            for tag_path, web_id in chunk:
                if self.query_mode == "interpolated":
                    full_uri = f"{self.base_url}/streams/{web_id}/interpolated?startTime={start_time_str}&endTime={end_time_str}&interval={interval}"
                else:
                    full_uri = f"{self.base_url}/streams/{web_id}/recorded?startTime={start_time_str}&endTime={end_time_str}"

                subrequests[tag_path] = {
                    "Method": "GET",
                    "Resource": full_uri,
                }

            try:
                resp = self.session.post(batch_url, json=subrequests, timeout=self.timeout * 2)
                if resp.status_code in (200, 207):
                    batch_resp = resp.json()
                    for tag_path, tag_res in batch_resp.items():
                        status = tag_res.get("Status", 500)
                        if status == 200:
                            content = tag_res.get("Content", {})
                            items = content.get("Items", [])
                            ts_list, val_list = [], []
                            for item in items:
                                val = item.get("Value")
                                ts = item.get("Timestamp")
                                if val is not None and not isinstance(val, dict):
                                    try:
                                        ts_list.append(pd.to_datetime(ts))
                                        val_list.append(float(val))
                                    except (ValueError, TypeError):
                                        continue
                            if ts_list:
                                results[tag_path] = pd.Series(val_list, index=ts_list)
                        else:
                            logger.warning(f"Batch item failed for {tag_path}: Status {status}")
                else:
                    logger.error(f"Batch request failed: HTTP {resp.status_code}")
            except Exception as e:
                logger.error(f"Batch request exception: {e}")

            # Compute progress and ETA
            tags_done = min(total_tags, i + len(chunk))
            fraction = tags_done / total_tags if total_tags > 0 else 1.0
            elapsed = time.time() - t_start
            eta = (elapsed / fraction) - elapsed if fraction > 0 else 0.0

            first_tag_path = chunk[0][0]
            subsystem = first_tag_path.split("\\")[4] if len(first_tag_path.split("\\")) >= 5 else ""
            msg = f"Batch {batch_idx}/{total_batches} ({tags_done}/{total_tags} tags) - {subsystem}"
            total_points = sum(len(s) for s in results.values())

            if progress_callback:
                progress_callback(
                    fraction,
                    msg,
                    {
                        "batch": batch_idx,
                        "total_batches": total_batches,
                        "tags_completed": tags_done,
                        "total_tags": total_tags,
                        "elapsed": round(elapsed, 1),
                        "eta": round(eta, 1),
                        "points_collected": total_points,
                    },
                )

        return results

    def pull_data(
        self,
        mode: str = "test",  # 'test' (1-day) or 'full' (12-months)
        custom_start: Optional[dt.datetime] = None,
        custom_end: Optional[dt.datetime] = None,
        custom_interval: Optional[str] = None,
        save_pickle: bool = True,
        pickle_path: Optional[Path] = None,
        progress_callback: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
    ) -> pd.DataFrame:
        """Execute telemetry ingestion according to mode, time range, and sampling interval.

        When sampling by minute (e.g. '1m', '5m', '10m'), queries spanning more than 1 hour
        are automatically split into 1-hour slices between start and stop to avoid PI server timeouts
        and payload limits.
        """
        end_time = custom_end or dt.datetime.now().replace(minute=0, second=0, microsecond=0)

        if custom_start is not None:
            start_time = custom_start
        elif mode == "test":
            test_days = self.config.get("pi_web_api", {}).get("test_duration_days", 1)
            start_time = end_time - dt.timedelta(days=test_days)
        else:
            months = self.config.get("pi_web_api", {}).get("full_duration_months", 12)
            start_time = end_time - dt.timedelta(days=int(months * 30.5))

        effective_interval = custom_interval or self.sample_interval

        # Detect minute-level resolution (e.g. '1m', '5m', '10m', '30m', '1min')
        s_int = effective_interval.strip().lower()
        is_minute = (s_int.endswith("m") and not s_int.endswith("mo")) or "min" in s_int

        # Split into 1-hour slices between start and stop if minute-based and duration > 1 hour
        if is_minute and (end_time - start_time) > dt.timedelta(hours=1):
            slices = []
            curr = start_time
            while curr < end_time:
                next_hr = min(curr + dt.timedelta(hours=1), end_time)
                slices.append((curr, next_hr))
                curr = next_hr
        else:
            slices = [(start_time, end_time)]

        logger.info(
            f"Pulling data (mode={mode}, interval={effective_interval}, mock={self.mock_mode}, slices={len(slices)}) "
            f"from {start_time} to {end_time}..."
        )

        if self.mock_mode:
            logger.info("MOCK MODE ACTIVE: Generating simulated GT-2420A telemetry (no external network call).")
            if progress_callback:
                for step in range(1, 6):
                    time.sleep(0.06)
                    frac = step / 5.0
                    progress_callback(
                        frac,
                        f"Simulating telemetry generation ({int(frac * 100)}%)...",
                        {
                            "batch": step,
                            "total_batches": 5,
                            "tags_completed": int(frac * len(self.sensors)),
                            "total_tags": len(self.sensors),
                            "elapsed": round(step * 0.06, 2),
                            "eta": round((5 - step) * 0.06, 2),
                            "points_collected": 0,
                        },
                    )

            df = generate_mock_telemetry(
                sensors=self.sensors,
                start_time=start_time,
                end_time=end_time,
                freq=effective_interval,
            )
        else:
            logger.info(f"LIVE PI WEB API MODE: Connecting to {self.base_url}")
            # Map sensors to WebIds
            tag_webid_map: Dict[str, str] = {}
            for s in self.sensors:
                parent = s.get("parent", "")
                attr_name = s.get("attribute_name", "Parameter")
                path_key = s.get("full_af_path", parent)
                web_id = s.get("web_id") or self.resolve_attribute_webid(parent, attr_name)
                if web_id:
                    tag_webid_map[path_key] = web_id

            if not tag_webid_map:
                logger.error("No WebIDs could be resolved from PI AF. Aborting live pull.")
                return pd.DataFrame()

            total_slices = len(slices)
            all_series: Dict[str, List[pd.Series]] = {k: [] for k in tag_webid_map.keys()}
            total_points_accum = 0
            t_pull_start = time.time()

            for s_idx, (s_start, s_end) in enumerate(slices):
                s_start_str = s_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                s_end_str = s_end.strftime("%Y-%m-%dT%H:%M:%SZ")
                slice_label = f"{s_start.strftime('%H:%M')}-{s_end.strftime('%H:%M')}"

                def slice_cb(fraction: float, message: str, details: Optional[Dict[str, Any]] = None):
                    if progress_callback:
                        details = details or {}
                        overall_frac = (s_idx + fraction) / total_slices
                        elapsed = time.time() - t_pull_start
                        eta = (elapsed / overall_frac) - elapsed if overall_frac > 0 else 0.0
                        d_out = dict(details)
                        d_out["slice"] = s_idx + 1
                        d_out["total_slices"] = total_slices
                        d_out["elapsed"] = round(elapsed, 1)
                        d_out["eta"] = round(eta, 1)
                        d_out["points_collected"] = total_points_accum + details.get("points_collected", 0)

                        if total_slices > 1:
                            hdr = f"Hour {s_idx + 1}/{total_slices} ({slice_label})"
                            progress_callback(overall_frac, f"{hdr} | {message}", d_out)
                        else:
                            progress_callback(fraction, message, d_out)

                slice_batch = self.fetch_batch_data_live(
                    tag_webid_map=tag_webid_map,
                    start_time_str=s_start_str,
                    end_time_str=s_end_str,
                    interval=effective_interval,
                    progress_callback=slice_cb,
                )

                slice_pts = sum(len(ser) for ser in slice_batch.values())
                total_points_accum += slice_pts

                for tag_path, ser in slice_batch.items():
                    if tag_path in all_series and not ser.empty:
                        all_series[tag_path].append(ser)

            # Combine and deduplicate across slices
            combined_dict: Dict[str, pd.Series] = {}
            for tag_path, ser_list in all_series.items():
                if ser_list:
                    cat_s = pd.concat(ser_list)
                    cat_s = cat_s[~cat_s.index.duplicated(keep="first")].sort_index()
                    combined_dict[tag_path] = cat_s

            df = pd.DataFrame(combined_dict)
            df.index.name = "timestamp"

        if save_pickle and not df.empty:
            if pickle_path is None:
                storage_cfg = self.config.get("storage", {})
                p_file = storage_cfg.get("pickle_file", "data/historical_data.pkl")
                pickle_path = Path(p_file)
                if not pickle_path.is_absolute():
                    pickle_path = Path(__file__).resolve().parent.parent.parent / pickle_path

            pickle_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pickle_path, "wb") as f:
                pickle.dump(df, f)
            logger.info(f"Historical telemetry saved to pickle at: {pickle_path} (Shape: {df.shape})")

        return df

    @staticmethod
    def load_cached_data(pickle_path: Path) -> Optional[pd.DataFrame]:
        """Load previously serialized telemetry DataFrame from pickle."""
        if not pickle_path.exists():
            return None
        try:
            with open(pickle_path, "rb") as f:
                df = pickle.load(f)
            return df
        except Exception as e:
            logger.error(f"Failed to load cached pickle from {pickle_path}: {e}")
            return None
