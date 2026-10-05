"""Module 1 Orchestration Pipeline.
Integrates PI Web API extraction, local pickle persistence, statistical operating limits
calculation (Normal, HH, H, L, LL), SQL table insertion with change-detection deduplication,
and run metadata tracking for dashboard reporting.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from src.config_manager import ConfigManager
from src.module1_pi_ingestion.limits_calculator import LimitsCalculator
from src.module1_pi_ingestion.pi_client import PIWebApiClient
from src.module1_pi_ingestion.sql_storage import SQLStorageManager
from src.utils.logger import get_logger

logger = get_logger("PipelineModule1")


class Module1Pipeline:
    """Orchestrator for the PI Telemetry Ingestion and Limits Calculation pipeline."""

    def __init__(self, config_manager: Optional[ConfigManager] = None) -> None:
        self.cm = config_manager or ConfigManager()
        self.config = self.cm.load_config()
        self.sensors = self.cm.load_sensors()

        self.pi_client = PIWebApiClient(self.config, self.sensors)
        self.calculator = LimitsCalculator(self.config)
        self.sql_storage = SQLStorageManager(self.config)

    def run(
        self,
        mode: str = "test",  # 'test' (1 day) or 'full' (12 months)
        force_mock: Optional[bool] = None,
        custom_start: Optional[dt.datetime] = None,
        custom_end: Optional[dt.datetime] = None,
    ) -> Dict[str, Any]:
        """Execute the full Module 1 pipeline.

        Parameters
        ----------
        mode : str
            'test' for 1-day ingestion, 'full' for 12-month ingestion.
        force_mock : bool, optional
            Override mock_mode setting if provided.
        custom_start : datetime, optional
            Custom start timestamp.
        custom_end : datetime, optional
            Custom end timestamp.

        Returns
        -------
        Dict[str, Any]
            Pipeline execution summary dictionary.
        """
        start_time_proc = time.time()
        logger.info(f"=== Starting Module 1 Pipeline (mode={mode}, mock={force_mock if force_mock is not None else self.pi_client.mock_mode}) ===")

        if force_mock is not None:
            self.pi_client.mock_mode = force_mock

        # Step 1: Ingest Telemetry
        pickle_rel = self.config.get("storage", {}).get("pickle_file", "data/historical_data.pkl")
        pickle_path = self.cm.resolve_path(pickle_rel)

        df = self.pi_client.pull_data(
            mode=mode,
            custom_start=custom_start,
            custom_end=custom_end,
            save_pickle=True,
            pickle_path=pickle_path,
        )

        if df.empty:
            error_msg = "No telemetry collected. Pipeline stopped."
            logger.error(error_msg)
            meta = {
                "last_pull_timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_seconds": round(time.time() - start_time_proc, 2),
                "pull_mode": mode,
                "time_range": "None",
                "tags_requested": len(self.sensors),
                "tags_successful": 0,
                "data_points_collected": 0,
                "limits_calculated": 0,
                "sql_inserted": 0,
                "sql_skipped": 0,
                "status": "Failed",
                "last_error": error_msg,
            }
            self.cm.save_last_run_meta(meta)
            return meta

        # Step 2: Compute Operating Limits
        records, summary_df = self.calculator.compute_all_limits(df)

        # Optional: Save summary to CSV
        limits_csv_rel = self.config.get("storage", {}).get("limits_csv_file", "data/operating_limits.csv")
        limits_csv_path = self.cm.resolve_path(limits_csv_rel)
        limits_csv_path.parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_csv(limits_csv_path, index=False)

        # Step 3: Insert into SQL with Deduplication
        inserted_count, skipped_count = self.sql_storage.save_limits(records)

        # Step 4: Record Execution Metadata
        duration = round(time.time() - start_time_proc, 2)
        start_str = df.index.min().strftime("%Y-%m-%d %H:%M") if hasattr(df.index, "min") else "Unknown"
        end_str = df.index.max().strftime("%Y-%m-%d %H:%M") if hasattr(df.index, "max") else "Unknown"
        time_range_desc = f"{start_str} to {end_str}"

        meta = {
            "last_pull_timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": duration,
            "pull_mode": "1-Day Test" if mode == "test" else "12-Month Historical",
            "is_mock": self.pi_client.mock_mode,
            "backend_db": self.sql_storage.active_backend,
            "time_range": time_range_desc,
            "tags_requested": len(self.sensors),
            "tags_successful": len(df.columns),
            "data_points_collected": int(df.size),
            "limits_calculated": len(records),
            "sql_inserted": inserted_count,
            "sql_skipped": skipped_count,
            "status": "Success",
            "last_error": None,
        }

        self.cm.save_last_run_meta(meta)
        logger.info(f"=== Module 1 Pipeline Completed in {duration}s! Inserted: {inserted_count}, Skipped: {skipped_count} ===")
        return meta
