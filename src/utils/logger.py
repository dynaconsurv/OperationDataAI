"""Application Logging Utility.
Provides formatted logging with timestamps and file output support.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LOG_FILE = LOG_DIR / "app.log"


def get_logger(name: str = "PTTEP_AI", log_file: Optional[Path] = DEFAULT_LOG_FILE) -> logging.Logger:
    """Return a configured logger with console and optional file handlers."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not initialize file log handler at {log_file}: {e}")

    return logger
