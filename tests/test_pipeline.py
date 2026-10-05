"""Integration test for Module 1 Pipeline."""

from pathlib import Path
from src.config_manager import ConfigManager
from src.module1_pi_ingestion.pipeline import Module1Pipeline


def test_module1_pipeline_mock_run(tmp_path: Path):
    cfg_file = tmp_path / "config.json"
    sen_file = tmp_path / "sensors.json"
    meta_file = tmp_path / "last_run_meta.json"
    db_file = tmp_path / "test.db"
    pickle_file = tmp_path / "test_data.pkl"

    cm = ConfigManager(config_path=cfg_file, sensors_path=sen_file, meta_path=meta_file)
    cfg = cm.load_config()
    cfg["pi_web_api"]["mock_mode"] = True
    cfg["database"]["engine"] = "sqlite"
    cfg["database"]["sqlite_path"] = str(db_file)
    cfg["storage"]["pickle_file"] = str(pickle_file)
    cm.save_config(cfg)

    # Use a small set of sensors for fast integration test
    test_sensors = [
        {"parent": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "attribute_name": "Parameter", "full_af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "tag_name": "Ambient Inlet Pressure", "subsystem": "Air Filter System", "sim_range": [0.9, 1.1]},
        {"parent": r"MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Tank Level", "attribute_name": "Parameter", "full_af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Tank Level", "tag_name": "Lube Oil Tank Level", "subsystem": "Lube Oil System", "sim_range": [40.0, 80.0]},
    ]
    cm.save_sensors(test_sensors)

    pipeline = Module1Pipeline(config_manager=cm)
    res = pipeline.run(mode="test", force_mock=True)

    assert res["status"] == "Success"
    assert res["tags_successful"] == 2
    assert res["limits_calculated"] == 10  # 2 tags * 5 limits (Normal, HH, H, L, LL)
    assert res["sql_inserted"] == 10
    assert res["sql_skipped"] == 0
    assert pickle_file.exists()

    # Re-run pipeline with same data -> deduplication should skip all 10 inserts!
    res2 = pipeline.run(mode="test", force_mock=True)
    assert res2["status"] == "Success"
    assert res2["sql_inserted"] == 0
    assert res2["sql_skipped"] == 10


def test_module1_pipeline_minute_hourly_slicing(tmp_path: Path):
    import datetime as dt

    cfg_file = tmp_path / "config_m.json"
    sen_file = tmp_path / "sensors_m.json"
    meta_file = tmp_path / "meta_m.json"
    db_file = tmp_path / "test_m.db"
    pickle_file = tmp_path / "test_m.pkl"

    cm = ConfigManager(config_path=cfg_file, sensors_path=sen_file, meta_path=meta_file)
    cfg = cm.load_config()
    cfg["pi_web_api"]["mock_mode"] = True
    cfg["database"]["engine"] = "sqlite"
    cfg["database"]["sqlite_path"] = str(db_file)
    cfg["storage"]["pickle_file"] = str(pickle_file)
    cm.save_config(cfg)

    test_sensors = [
        {"parent": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "attribute_name": "Parameter", "full_af_path": r"MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure", "tag_name": "Ambient Inlet Pressure", "subsystem": "Air Filter System", "sim_range": [0.9, 1.1]},
    ]
    cm.save_sensors(test_sensors)

    # 3-hour window with 1m sampling
    t_start = dt.datetime(2026, 10, 5, 8, 0, 0)
    t_end = dt.datetime(2026, 10, 5, 11, 0, 0)

    pipeline = Module1Pipeline(config_manager=cm)
    res = pipeline.run(
        mode="test",
        force_mock=True,
        custom_start=t_start,
        custom_end=t_end,
        custom_interval="1m",
    )

    assert res["status"] == "Success"
    assert res["sample_interval"] == "1m"
    assert res["tags_successful"] == 1
    # 3 hours at 1m interval = 181 points
    assert res["data_points_collected"] == 181
    assert res["limits_calculated"] == 5


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])

