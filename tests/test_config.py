"""Unit tests for ConfigManager."""

import json
from pathlib import Path
from src.config_manager import ConfigManager


def test_config_manager_load_and_save(tmp_path: Path):
    cfg_file = tmp_path / "config.json"
    sen_file = tmp_path / "sensors.json"
    meta_file = tmp_path / "last_run_meta.json"

    cm = ConfigManager(config_path=cfg_file, sensors_path=sen_file, meta_path=meta_file)

    # Load defaults
    cfg = cm.load_config()
    assert cfg["app_name"] == "PTTEP Gas Turbine (GT-2420A) PI Analytics"
    assert cfg["pi_web_api"]["username"] == "zaqeelahr"
    assert cfg["database"]["user"] == "pi-ai"

    # Modify and save
    cfg["pi_web_api"]["timeout_seconds"] = 45
    cm.save_config(cfg)

    # Reload and verify
    reloaded = cm.load_config()
    assert reloaded["pi_web_api"]["timeout_seconds"] == 45

    # Test metadata
    meta = cm.load_last_run_meta()
    assert "status" in meta
    meta["status"] = "Success"
    cm.save_last_run_meta(meta)
    reloaded_meta = cm.load_last_run_meta()
    assert reloaded_meta["status"] == "Success"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
