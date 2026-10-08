"""PI Web API Client for OSIsoft PI AF Telemetry Ingestion.
Supports Basic and NTLM Authentication, SSL toggle, Batch streaming,
Interpolated and Recorded data extraction, WebID resolution, and Mock fallback.
"""

from __future__ import annotations

import datetime as dt
import json
import pickle
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
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
        self.batch_throttle_calls = int(pi_cfg.get("batch_throttle_calls", 5))
        self.batch_throttle_delay = float(pi_cfg.get("batch_throttle_delay_seconds", 5.0))
        self.batch_call_count = 0

        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.session = self._create_session()
        self._webid_cache: Dict[str, str] = {}
        self.last_batch_network_error: bool = False

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
        self.last_batch_network_error = False

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
                    self.last_batch_network_error = True
                    logger.error(f"Batch request failed: HTTP {resp.status_code}")
            except Exception as e:
                self.last_batch_network_error = True
                logger.error(f"Batch request exception: {e}")

            self.batch_call_count += 1

            # Compute progress and ETA
            tags_done = min(total_tags, i + len(chunk))
            fraction = tags_done / total_tags if total_tags > 0 else 1.0
            elapsed = time.time() - t_start
            eta = (elapsed / fraction) - elapsed if fraction > 0 else 0.0

            first_tag_path = chunk[0][0]
            subsystem = first_tag_path.split("\\")[4] if len(first_tag_path.split("\\")) >= 5 else ""
            msg = f"Batch {batch_idx}/{total_batches} ({tags_done}/{total_tags} tags) - {subsystem}"
            total_points = sum(len(s) for s in results.values())

            details_info = {
                "batch": batch_idx,
                "total_batches": total_batches,
                "tags_completed": tags_done,
                "total_tags": total_tags,
                "elapsed": round(elapsed, 1),
                "eta": round(eta, 1),
                "points_collected": total_points,
            }

            # Throttling delay every N batch calls to accommodate concurrent PI Web API & PI Vision users
            if self.batch_throttle_calls > 0 and self.batch_throttle_delay > 0 and (self.batch_call_count % self.batch_throttle_calls == 0):
                logger.info(
                    f"Throttling PI Web API: Pausing {self.batch_throttle_delay}s after batch call #{self.batch_call_count} "
                    "to accommodate concurrent PI Vision users."
                )
                if progress_callback:
                    progress_callback(
                        fraction,
                        f"{msg} | ⏸️ Pausing {self.batch_throttle_delay}s for PI Vision...",
                        details_info,
                    )
                time.sleep(self.batch_throttle_delay)
            elif progress_callback:
                progress_callback(
                    fraction,
                    msg,
                    details_info,
                )

        return results

    def pull_data(
        self,
        mode: str = "test",  # 'test' (1-day) or 'full' (12-months)
        custom_start: Optional[dt.datetime] = None,
        custom_end: Optional[dt.datetime] = None,
        custom_interval: Optional[str] = None,
        save_storage: bool = True,
        storage_path: Optional[Path] = None,
        save_pickle: Optional[bool] = None,
        pickle_path: Optional[Path] = None,
        resume: bool = True,
        checkpoint_interval: int = 10,
        progress_callback: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
    ) -> pd.DataFrame:
        """Execute telemetry ingestion according to mode, time range, and sampling interval.

        When sampling by minute (e.g. '1m', '5m', '10m'), queries spanning more than 1 hour
        are automatically split into 1-hour slices between start and stop to avoid PI server timeouts
        and payload limits.

        Supports checkpointing and resume: if resume=True, inspects existing parquet/pickle storage,
        skips already completed hourly slices, and continues from where it stopped. Saves checkpoints
        periodically and upon interruption.
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

        # Determine target file path for checkpoints & storage
        target_path = storage_path or pickle_path
        if target_path is None:
            storage_cfg = self.config.get("storage", {})
            pq_file = storage_cfg.get("parquet_file", "data/historical_data.parquet")
            target_path = Path(pq_file)
            if not target_path.is_absolute():
                target_path = Path(__file__).resolve().parent.parent.parent / target_path
        elif not isinstance(target_path, Path):
            target_path = Path(target_path)

        should_save = save_storage if save_pickle is None else (save_storage or save_pickle)

        ledger_path = target_path.parent / "completed_slices.json" if target_path else None
        completed_slice_keys: Set[str] = set()

        if resume and ledger_path and ledger_path.exists():
            try:
                with open(ledger_path, "r", encoding="utf-8") as f:
                    ledger_data = json.load(f)
                    if isinstance(ledger_data, list):
                        completed_slice_keys = set(ledger_data)
                    elif isinstance(ledger_data, dict):
                        completed_slice_keys = set(ledger_data.get("completed_slices", []))
                logger.info(f"Loaded {len(completed_slice_keys)} completed slices from ledger {ledger_path}")
            except Exception as e:
                logger.warning(f"Could not read completed slices ledger from {ledger_path}: {e}")
        elif not resume:
            completed_slice_keys = set()
            if ledger_path and ledger_path.exists() and should_save:
                try:
                    ledger_path.unlink()
                except Exception as e:
                    logger.warning(f"Could not remove old ledger {ledger_path}: {e}")

        def to_slice_key(dt_val) -> str:
            ts = pd.Timestamp(dt_val)
            if ts.tz is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            return ts.strftime("%Y-%m-%dT%H:%M:%SZ")

        def save_ledger():
            if should_save and ledger_path and completed_slice_keys:
                try:
                    ledger_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(ledger_path, "w", encoding="utf-8") as f:
                        json.dump({"completed_slices": sorted(list(completed_slice_keys))}, f, indent=2)
                except Exception as e:
                    logger.warning(f"Could not save completed slices ledger to {ledger_path}: {e}")

        # Check for existing checkpoint to resume
        existing_df: Optional[pd.DataFrame] = None
        if resume and target_path and target_path.exists():
            try:
                if str(target_path).lower().endswith(".parquet"):
                    existing_df = pd.read_parquet(target_path, engine="pyarrow")
                else:
                    with open(target_path, "rb") as f:
                        existing_df = pickle.load(f)
                if existing_df is not None and not existing_df.empty:
                    if not isinstance(existing_df.index, pd.DatetimeIndex):
                        existing_df.index = pd.to_datetime(existing_df.index)
                    existing_df = existing_df.sort_index()
                    logger.info(
                        f"Resume enabled: Loaded existing checkpoint from {target_path} "
                        f"({len(existing_df)} rows, {len(existing_df.columns)} sensors, "
                        f"from {existing_df.index.min()} to {existing_df.index.max()})"
                    )
            except Exception as e:
                logger.warning(f"Could not read existing checkpoint from {target_path}: {e}")
                existing_df = None

        logger.info(
            f"Pulling data (mode={mode}, interval={effective_interval}, mock={self.mock_mode}, "
            f"slices={len(slices)}, resume={resume}) from {start_time} to {end_time}..."
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

            if resume and existing_df is not None and not existing_df.empty:
                df = pd.concat([existing_df, df])
                df = df[~df.index.duplicated(keep="last")].sort_index()

            if should_save and not df.empty and target_path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if str(target_path).lower().endswith(".parquet"):
                    df.to_parquet(target_path, engine="pyarrow", compression="snappy", index=True)
                    logger.info(f"Simulated telemetry saved to Apache Parquet at: {target_path} (Shape: {df.shape})")
                else:
                    with open(target_path, "wb") as f:
                        pickle.dump(df, f)
                    logger.info(f"Simulated telemetry saved to pickle at: {target_path} (Shape: {df.shape})")

            return df

        else:
            logger.info(f"LIVE PI WEB API MODE: Connecting to {self.base_url}")
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

            # Inspect checkpoint and ledger to determine which slices to skip vs backfill
            skipped_slices = []
            remaining_slices = []

            if resume and ((existing_df is not None and not existing_df.empty) or completed_slice_keys):
                try:
                    # Pre-compute hourly point counts across existing dataset for fast O(1) lookup
                    hourly_counts = existing_df.iloc[:, 0].resample("1h").count() if (existing_df is not None and not existing_df.empty) else pd.Series(dtype=int)
                    for s_start, s_end in slices:
                        s_key = to_slice_key(s_start)
                        s_ts = pd.Timestamp(s_key)

                        pts = hourly_counts.get(s_ts, 0)
                        # Slice is skipped if already in parquet with data OR confirmed completed in ledger (e.g. plant outage)
                        if pts >= 30 or s_key in completed_slice_keys:
                            skipped_slices.append((s_start, s_end))
                            completed_slice_keys.add(s_key)
                        else:
                            remaining_slices.append((s_start, s_end))

                    if skipped_slices:
                        logger.info(
                            f"Checkpoint resume: Skipping {len(skipped_slices)} previously completed slices. "
                            f"{len(remaining_slices)} slices will be downloaded / backfilled."
                        )
                except Exception as e:
                    logger.warning(f"Error during gap-aware slice check: {e}. Falling back to default slicing.")
                    remaining_slices = list(slices)
            else:
                remaining_slices = list(slices)

            if not remaining_slices and existing_df is not None and not existing_df.empty:
                logger.info("All requested time slices are already present in existing parquet file / ledger. No network calls needed.")
                if progress_callback:
                    progress_callback(
                        1.0,
                        f"All {len(slices)} slices already completed. Loaded {len(existing_df)} rows.",
                        {"points_collected": int(existing_df.size), "total_slices": len(slices), "slice": len(slices)},
                    )
                return existing_df

            total_slices = len(slices)
            completed_slices = len(skipped_slices)

            all_series: Dict[str, List[pd.Series]] = {k: [] for k in tag_webid_map.keys()}
            total_points_accum = 0

            # Pre-seed series from existing checkpoint
            if resume and existing_df is not None and not existing_df.empty:
                total_points_accum = int(existing_df.size)
                for col in existing_df.columns:
                    s = existing_df[col].dropna()
                    if not s.empty:
                        if col in all_series:
                            all_series[col].append(s)
                        else:
                            all_series[col] = [s]

            t_pull_start = time.time()

            def save_checkpoint(is_final: bool = False) -> pd.DataFrame:
                save_ledger()
                combined_dict: Dict[str, pd.Series] = {}
                for tag_path, ser_list in all_series.items():
                    if ser_list:
                        cat_s = pd.concat(ser_list)
                        cat_s = cat_s[~cat_s.index.duplicated(keep="last")].sort_index()
                        combined_dict[tag_path] = cat_s

                if not combined_dict:
                    return existing_df if existing_df is not None else pd.DataFrame()

                chk_df = pd.DataFrame(combined_dict)
                chk_df.index.name = "timestamp"

                if should_save and target_path:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    if str(target_path).lower().endswith(".parquet"):
                        chk_df.to_parquet(target_path, engine="pyarrow", compression="snappy", index=True)
                    else:
                        with open(target_path, "wb") as f:
                            pickle.dump(chk_df, f)
                    action = "Final telemetry saved" if is_final else "Checkpoint saved"
                    logger.info(f"{action} ({chk_df.shape[0]} rows, {chk_df.shape[1]} sensors) to {target_path}")

                return chk_df

            df = pd.DataFrame()
            consecutive_network_failures = 0
            try:
                for s_idx, (s_start, s_end) in enumerate(remaining_slices):
                    current_slice_num = completed_slices + s_idx + 1
                    s_start_str = s_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                    s_end_str = s_end.strftime("%Y-%m-%dT%H:%M:%SZ")
                    slice_label = f"{s_start.strftime('%Y-%m-%d %H:%M')}-{s_end.strftime('%H:%M')}"

                    def slice_cb(fraction: float, message: str, details: Optional[Dict[str, Any]] = None):
                        if progress_callback:
                            details = details or {}
                            overall_frac = (completed_slices + s_idx + fraction) / total_slices
                            elapsed = time.time() - t_pull_start
                            done_in_session = (s_idx + fraction)
                            if done_in_session > 0:
                                rem_slices_count = total_slices - (completed_slices + s_idx + fraction)
                                eta = (elapsed / done_in_session) * rem_slices_count
                            else:
                                eta = 0.0

                            d_out = dict(details)
                            d_out["slice"] = current_slice_num
                            d_out["total_slices"] = total_slices
                            d_out["elapsed"] = round(elapsed, 1)
                            d_out["eta"] = round(eta, 1)
                            d_out["points_collected"] = total_points_accum + details.get("points_collected", 0)

                            if total_slices > 1:
                                hdr = f"Hour {current_slice_num}/{total_slices} ({slice_label})"
                                if completed_slices > 0:
                                    hdr += f" [Resumed from Hr {completed_slices}]"
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

                    # VPN / Network Disconnect Guard
                    if slice_pts == 0 and getattr(self, "last_batch_network_error", False):
                        consecutive_network_failures += 1
                        if consecutive_network_failures >= 3:
                            msg = "VPN / Network connection lost (3 consecutive batch failures). Ingestion paused and checkpoint saved."
                            logger.error(msg)
                            save_ledger()
                            if progress_callback:
                                overall_frac = (completed_slices + s_idx + 1.0) / total_slices
                                progress_callback(
                                    overall_frac,
                                    f"⚠️ {msg} Reconnect VPN and click Trigger Ingestion to resume.",
                                    {"vpn_error": True, "slice": current_slice_num, "total_slices": total_slices},
                                )
                            break
                    else:
                        consecutive_network_failures = 0
                        # Successful query (even if 0 points due to unit shutdown) -> mark slice as completed
                        completed_slice_keys.add(to_slice_key(s_start))

                    for tag_path, ser in slice_batch.items():
                        if tag_path in all_series and not ser.empty:
                            all_series[tag_path].append(ser)

                    # Periodic Checkpoint
                    if (s_idx + 1) % checkpoint_interval == 0:
                        save_checkpoint(is_final=False)

            finally:
                df = save_checkpoint(is_final=True)
                save_ledger()

            return df

    @staticmethod
    def load_cached_data(file_path: Path) -> Optional[pd.DataFrame]:
        """Load previously serialized telemetry DataFrame from Parquet (or fallback to Pickle)."""
        if not file_path.exists():
            return None
        try:
            if str(file_path).lower().endswith(".parquet"):
                return pd.read_parquet(file_path, engine="pyarrow")
            else:
                with open(file_path, "rb") as f:
                    return pickle.load(f)
        except Exception as e:
            logger.error(f"Failed to load cached telemetry from {file_path}: {e}")
            return None
