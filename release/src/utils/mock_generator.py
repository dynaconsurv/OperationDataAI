"""Synthetic telemetry generator for Module 1 Portable Release.
Generates realistic multi-sensor operational data for testing when PI Web API is unreachable.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def normalize_pandas_freq(freq_str: str) -> str:
    """Convert frequency strings (e.g. '1m', '1h', '1d') to pandas aliases ('1min', '1h', '1D')."""
    f = str(freq_str).strip().lower()
    if f.endswith("m") and not f.endswith("mo") and not f.endswith("min"):
        return f + "in"
    if f.endswith("d"):
        return f.upper()
    return freq_str


def generate_mock_telemetry(
    sensors: List[Dict[str, Any]],
    start_time: Optional[dt.datetime] = None,
    end_time: Optional[dt.datetime] = None,
    freq: str = "1h",
    random_seed: int = 42,
) -> pd.DataFrame:
    """Generate a realistic DataFrame of historical time-series data for all sensors.

    Parameters
    ----------
    sensors : list of dict
        List of sensor definitions containing 'full_af_path', 'sim_range', 'category', 'subsystem'.
    start_time : datetime, optional
        Start of the time series (default: 6 months ago if None).
    end_time : datetime, optional
        End of the time series (default: now).
    freq : str
        Sampling frequency, e.g. '1h'.
    random_seed : int
        Seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Indexed by Timestamp, with columns matching 'full_af_path'.
    """
    np.random.seed(random_seed)

    if end_time is None:
        end_time = dt.datetime.now().replace(minute=0, second=0, microsecond=0)
    if start_time is None:
        start_time = end_time - dt.timedelta(days=183)

    pandas_freq = normalize_pandas_freq(freq)
    timestamps = pd.date_range(start=start_time, end=end_time, freq=pandas_freq)
    n_points = len(timestamps)

    if n_points == 0:
        return pd.DataFrame()

    t_arr = np.linspace(0, 10 * np.pi, n_points)
    data_dict: Dict[str, np.ndarray] = {}

    for sensor in sensors:
        path = sensor.get("full_af_path") or sensor.get("parent", "Sensor")
        sim_range = sensor.get("sim_range", [10.0, 100.0])
        category = sensor.get("category", "General")

        min_val, max_val = float(sim_range[0]), float(sim_range[1])
        span = max_val - min_val
        mid_val = min_val + 0.5 * span

        freq_factor = 1.0 + (hash(path) % 5) * 0.2
        phase_shift = (hash(path) % 10) * 0.5

        if category == "Temperature":
            base = mid_val + 0.15 * span * np.sin(freq_factor * t_arr + phase_shift)
            noise = np.random.normal(0, 0.02 * span, n_points)
        elif category in ("Vibration", "Speed"):
            base = mid_val + 0.20 * span * np.cos(freq_factor * t_arr + phase_shift)
            noise = np.random.normal(0, 0.04 * span, n_points)
        elif category in ("Pressure", "Differential Pressure"):
            base = mid_val + 0.10 * span * np.sin(freq_factor * t_arr + phase_shift)
            noise = np.random.normal(0, 0.015 * span, n_points)
        elif category in ("Flow", "Power"):
            base = mid_val + 0.25 * span * np.sin(freq_factor * 0.5 * t_arr + phase_shift)
            noise = np.random.normal(0, 0.03 * span, n_points)
        else:
            base = mid_val + 0.10 * span * np.sin(freq_factor * t_arr)
            noise = np.random.normal(0, 0.02 * span, n_points)

        series_vals = np.clip(base + noise, min_val, max_val)
        data_dict[path] = series_vals

    df = pd.DataFrame(data_dict, index=timestamps)
    df.index.name = "timestamp"
    return df
