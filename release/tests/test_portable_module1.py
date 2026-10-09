"""Automated tests for the Portable Module 1 Release.
Verifies equipment-grouped sensor catalog loading, 6-month hourly ingestion,
operating limits calculation, and SQL change-detection deduplication with current timestamping.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import pandas as pd
import pytest

from src.config_manager import ConfigManager
from src.module1_pi_ingestion.limits_calculator import LimitsCalculator
from src.module1_pi_ingestion.pipeline import Module1Pipeline
from src.module1_pi_ingestion.sql_storage import SQLStorageManager


def test_grouped_sensor_loading():
    """Verify that sensors.json grouped by equipment number loads properly for GT-2420A."""
    cm = ConfigManager()
    sensors = cm.load_sensors(equipment_id="GT-2420A")

    assert len(sensors) == 162
    for s in sensors:
        assert s.get("equipment_id") == "GT-2420A"
        assert "MALAYSIA\\BORF\\GTG\\GT-2420A" in s.get("parent", "")


def test_deduplication_and_current_timestamp(tmp_path: Path):
    """Verify that SQL storage deduplication matches (af_path, type) and skips unchanged records while updating timestamp."""
    db_file = tmp_path / "test_limits.db"
    cfg = {
        "database": {
            "engine": "sqlite",
            "sqlite_path": str(db_file),
            "use_sqlite_fallback": True,
            "deduplication_tolerance": 0.001,
        }
    }

    storage = SQLStorageManager(config=cfg)

    records = [
        {"af_path": "MALAYSIA\\GT-2420A\\Tag1", "type": "Normal", "value": 50.0},
        {"af_path": "MALAYSIA\\GT-2420A\\Tag1", "type": "HH", "value": 90.0},
        {"af_path": "MALAYSIA\\GT-2420A\\Tag1", "type": "H", "value": 75.0},
        {"af_path": "MALAYSIA\\GT-2420A\\Tag1", "type": "L", "value": 25.0},
        {"af_path": "MALAYSIA\\GT-2420A\\Tag1", "type": "LL", "value": 10.0},
    ]

    # 1. Initial insert: All 5 records should be inserted
    inserted, skipped = storage.save_limits(records)
    assert inserted == 5
    assert skipped == 0

    # Verify latest map
    latest = storage.get_latest_limits_map()
    assert len(latest) == 5
    assert latest[("MALAYSIA\\GT-2420A\\Tag1", "Normal")] == 50.0
    assert latest[("MALAYSIA\\GT-2420A\\Tag1", "HH")] == 90.0

    # 2. Second insert with identical values: All 5 should be skipped!
    inserted2, skipped2 = storage.save_limits(records)
    assert inserted2 == 0
    assert skipped2 == 5

    # 3. Third insert with 1 updated value (HH changed from 90.0 to 95.0)
    records_mod = list(records)
    records_mod[1] = {"af_path": "MALAYSIA\\GT-2420A\\Tag1", "type": "HH", "value": 95.0}

    inserted3, skipped3 = storage.save_limits(records_mod)
    assert inserted3 == 1  # Only the modified HH record is inserted
    assert skipped3 == 4   # The other 4 unchanged records are skipped

    latest_updated = storage.get_latest_limits_map()
    assert latest_updated[("MALAYSIA\\GT-2420A\\Tag1", "HH")] == 95.0


def test_portable_pipeline_mock_run(tmp_path: Path):
    """Verify that the full portable pipeline runs end-to-end in mock mode."""
    cfg_file = tmp_path / "config.json"
    sen_file = tmp_path / "sensors.json"
    meta_file = tmp_path / "meta.json"
    db_file = tmp_path / "portable.db"
    pq_file = tmp_path / "telemetry.parquet"
    csv_file = tmp_path / "limits.csv"

    import json
    cfg = {
        "target_equipment": "GT-2420A",
        "pi_web_api": {
            "mock_mode": True,
            "sample_interval": "1h",
            "duration_months": 6,
        },
        "database": {
            "engine": "sqlite",
            "sqlite_path": str(db_file),
            "use_sqlite_fallback": True,
            "deduplication_tolerance": 0.001,
        },
        "operating_limits": {
            "method": "percentile",
            "normal_stat": "median",
        },
        "storage": {
            "parquet_file": str(pq_file),
            "limits_csv_file": str(csv_file),
        },
    }
    with open(cfg_file, "w") as f:
        json.dump(cfg, f)

    test_sensors = {
        "GT-2420A": [
            {
                "id": 1,
                "equipment_id": "GT-2420A",
                "parent": "MALAYSIA\\BORF\\GTG\\GT-2420A\\System\\SensorA",
                "attribute_name": "Parameter",
                "full_af_path": "MALAYSIA\\BORF\\GTG\\GT-2420A\\System\\SensorA",
                "sim_range": [10.0, 50.0],
                "category": "Pressure",
            },
            {
                "id": 2,
                "equipment_id": "GT-2420A",
                "parent": "MALAYSIA\\BORF\\GTG\\GT-2420A\\System\\SensorB",
                "attribute_name": "Parameter",
                "full_af_path": "MALAYSIA\\BORF\\GTG\\GT-2420A\\System\\SensorB",
                "sim_range": [50.0, 150.0],
                "category": "Temperature",
            },
        ]
    }
    with open(sen_file, "w") as f:
        json.dump(test_sensors, f)

    cm = ConfigManager(config_path=cfg_file, sensors_path=sen_file, meta_path=meta_file)
    pipeline = Module1Pipeline(config_manager=cm, equipment_id="GT-2420A")

    # Run for a 2-day hourly test window
    t_end = dt.datetime(2026, 10, 5, 12, 0, 0)
    t_start = dt.datetime(2026, 10, 3, 12, 0, 0)

    res = pipeline.run(
        mode="test",
        force_mock=True,
        custom_start=t_start,
        custom_end=t_end,
        custom_interval="1h",
        resume=False,
    )

    assert res["status"] == "Success"
    assert res["tags_successful"] == 2
    assert res["limits_calculated"] == 10  # 2 sensors * 5 limits = 10
    assert res["sql_inserted"] == 10
    assert res["sql_skipped"] == 0

    assert pq_file.exists()
    assert csv_file.exists()
    assert db_file.exists()

    # Re-running same data should skip all 10 inserts due to deduplication
    res2 = pipeline.run(
        mode="test",
        force_mock=True,
        custom_start=t_start,
        custom_end=t_end,
        custom_interval="1h",
        resume=True,
    )
    assert res2["status"] == "Success"
    assert res2["sql_inserted"] == 0
    assert res2["sql_skipped"] == 10
