"""PI Web API Client for OSIsoft PI AF Telemetry Ingestion.
Supports Basic and NTLM Authentication, SSL toggle, Batch streaming,
Interpolated and Recorded data extraction, WebID resolution, and Mock fallback.
"""

from __future__ import annotations

import datetime as dt
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
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
    ) -> Dict[str, pd.Series]:
        """Fetch data using PI Web API Batch request for multiple WebIDs."""
        batch_url = f"{self.base_url}/batch"
        results: Dict[str, pd.Series] = {}

        tag_items = list(tag_webid_map.items())
        for i in range(0, len(tag_items), self.batch_size):
            chunk = tag_items[i : i + self.batch_size]
            subrequests: Dict[str, Any] = {}

            for tag_path, web_id in chunk:
                if self.query_mode == "interpolated":
                    rel_url = f"streams/{web_id}/interpolated?startTime={urllib.parse.quote(start_time_str)}&endTime={urllib.parse.quote(end_time_str)}&interval={interval}"
                else:
                    rel_url = f"streams/{web_id}/recorded?startTime={urllib.parse.quote(start_time_str)}&endTime={urllib.parse.quote(end_time_str)}"

                subrequests[tag_path] = {
                    "Method": "GET",
                    "Resource": rel_url,
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

        return results

    def pull_data(
        self,
        mode: str = "test",  # 'test' (1-day) or 'full' (12-months)
        custom_start: Optional[dt.datetime] = None,
        custom_end: Optional[dt.datetime] = None,
        save_pickle: bool = True,
        pickle_path: Optional[Path] = None,
    ) -> pd.DataFrame:
        """Execute telemetry ingestion according to mode and configuration.

        Parameters
        ----------
        mode : str
            'test' for 1-day ingestion, 'full' for 12-month ingestion.
        custom_start : datetime, optional
            Explicit start time.
        custom_end : datetime, optional
            Explicit end time.
        save_pickle : bool
            Whether to serialize resulting DataFrame to pickle.
        pickle_path : Path, optional
            Target pickle file path.

        Returns
        -------
        pd.DataFrame
            Indexed by timestamp, columns matching sensor paths.
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

        logger.info(
            f"Pulling data (mode={mode}, mock={self.mock_mode}) from {start_time} to {end_time}..."
        )

        if self.mock_mode:
            logger.info("MOCK MODE ACTIVE: Generating simulated GT-2420A telemetry (no external network call).")
            df = generate_mock_telemetry(
                sensors=self.sensors,
                start_time=start_time,
                end_time=end_time,
                freq=self.sample_interval,
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

            start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

            batch_data = self.fetch_batch_data_live(
                tag_webid_map=tag_webid_map,
                start_time_str=start_str,
                end_time_str=end_str,
                interval=self.sample_interval,
            )

            df = pd.DataFrame(batch_data)
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
