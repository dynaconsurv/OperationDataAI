"""High-fidelity synthetic time-series telemetry generator for GT-2420A.
Generates realistic multi-sensor operational data adhering to physical thermodynamic,
vibrational, and aerodynamic relations for testing the analytics framework without
connecting to the live PI Web API server.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def normalize_pandas_freq(freq_str: str) -> str:
    """Convert PI Web API frequency strings (e.g. '1m', '10m', '1d') to pandas aliases ('1min', '10min', '1D')."""
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
        Start of the time series (default: 12 months ago if None and end_time is None).
    end_time : datetime, optional
        End of the time series (default: now).
    freq : str
        Sampling frequency, e.g. '1h', '10min'.
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
        start_time = end_time - dt.timedelta(days=365)

    pandas_freq = normalize_pandas_freq(freq)
    timestamps = pd.date_range(start=start_time, end=end_time, freq=pandas_freq)
    n_points = len(timestamps)

    if n_points == 0:
        return pd.DataFrame()

    # Base operating cycles (diurnal ambient temperature cycle + turbine load cycle)
    hours = np.array([t.hour + t.minute / 60.0 for t in timestamps])
    day_fraction = (timestamps - timestamps[0]).total_seconds() / (24 * 3600)

    # Ambient daily fluctuation (24-hour cycle)
    ambient_cycle = np.sin(2 * np.pi * (hours - 9) / 24.0)

    # Turbine load profile (weekly cyclicality + occasional planned shutdowns or load changes)
    load_factor = 0.85 + 0.10 * np.sin(2 * np.pi * day_fraction / 7.0) + 0.05 * np.sin(2 * np.pi * day_fraction / 30.0)
    load_factor = np.clip(load_factor + np.random.normal(0, 0.02, n_points), 0.5, 1.0)

    data: Dict[str, np.ndarray] = {}

    for sensor in sensors:
        path = sensor.get("full_af_path", sensor.get("tag_name", "Unknown"))
        tag_name = sensor.get("tag_name", "").lower()
        sim_range = sensor.get("sim_range", [10.0, 100.0])
        category = sensor.get("category", "Process Parameter")

        min_val, max_val = float(sim_range[0]), float(sim_range[1])
        span = max_val - min_val
        mid = (min_val + max_val) / 2.0

        noise = np.random.normal(0, span * 0.03, n_points)

        # Physics-driven sensor modeling
        if "ambient" in tag_name:
            # Ambient inlet pressure or temperature
            base = min_val + 0.5 * span + (span * 0.35) * ambient_cycle
            series = base + noise
        elif "exhaust temperature" in tag_name:
            # Exhaust gas temperature thermocouples (tightly correlated with load and each other)
            # Add small channel-specific offset to simulate thermocouple spread
            tc_offset = np.random.uniform(-8.0, 8.0)
            base = min_val + span * (0.60 + 0.35 * load_factor) + tc_offset
            series = base + noise * 0.5
        elif "spread exhaust" in tag_name:
            # Temperature spread is small (10 to 35 degC)
            series = 15.0 + 8.0 * load_factor + np.abs(np.random.normal(0, 2.5, n_points))
        elif "vibration" in tag_name:
            # Vibration increases slightly with load and has log-normal like random spikes
            base = min_val + (span * 0.25) * load_factor
            vib_noise = np.random.exponential(scale=span * 0.08, size=n_points)
            series = base + vib_noise
        elif "bearing" in tag_name and "temperature" in tag_name:
            # Bearing temperatures rise with shaft speed & lube oil temperature
            base = min_val + span * (0.50 + 0.40 * load_factor)
            series = base + noise * 0.8
        elif "lube oil" in tag_name and "temperature" in tag_name:
            base = 45.0 + 15.0 * load_factor + 5.0 * ambient_cycle
            series = base + noise * 0.5
        elif "lube oil" in tag_name and "level" in tag_name:
            # Tank level is relatively steady with slow drift
            slow_drift = np.sin(2 * np.pi * day_fraction / 90.0) * 4.0
            series = 72.0 + slow_drift + np.random.normal(0, 0.5, n_points)
        elif "lube oil" in tag_name and "pressure" in tag_name:
            base = 2.8 + 0.3 * load_factor
            series = base + np.random.normal(0, 0.05, n_points)
        elif "speed" in tag_name:
            # High speed shaft around 9000-9400 RPM
            base = min_val + span * (0.88 + 0.10 * load_factor)
            series = base + noise * 0.2
        elif "differential pressure" in tag_name or "dp" in tag_name:
            # Filter DP slowly rises over time as filters load up
            clogging = (day_fraction / 365.0) * (span * 0.3)
            base = min_val + (span * 0.2) + clogging + (span * 0.2) * load_factor
            series = base + noise * 0.5
        elif "flame" in tag_name:
            # Flame detector intensity
            series = np.clip(85.0 + 10.0 * load_factor + np.random.normal(0, 2.0, n_points), 0.0, 100.0)
        elif "position" in tag_name or "asv" in tag_name:
            # ASV opens at lower load, closes at full load
            series = np.clip((1.0 - load_factor) * 100.0 + noise, 0.0, 100.0)
        else:
            # General process tag
            base = min_val + span * (0.45 + 0.40 * load_factor)
            series = base + noise

        # Ensure values stay bounded in realistic engineering limits
        data[path] = np.clip(series, min_val * 0.8, max_val * 1.2)

    df = pd.DataFrame(data, index=timestamps)
    df.index.name = "timestamp"
    return df
