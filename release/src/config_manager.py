"""Configuration Manager for Module 1 Portable Release.
Handles loading configuration, equipment-grouped sensor catalogs, and runtime execution metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger("ConfigManager")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"

CONFIG_FILE = CONFIG_DIR / "config.json"
SENSORS_FILE = CONFIG_DIR / "sensors.json"
LAST_RUN_META_FILE = CONFIG_DIR / "last_run_meta.json"


class ConfigManager:
    """Manages application configurations and equipment-grouped sensor catalogs."""

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
        self.sensors_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """Load and return configuration from config.json."""
        if not self.config_path.exists():
            logger.error(f"Config file not found at {self.config_path}")
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {self.config_path}: {e}")
            return {}

    def save_config(self, config: Dict[str, Any]) -> None:
        """Persist configuration dictionary to config.json."""
        self._ensure_directories()
        temp_file = self.config_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        temp_file.replace(self.config_path)

    def load_sensors(self, equipment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load sensor list from sensors.json.
        Supports both:
        1. Grouped dictionary format: {"GT-2420A": [sensors...]}
        2. Flat list format: [sensors...]

        Parameters
        ----------
        equipment_id : str, optional
            Filter sensors for this specific equipment (e.g. 'GT-2420A').
            If None, uses 'target_equipment' from config.json.
            If 'all', concatenates all sensors across all equipment.
        """
        if not self.sensors_path.exists():
            logger.error(f"Sensors file not found at {self.sensors_path}")
            return []

        try:
            with open(self.sensors_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                cfg = self.load_config()
                target_eq = equipment_id or cfg.get("target_equipment", "GT-2420A")

                if target_eq.lower() == "all":
                    flat_list: List[Dict[str, Any]] = []
                    for eq_name, tag_list in data.items():
                        if isinstance(tag_list, list):
                            flat_list.extend(tag_list)
                    logger.info(f"Loaded all {len(flat_list)} sensors across all equipment ({list(data.keys())})")
                    return flat_list
                else:
                    selected = data.get(target_eq, [])
                    logger.info(f"Loaded {len(selected)} sensors for equipment '{target_eq}' from {self.sensors_path}")
                    return selected

            elif isinstance(data, list):
                if equipment_id and equipment_id.lower() != "all":
                    filtered = [
                        s for s in data
                        if s.get("equipment_id") == equipment_id or equipment_id in s.get("parent", "")
                    ]
                    logger.info(f"Loaded {len(filtered)} filtered sensors for '{equipment_id}' from flat list")
                    return filtered
                logger.info(f"Loaded {len(data)} sensors from flat list {self.sensors_path}")
                return data

            return []
        except Exception as e:
            logger.error(f"Error loading {self.sensors_path}: {e}")
            return []

    def save_sensors(self, sensors_data: Any) -> None:
        """Save sensor catalog (dict or list) to sensors.json."""
        self._ensure_directories()
        temp_file = self.sensors_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(sensors_data, f, indent=2)
        temp_file.replace(self.sensors_path)

    def load_last_run_meta(self) -> Dict[str, Any]:
        """Load execution metadata from last_run_meta.json."""
        if not self.meta_path.exists():
            return {}
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {self.meta_path}: {e}")
            return {}

    def save_last_run_meta(self, meta: Dict[str, Any]) -> None:
        """Save pipeline execution metadata to last_run_meta.json."""
        self._ensure_directories()
        temp_file = self.meta_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)
        temp_file.replace(self.meta_path)

    def resolve_path(self, path_str: str) -> Path:
        """Resolve a relative path against release BASE_DIR."""
        p = Path(path_str)
        if p.is_absolute():
            return p
        return BASE_DIR / p
