"""Configuration Manager for PTTEP PI Analytics Application.

Handles loading, validating, and saving application configurations,
sensor registries, and runtime metadata stored as JSON files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default Paths
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"

CONFIG_FILE = CONFIG_DIR / "config.json"
SENSORS_FILE = CONFIG_DIR / "sensors.json"
LAST_RUN_META_FILE = CONFIG_DIR / "last_run_meta.json"


DEFAULT_CONFIG: Dict[str, Any] = {
    "app_name": "PTTEP Gas Turbine (GT-2420A) PI Analytics",
    "version": "1.0.0",
    "pi_web_api": {
        "url": "https://kul-pivision.pttep.com/piwebapi/",
        "af_db": r"\\KUL-PIAF\GEG RPM\\",
        "username": "zaqeelahr",
        "password": "Welcome@1234567",
        "auth_type": "basic",  # 'basic' or 'ntlm'
        "verify_ssl": False,
        "timeout_seconds": 30,
        "mock_mode": True,  # Safe development default
        "query_mode": "interpolated",  # 'interpolated' or 'recorded'
        "sample_interval": "1h",
        "batch_size": 25,
        "test_duration_days": 1,
        "full_duration_months": 12,
    },
    "database": {
        "engine": "mssql",  # 'mssql' or 'sqlite'
        "host": "localhost",
        "port": 1433,
        "database": "OperationLimits",
        "user": "pi-ai",
        "password": "Ptt3p@2026",
        "driver": "SQL Server",
        "table_name": "operating_limits",
        "use_sqlite_fallback": True,
        "sqlite_path": "data/operating_limits.db",
    },
    "operating_limits": {
        "method": "percentile",  # 'percentile' or 'sigma'
        "normal_stat": "median",  # 'median' or 'mean'
        "sigma_multipliers": {
            "hh": 3.0,
            "h": 2.0,
            "l": 2.0,
            "ll": 3.0,
        },
        "percentiles": {
            "ll": 1.0,
            "l": 5.0,
            "h": 95.0,
            "hh": 99.0,
        },
    },
    "correlation": {
        "method": "pearson",  # 'pearson' or 'spearman'
        "min_periods": 30,
        "top_n_pairs": 20,
    },
    "storage": {
        "pickle_file": "data/historical_data.pkl",
        "correlation_file": "data/correlation_matrix.csv",
        "limits_csv_file": "data/operating_limits.csv",
    },
}


class ConfigManager:
    """Manages reading and writing application configurations."""

    def __init__(
        self,
        config_path: Path = CONFIG_FILE,
        sensors_path: Path = SENSORS_FILE,
        meta_path: Path = LAST_RUN_META_FILE,
    ) -> None:
        self.config_path = Path(config_path)
        self.sensors_path = Path(sensors_path)
        self.meta_path = Path(meta_path)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure necessary parent directories exist."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """Load application configuration from JSON. Create default if missing."""
        if not self.config_path.exists():
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge with defaults for any missing keys
            merged = DEFAULT_CONFIG.copy()
            for key, val in data.items():
                if isinstance(val, dict) and key in merged and isinstance(merged[key], dict):
                    merged[key].update(val)
                else:
                    merged[key] = val
            return merged
        except Exception as e:
            print(f"Error loading {self.config_path}, falling back to defaults: {e}")
            return DEFAULT_CONFIG.copy()

    def save_config(self, config_data: Dict[str, Any]) -> None:
        """Save configuration dictionary to config.json."""
        self._ensure_directories()
        temp_file = self.config_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
        temp_file.replace(self.config_path)

    def load_sensors(self) -> List[Dict[str, Any]]:
        """Load sensor catalog from sensors.json."""
        if not self.sensors_path.exists():
            return []
        try:
            with open(self.sensors_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {self.sensors_path}: {e}")
            return []

    def save_sensors(self, sensors: List[Dict[str, Any]]) -> None:
        """Save sensor list to sensors.json."""
        self._ensure_directories()
        temp_file = self.sensors_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(sensors, f, indent=4)
        temp_file.replace(self.sensors_path)

    def load_last_run_meta(self) -> Dict[str, Any]:
        """Load execution metadata (timestamps, duration, counts)."""
        if not self.meta_path.exists():
            default_meta = {
                "last_pull_timestamp": None,
                "duration_seconds": 0.0,
                "pull_mode": "None",
                "time_range": "N/A",
                "tags_requested": 0,
                "tags_successful": 0,
                "data_points_collected": 0,
                "limits_calculated": 0,
                "sql_inserted": 0,
                "sql_skipped": 0,
                "status": "Ready",
                "last_error": None,
            }
            self.save_last_run_meta(default_meta)
            return default_meta

        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {self.meta_path}: {e}")
            return {}

    def resolve_path(self, path_str: str) -> Path:
        """Resolve a file or directory path relative to project BASE_DIR if not absolute."""
        p = Path(path_str)
        if p.is_absolute():
            return p
        return BASE_DIR / p

    def save_last_run_meta(self, meta: Dict[str, Any]) -> None:
        """Persist execution metadata."""
        self._ensure_directories()
        temp_file = self.meta_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)
        temp_file.replace(self.meta_path)
