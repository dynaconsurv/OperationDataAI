"""Module 1 Orchestration Pipeline for Portable Release.
Integrates PI Web API hourly telemetry extraction, statistical operating limits
calculation (Normal, HH, H, L, LL), SQL table insertion with change-detection deduplication,
and run metadata tracking.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import pandas as pd

from src.config_manager import ConfigManager
from src.module1_pi_ingestion.limits_calculator import LimitsCalculator
from src.module1_pi_ingestion.pi_client import PIWebApiClient
from src.module1_pi_ingestion.sql_storage import SQLStorageManager
from src.utils.logger import get_logger

logger = get_logger("PipelineModule1")


class Module1Pipeline:
    """Orchestrator for PI Telemetry Ingestion and Limits Calculation pipeline."""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        equipment_id: Optional[str] = None,
    ) -> None:
        self.cm = config_manager or ConfigManager()
        self.config = self.cm.load_config()

        # Target equipment
        self.target_equipment = equipment_id or self.config.get("target_equipment", "GT-2420A")
        self.sensors = self.cm.load_sensors(equipment_id=self.target_equipment)

        self.pi_client = PIWebApiClient(self.config, self.sensors)
        self.calculator = LimitsCalculator(self.config)
        self.sql_storage = SQLStorageManager(self.config)

    def run(
        self,
        mode: str = "6month",
        force_mock: Optional[bool] = None,
        custom_start: Optional[dt.datetime] = None,
        custom_end: Optional[dt.datetime] = None,
        custom_interval: Optional[str] = None,
        resume: bool = True,
        checkpoint_interval: int = 5,
        progress_callback: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Execute the full Module 1 pipeline.

        Parameters
        ----------
        mode : str
            '6month' (default), 'test' (1 day), or 'custom'.
        force_mock : bool, optional
            Override mock mode.
        custom_start : datetime, optional
            Start time.
        custom_end : datetime, optional
            End time.
        custom_interval : str, optional
            Sampling interval (default from config: '1h').
        resume : bool
            Resume from existing checkpoint if available.
        checkpoint_interval : int
            Slice interval for saving checkpoints.
        progress_callback : callable, optional
            Callback for UI / CLI progress updates.
        """
        start_time_proc = time.time()
        effective_interval = custom_interval or self.config.get("pi_web_api", {}).get("sample_interval", "1h")
        months = self.config.get("pi_web_api", {}).get("duration_months", 6)

        logger.info(
            f"=== Starting Module 1 Pipeline for '{self.target_equipment}' "
            f"(mode={mode}, interval={effective_interval}, duration_months={months}, "
            f"sensors={len(self.sensors)}, resume={resume}) ==="
        )

        if force_mock is not None:
            self.pi_client.mock_mode = force_mock

        # Step 1: Ingest Telemetry
        storage_cfg = self.config.get("storage", {})
        parquet_rel = storage_cfg.get("parquet_file", "data/historical_data_hourly.parquet")
        storage_path = self.cm.resolve_path(parquet_rel)

        def ingestion_cb(fraction: float, message: str, details: Optional[Dict[str, Any]] = None):
            if progress_callback:
                progress_callback(fraction * 0.80, f"[Ingest] {message}", details or {})

        df = self.pi_client.pull_data(
            mode=mode,
            custom_start=custom_start,
            custom_end=custom_end,
            custom_interval=effective_interval,
            save_storage=True,
            storage_path=storage_path,
            resume=resume,
            checkpoint_interval=checkpoint_interval,
            progress_callback=ingestion_cb,
        )

        if df.empty:
            error_msg = f"No telemetry collected for equipment '{self.target_equipment}'. Pipeline halted."
            logger.error(error_msg)
            if progress_callback:
                progress_callback(1.0, f"[Failed] {error_msg}", {"error": True})
            meta = {
                "last_pull_timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_seconds": round(time.time() - start_time_proc, 2),
                "target_equipment": self.target_equipment,
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

        # Step 2: Compute Operating Limits (80% - 90%)
        if progress_callback:
            progress_callback(0.85, f"[Limits] Computing operating limits for {len(df.columns)} sensors...", {"step": 2, "total_steps": 3})

        records, summary_df = self.calculator.compute_all_limits(df)

        # Export CSV Summary
        limits_csv_rel = storage_cfg.get("limits_csv_file", "data/operating_limits.csv")
        limits_csv_path = self.cm.resolve_path(limits_csv_rel)
        limits_csv_path.parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_csv(limits_csv_path, index=False)
        logger.info(f"Exported operating limits summary to {limits_csv_path}")

        # Step 3: Insert into SQL with Deduplication (90% - 100%)
        if progress_callback:
            progress_callback(0.92, f"[SQL Sync] Synchronizing {len(records)} limits into database...", {"step": 3, "total_steps": 3})

        tolerance = float(self.config.get("database", {}).get("deduplication_tolerance", 1e-4))
        inserted_count, skipped_count = self.sql_storage.save_limits(records, tolerance=tolerance)

        if progress_callback:
            progress_callback(1.0, f"[Done] Sync complete: {inserted_count} limits inserted, {skipped_count} skipped.", {"step": 3, "total_steps": 3})

        # Step 4: Record Execution Metadata
        duration = round(time.time() - start_time_proc, 2)
        start_str = df.index.min().strftime("%Y-%m-%d %H:%M") if hasattr(df.index, "min") else "Unknown"
        end_str = df.index.max().strftime("%Y-%m-%d %H:%M") if hasattr(df.index, "max") else "Unknown"
        time_range_desc = f"{start_str} to {end_str}"

        meta = {
            "last_pull_timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": duration,
            "target_equipment": self.target_equipment,
            "pull_mode": f"{months}-Month Hourly" if mode == "6month" else mode,
            "sample_interval": effective_interval,
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
        logger.info(
            f"=== Module 1 Pipeline Completed Successfully in {duration}s ===\n"
            f"Equipment: {self.target_equipment} | Data Points: {meta['data_points_collected']:,} | "
            f"Limits: {meta['limits_calculated']} | SQL Inserted: {inserted_count} | SQL Skipped: {skipped_count}"
        )
        return meta
