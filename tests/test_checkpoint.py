"""Unit and integration tests for telemetry checkpointing and resume functionality."""

import datetime as dt
from pathlib import Path
import pandas as pd
import numpy as np

from src.config_manager import ConfigManager
from src.module1_pi_ingestion.pi_client import PIWebApiClient
from src.module1_pi_ingestion.pipeline import Module1Pipeline


def test_resume_preserves_and_appends_checkpoint(tmp_path: Path):
    """Verify that an existing parquet checkpoint is detected and resumed seamlessly."""
    cfg_file = tmp_path / "config.json"
    sen_file = tmp_path / "sensors.json"
    meta_file = tmp_path / "last_run_meta.json"
    db_file = tmp_path / "test.db"
    parquet_file = tmp_path / "test_data.parquet"

    cm = ConfigManager(config_path=cfg_file, sensors_path=sen_file, meta_path=meta_file)
    cfg = cm.load_config()
    cfg["pi_web_api"]["mock_mode"] = True
    cfg["database"]["engine"] = "sqlite"
    cfg["database"]["sqlite_path"] = str(db_file)
    cfg["storage"]["parquet_file"] = str(parquet_file)
    cm.save_config(cfg)

    test_sensors = [
        {
            "parent": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure",
            "attribute_name": "Parameter",
            "full_af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure",
            "tag_name": "Ambient Inlet Pressure",
            "subsystem": "Air Filter System",
            "sim_range": [0.9, 1.1],
        }
    ]
    cm.save_sensors(test_sensors)

    # 1. Simulate initial partial run: 08:00 to 09:00 (1 hour = 61 minute points)
    t_start1 = dt.datetime(2026, 10, 5, 8, 0, 0)
    t_end1 = dt.datetime(2026, 10, 5, 9, 0, 0)

    pipeline = Module1Pipeline(config_manager=cm)
    res1 = pipeline.run(
        mode="test",
        force_mock=True,
        custom_start=t_start1,
        custom_end=t_end1,
        custom_interval="1m",
        resume=True,
    )

    assert res1["status"] == "Success"
    assert parquet_file.exists()

    df_part1 = pd.read_parquet(parquet_file)
    assert len(df_part1) == 61
    assert df_part1.index.min() == pd.Timestamp("2026-10-05 08:00:00")
    assert df_part1.index.max() == pd.Timestamp("2026-10-05 09:00:00")

    # 2. Simulate resuming to 11:00 (from 08:00 to 11:00 = total 3 hours = 181 minute points)
    t_end2 = dt.datetime(2026, 10, 5, 11, 0, 0)
    res2 = pipeline.run(
        mode="test",
        force_mock=True,
        custom_start=t_start1,
        custom_end=t_end2,
        custom_interval="1m",
        resume=True,
    )

    assert res2["status"] == "Success"
    df_part2 = pd.read_parquet(parquet_file)
    # The resumed dataset must now cover 08:00 to 11:00 (181 rows) without duplicates
    assert len(df_part2) == 181
    assert df_part2.index.min() == pd.Timestamp("2026-10-05 08:00:00")
    assert df_part2.index.max() == pd.Timestamp("2026-10-05 11:00:00")
    assert not df_part2.index.duplicated().any()


def test_no_resume_overwrites_existing(tmp_path: Path):
    """Verify that when resume=False, the pipeline writes fresh data without preserving earlier hours."""
    parquet_file = tmp_path / "fresh_test.parquet"

    # Pre-populate an old file with timestamps from yesterday
    old_idx = pd.date_range("2026-10-01 00:00", "2026-10-01 02:00", freq="1h")
    old_df = pd.DataFrame({"sensor_a": [1.0, 2.0, 3.0]}, index=old_idx)
    old_df.to_parquet(parquet_file)

    cfg = {
        "pi_web_api": {"mock_mode": True, "sample_interval": "1h"},
        "storage": {"parquet_file": str(parquet_file)},
    }
    client = PIWebApiClient(
        config=cfg,
        sensors=[{"full_af_path": "sensor_a", "sim_range": [10.0, 20.0]}],
    )

    # Pull fresh data with resume=False
    t_start = dt.datetime(2026, 10, 5, 10, 0, 0)
    t_end = dt.datetime(2026, 10, 5, 12, 0, 0)
    df_fresh = client.pull_data(
        custom_start=t_start,
        custom_end=t_end,
        custom_interval="1h",
        storage_path=parquet_file,
        resume=False,
    )

    assert len(df_fresh) == 3
    assert df_fresh.index.min() == pd.Timestamp("2026-10-05 10:00:00")
    # Verify the old 2026-10-01 rows are completely gone because resume was False
    assert (df_fresh.index.year == 2026).all()
    assert (df_fresh.index.day == 5).all()


def test_completed_slices_ledger_skips_outage_hours(tmp_path: Path):
    """Verify that slices returning 0 points (plant outages) are tracked in ledger and not re-queried on resume."""
    import json
    from unittest.mock import MagicMock

    parquet_file = tmp_path / "ledger_test.parquet"
    ledger_file = tmp_path / "completed_slices.json"

    cfg = {
        "pi_web_api": {"mock_mode": False, "sample_interval": "1m"},
        "storage": {"parquet_file": str(parquet_file)},
    }
    client = PIWebApiClient(
        config=cfg,
        sensors=[{"parent": "TestElem", "attribute_name": "TestAttr", "full_af_path": "Path/TestAttr", "web_id": "W123"}],
    )

    # Mock fetch_batch_data_live: Hour 1 has data, Hour 2 is outage (0 pts), Hour 3 has data
    calls = []

    def mock_fetch(tag_webid_map, start_time_str, end_time_str, interval, progress_callback=None):
        calls.append((start_time_str, end_time_str))
        if "09:00:00" in start_time_str:
            # Outage hour - returns 0 points
            return {"Path/TestAttr": pd.Series(dtype=float)}
        else:
            # Operating hour - returns data
            ts = pd.date_range(start_time_str, end_time_str, freq="1min")
            return {"Path/TestAttr": pd.Series(np.ones(len(ts)), index=ts)}

    client.fetch_batch_data_live = MagicMock(side_effect=mock_fetch)

    t_start = dt.datetime(2026, 10, 5, 8, 0, 0)
    t_end = dt.datetime(2026, 10, 5, 11, 0, 0)

    # 1. First run: processes hours 8-9, 9-10 (outage), 10-11
    df1 = client.pull_data(
        custom_start=t_start,
        custom_end=t_end,
        custom_interval="1m",
        storage_path=parquet_file,
        resume=True,
    )

    assert len(calls) == 3
    assert ledger_file.exists()

    with open(ledger_file, "r") as f:
        ledger = json.load(f)
    # All 3 hours must be marked complete in the ledger, including the 0-point outage hour
    assert len(ledger["completed_slices"]) == 3
    assert "2026-10-05T09:00:00Z" in ledger["completed_slices"]

    # 2. Second run with resume=True: all 3 slices should be skipped!
    calls.clear()
    df2 = client.pull_data(
        custom_start=t_start,
        custom_end=t_end,
        custom_interval="1m",
        storage_path=parquet_file,
        resume=True,
    )

    # No network calls made because all 3 slices (including outage) are acknowledged in ledger
    assert len(calls) == 0
    assert len(df2) == len(df1)

