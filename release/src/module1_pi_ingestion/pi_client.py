"""PI Web API Client for Module 1 Portable Release.
Handles hourly telemetry extraction, batch streaming, PI Vision friendly throttling,
outage-resilient ledger tracking, and checkpoint persistence.
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
    """Client for querying PI System via PI Web API with batching and outage-aware checkpointing."""

    def __init__(self, config: Dict[str, Any], sensors: List[Dict[str, Any]]) -> None:
        self.config = config
        self.sensors = sensors
        pi_cfg = config.get("pi_web_api", {})

        self.base_url = (pi_cfg.get("base_url") or pi_cfg.get("url") or "https://kul-pivision.pttep.com/piwebapi").rstrip("/")
        self.auth_type = pi_cfg.get("auth_type", "basic").lower()
        self.username = pi_cfg.get("user") or pi_cfg.get("username", "")
        self.password = pi_cfg.get("password", "")
        self.verify_ssl = pi_cfg.get("verify_ssl", False)
        self.timeout = int(pi_cfg.get("timeout_seconds", 30))
        self.mock_mode = bool(pi_cfg.get("mock_mode", False))
        self.query_mode = pi_cfg.get("query_mode", "interpolated")
        self.sample_interval = pi_cfg.get("sample_interval", "1h")
        self.batch_size = int(pi_cfg.get("batch_size", 25))

        # Throttling to protect PI Web API & PI Vision users
        self.batch_throttle_calls = int(pi_cfg.get("batch_throttle_calls", 5))
        self.batch_throttle_delay = float(pi_cfg.get("batch_throttle_delay_seconds", 5.0))
        self.batch_counter = 0

        self.last_batch_network_error = False

        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.session = self._init_session()

    def _init_session(self) -> requests.Session:
        """Initialize authenticated requests session."""
        session = requests.Session()
        session.verify = self.verify_ssl

        if self.auth_type == "basic":
            session.auth = HTTPBasicAuth(self.username, self.password)
        elif self.auth_type == "ntlm":
            if not HAS_NTLM:
                logger.warning("requests_ntlm is not installed; falling back to Basic auth.")
                session.auth = HTTPBasicAuth(self.username, self.password)
            else:
                session.auth = HttpNtlmAuth(self.username, self.password)

        session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Requested-With": "PIWebApiClient",
        })
        return session

    def resolve_attribute_webid(self, parent_path: str, attribute_name: str = "Parameter") -> Optional[str]:
        """Query PI AF to find WebID for a given Element and Attribute path."""
        if self.mock_mode:
            return f"mock-webid-{abs(hash(parent_path + attribute_name))}"

        elem_clean = parent_path.strip().strip("\\")
        encoded_path = urllib.parse.quote(f"\\\\{elem_clean}|{attribute_name}", safe="")
        endpoint = f"{self.base_url}/attributes?path={encoded_path}"

        try:
            resp = self.session.get(endpoint, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("WebId")
        except Exception as e:
            logger.debug(f"Failed to resolve WebID for \\\\{elem_clean}|{attribute_name}: {e}")
        return None

    def fetch_batch_data_live(
        self,
        tag_webid_map: Dict[str, str],
        start_time_str: str = "*-6mo",
        end_time_str: str = "*",
        interval: str = "1h",
        progress_callback: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, pd.Series]:
        """Extract telemetry data for multiple sensors using the PI Web API Batch endpoint."""
        if not tag_webid_map:
            return {}

        self.last_batch_network_error = False
        batch_endpoint = f"{self.base_url}/batch"
        all_results: Dict[str, pd.Series] = {k: pd.Series(dtype=float) for k in tag_webid_map.keys()}

        tags_list = list(tag_webid_map.items())
        total_tags = len(tags_list)
        total_batches = (total_tags + self.batch_size - 1) // self.batch_size

        logger.info(
            f"Executing live PI Web API batch query ({total_tags} sensors in {total_batches} sub-batches) "
            f"from {start_time_str} to {end_time_str} at interval={interval}"
        )

        t0 = time.time()
        for b_idx in range(total_batches):
            chunk = tags_list[b_idx * self.batch_size : (b_idx + 1) * self.batch_size]
            batch_payload: Dict[str, Dict[str, Any]] = {}

            for tag_idx, (path_key, web_id) in enumerate(chunk):
                sub_req_id = str(tag_idx + 1)
                enc_start = urllib.parse.quote(start_time_str, safe="")
                enc_end = urllib.parse.quote(end_time_str, safe="")

                if self.query_mode == "interpolated":
                    enc_int = urllib.parse.quote(interval, safe="")
                    rel_url = f"/streams/{web_id}/interpolated?startTime={enc_start}&endTime={enc_end}&interval={enc_int}"
                else:
                    rel_url = f"/streams/{web_id}/recorded?startTime={enc_start}&endTime={enc_end}"

                batch_payload[sub_req_id] = {
                    "Method": "GET",
                    "Resource": f"{self.base_url}{rel_url}",
                }

            # Batch Execution
            try:
                resp = self.session.post(batch_endpoint, json=batch_payload, timeout=self.timeout)
                if resp.status_code in (200, 207):
                    resp_json = resp.json()
                    for tag_idx, (path_key, _) in enumerate(chunk):
                        sub_req_id = str(tag_idx + 1)
                        tag_resp = resp_json.get(sub_req_id, {})
                        if tag_resp.get("Status") == 200:
                            body = tag_resp.get("Content", {})
                            items = body.get("Items", [])
                            if items:
                                parsed = []
                                for item in items:
                                    if item.get("Good", True):
                                        val = item.get("Value")
                                        ts_str = item.get("Timestamp")
                                        if val is not None and not isinstance(val, dict):
                                            try:
                                                parsed.append((pd.to_datetime(ts_str), float(val)))
                                            except (ValueError, TypeError):
                                                pass
                                if parsed:
                                    s = pd.Series(dict(parsed)).sort_index()
                                    s = s[~s.index.duplicated(keep="last")]
                                    all_results[path_key] = s
                else:
                    logger.warning(f"Batch request returned status {resp.status_code}: {resp.text[:200]}")
                    self.last_batch_network_error = True

            except Exception as e:
                logger.error(f"Batch request exception: {e}")
                self.last_batch_network_error = True

            # Throttling Delay
            self.batch_counter += 1
            if self.batch_throttle_calls > 0 and self.batch_counter % self.batch_throttle_calls == 0:
                logger.debug(f"Throttling: paused {self.batch_throttle_delay}s after {self.batch_counter} batches")
                time.sleep(self.batch_throttle_delay)

            # Progress Callback
            if progress_callback:
                frac = (b_idx + 1) / total_batches
                elapsed = time.time() - t0
                rem_batches = total_batches - (b_idx + 1)
                eta = (elapsed / (b_idx + 1)) * rem_batches if b_idx > 0 else 0.0
                pts = sum(len(s) for s in all_results.values())
                progress_callback(
                    frac,
                    f"Batch {b_idx + 1}/{total_batches} ({min((b_idx + 1)*self.batch_size, total_tags)}/{total_tags} tags)",
                    {
                        "batch": b_idx + 1,
                        "total_batches": total_batches,
                        "tags_completed": min((b_idx + 1)*self.batch_size, total_tags),
                        "total_tags": total_tags,
                        "elapsed": round(elapsed, 1),
                        "eta": round(eta, 1),
                        "points_collected": pts,
                    },
                )

        return all_results

    def pull_data(
        self,
        mode: str = "6month",
        custom_start: Optional[dt.datetime] = None,
        custom_end: Optional[dt.datetime] = None,
        custom_interval: Optional[str] = None,
        save_storage: bool = True,
        storage_path: Optional[Path] = None,
        resume: bool = True,
        checkpoint_interval: int = 5,
        progress_callback: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
    ) -> pd.DataFrame:
        """Extract historical telemetry from PI Web API with outage-aware slicing and checkpointing.

        Parameters
        ----------
        mode : str
            '6month' (default: 6 months), 'test' (1 day), or 'custom'.
        custom_start : datetime, optional
            Explicit start time.
        custom_end : datetime, optional
            Explicit stop time.
        custom_interval : str, optional
            Sampling interval ('1h', '1m', etc.).
        save_storage : bool
            Whether to serialize checkpoint to Parquet.
        storage_path : Path, optional
            Destination Parquet path.
        resume : bool
            Resume from existing checkpoint and skip verified outage/completed slices.
        checkpoint_interval : int
            Interval of slices between saving checkpoints.
        """
        end_time = custom_end or dt.datetime.now().replace(minute=0, second=0, microsecond=0)

        if custom_start is not None:
            start_time = custom_start
        elif mode == "test":
            test_days = self.config.get("pi_web_api", {}).get("test_duration_days", 1)
            start_time = end_time - dt.timedelta(days=test_days)
        else:
            months = self.config.get("pi_web_api", {}).get("duration_months") or self.config.get("pi_web_api", {}).get("full_duration_months", 6)
            start_time = end_time - dt.timedelta(days=int(months * 30.5))

        effective_interval = custom_interval or self.sample_interval

        # Determine slicing strategy
        s_int = effective_interval.strip().lower()
        is_minute = (s_int.endswith("m") and not s_int.endswith("mo")) or "min" in s_int
        slice_days = self.config.get("pi_web_api", {}).get("slice_days", 30)

        if is_minute and (end_time - start_time) > dt.timedelta(hours=1):
            slices = []
            curr = start_time
            while curr < end_time:
                nxt = min(curr + dt.timedelta(hours=1), end_time)
                slices.append((curr, nxt))
                curr = nxt
        elif slice_days and slice_days > 0 and (end_time - start_time) > dt.timedelta(days=slice_days):
            slices = []
            curr = start_time
            while curr < end_time:
                nxt = min(curr + dt.timedelta(days=slice_days), end_time)
                slices.append((curr, nxt))
                curr = nxt
        else:
            slices = [(start_time, end_time)]

        # Target file path
        target_path = storage_path
        if target_path is None:
            storage_cfg = self.config.get("storage", {})
            pq_file = storage_cfg.get("parquet_file", "data/historical_data_hourly.parquet")
            target_path = Path(pq_file)
            if not target_path.is_absolute():
                base_dir = Path(__file__).resolve().parent.parent.parent
                target_path = base_dir / target_path
        elif not isinstance(target_path, Path):
            target_path = Path(target_path)

        ledger_path = target_path.parent / "completed_slices.json" if target_path else None
        completed_slice_keys: Set[str] = set()

        if resume and ledger_path and ledger_path.exists():
            try:
                with open(ledger_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        completed_slice_keys = set(data)
                    elif isinstance(data, dict):
                        completed_slice_keys = set(data.get("completed_slices", []))
                logger.info(f"Loaded {len(completed_slice_keys)} verified completed slices from ledger {ledger_path}")
            except Exception as e:
                logger.warning(f"Could not read ledger from {ledger_path}: {e}")
        elif not resume:
            completed_slice_keys = set()
            if ledger_path and ledger_path.exists() and save_storage:
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
            if save_storage and ledger_path and completed_slice_keys:
                try:
                    ledger_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(ledger_path, "w", encoding="utf-8") as f:
                        json.dump({"completed_slices": sorted(list(completed_slice_keys))}, f, indent=2)
                except Exception as e:
                    logger.warning(f"Could not save ledger to {ledger_path}: {e}")

        # Check existing checkpoint
        existing_df: Optional[pd.DataFrame] = None
        if resume and target_path and target_path.exists():
            try:
                existing_df = pd.read_parquet(target_path, engine="pyarrow")
                if existing_df is not None and not existing_df.empty:
                    if not isinstance(existing_df.index, pd.DatetimeIndex):
                        existing_df.index = pd.to_datetime(existing_df.index)
                    existing_df = existing_df.sort_index()
                    logger.info(
                        f"Resume enabled: Loaded existing checkpoint from {target_path} "
                        f"({len(existing_df)} rows from {existing_df.index.min()} to {existing_df.index.max()})"
                    )
            except Exception as e:
                logger.warning(f"Could not read existing checkpoint from {target_path}: {e}")
                existing_df = None

        logger.info(
            f"Pulling telemetry (mode={mode}, interval={effective_interval}, mock={self.mock_mode}, "
            f"slices={len(slices)}, resume={resume}) from {start_time} to {end_time}..."
        )

        if self.mock_mode:
            logger.info("MOCK MODE ACTIVE: Generating synthetic operational telemetry.")
            if progress_callback:
                for step in range(1, 6):
                    time.sleep(0.05)
                    frac = step / 5.0
                    progress_callback(frac, f"Simulating telemetry generation ({int(frac * 100)}%)...", {"batch": step, "total_batches": 5})

            df = generate_mock_telemetry(
                sensors=self.sensors,
                start_time=start_time,
                end_time=end_time,
                freq=effective_interval,
            )

            if resume and existing_df is not None and not existing_df.empty:
                df = pd.concat([existing_df, df])
                df = df[~df.index.duplicated(keep="last")].sort_index()

            if save_storage and not df.empty and target_path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                df.to_parquet(target_path, engine="pyarrow", compression="snappy", index=True)
                logger.info(f"Simulated telemetry saved to {target_path} (Shape: {df.shape})")

            return df

        # LIVE PI WEB API MODE
        tag_webid_map: Dict[str, str] = {}
        for s in self.sensors:
            parent = s.get("parent", "")
            attr_name = s.get("attribute_name", "Parameter")
            path_key = s.get("full_af_path", parent)
            web_id = s.get("web_id") or self.resolve_attribute_webid(parent, attr_name)
            if web_id:
                tag_webid_map[path_key] = web_id

        if not tag_webid_map:
            logger.error("No WebIDs resolved from PI AF. Aborting live pull.")
            return pd.DataFrame()

        # Check slices to skip vs backfill
        skipped_slices = []
        remaining_slices = []

        if resume and ((existing_df is not None and not existing_df.empty) or completed_slice_keys):
            try:
                for s_start, s_end in slices:
                    s_key = to_slice_key(s_start)
                    # Check if already present in parquet or ledger
                    if s_key in completed_slice_keys:
                        skipped_slices.append((s_start, s_end))
                    elif existing_df is not None and not existing_df.empty:
                        s_ts = pd.Timestamp(s_key)
                        if (existing_df.index >= s_ts) & (existing_df.index < pd.Timestamp(to_slice_key(s_end))).any():
                            skipped_slices.append((s_start, s_end))
                            completed_slice_keys.add(s_key)
                        else:
                            remaining_slices.append((s_start, s_end))
                    else:
                        remaining_slices.append((s_start, s_end))

                if skipped_slices:
                    logger.info(f"Checkpoint resume: Skipping {len(skipped_slices)} previously completed slices. {len(remaining_slices)} slices to download.")
            except Exception as e:
                logger.warning(f"Error during slice check: {e}. Falling back to default slicing.")
                remaining_slices = list(slices)
        else:
            remaining_slices = list(slices)

        if not remaining_slices and existing_df is not None and not existing_df.empty:
            logger.info("All requested time slices are already present in existing parquet file / ledger. No network calls needed.")
            if progress_callback:
                progress_callback(1.0, f"All {len(slices)} slices already completed. Loaded {len(existing_df)} rows.", {"total_slices": len(slices)})
            return existing_df

        total_slices = len(slices)
        completed_slices = len(skipped_slices)

        all_series: Dict[str, List[pd.Series]] = {k: [] for k in tag_webid_map.keys()}
        total_points_accum = 0

        if resume and existing_df is not None and not existing_df.empty:
            total_points_accum = int(existing_df.size)
            for col in existing_df.columns:
                s = existing_df[col].dropna()
                if not s.empty:
                    all_series.setdefault(col, []).append(s)

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

            if save_storage and target_path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                chk_df.to_parquet(target_path, engine="pyarrow", compression="snappy", index=True)
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
                slice_label = f"{s_start.strftime('%Y-%m-%d %H:%M')}-{s_end.strftime('%Y-%m-%d %H:%M')}"

                def slice_cb(fraction: float, message: str, details: Optional[Dict[str, Any]] = None):
                    if progress_callback:
                        details = details or {}
                        overall_frac = (completed_slices + s_idx + fraction) / total_slices
                        elapsed = time.time() - t_pull_start
                        done_in_session = (s_idx + fraction)
                        eta = (elapsed / done_in_session) * (total_slices - (completed_slices + s_idx + fraction)) if done_in_session > 0 else 0.0

                        d_out = dict(details)
                        d_out["slice"] = current_slice_num
                        d_out["total_slices"] = total_slices
                        d_out["elapsed"] = round(elapsed, 1)
                        d_out["eta"] = round(eta, 1)
                        d_out["points_collected"] = total_points_accum + details.get("points_collected", 0)

                        hdr = f"Slice {current_slice_num}/{total_slices} ({slice_label})"
                        progress_callback(overall_frac, f"{hdr} | {message}", d_out)

                slice_batch = self.fetch_batch_data_live(
                    tag_webid_map=tag_webid_map,
                    start_time_str=s_start_str,
                    end_time_str=s_end_str,
                    interval=effective_interval,
                    progress_callback=slice_cb,
                )

                slice_pts = sum(len(ser) for ser in slice_batch.values())
                total_points_accum += slice_pts

                if slice_pts == 0 and getattr(self, "last_batch_network_error", False):
                    consecutive_network_failures += 1
                    if consecutive_network_failures >= 3:
                        msg = "VPN / Network connection lost (3 consecutive failures). Ingestion paused."
                        logger.error(msg)
                        save_ledger()
                        break
                else:
                    consecutive_network_failures = 0
                    completed_slice_keys.add(to_slice_key(s_start))

                for tag_path, ser in slice_batch.items():
                    if tag_path in all_series and not ser.empty:
                        all_series[tag_path].append(ser)

                if (s_idx + 1) % checkpoint_interval == 0:
                    save_checkpoint(is_final=False)

        finally:
            df = save_checkpoint(is_final=True)
            save_ledger()

        return df
