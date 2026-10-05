"""Unit tests for LimitsCalculator."""

import numpy as np
import pandas as pd
from src.module1_pi_ingestion.limits_calculator import LimitsCalculator


def test_percentile_limits():
    cfg = {
        "operating_limits": {
            "method": "percentile",
            "normal_stat": "median",
            "percentiles": {"ll": 1.0, "l": 5.0, "h": 95.0, "hh": 99.0},
        }
    }
    calc = LimitsCalculator(cfg)
    # Generate 1000 standard normal points
    np.random.seed(42)
    data = pd.Series(np.linspace(1, 100, 1000))

    limits = calc.compute_sensor_limits(data)
    assert "Normal" in limits
    assert "HH" in limits
    assert "H" in limits
    assert "L" in limits
    assert "LL" in limits

    # Monotonicity check
    assert limits["LL"] < limits["L"] < limits["Normal"] < limits["H"] < limits["HH"]
    assert 49.0 <= limits["Normal"] <= 51.5


def test_sigma_limits():
    cfg = {
        "operating_limits": {
            "method": "sigma",
            "normal_stat": "mean",
            "sigma_multipliers": {"hh": 3.0, "h": 2.0, "l": 2.0, "ll": 3.0},
        }
    }
    calc = LimitsCalculator(cfg)
    np.random.seed(42)
    # Mean 50, std 10
    data = pd.Series(np.random.normal(50.0, 10.0, 5000))

    limits = calc.compute_sensor_limits(data)
    assert limits["LL"] < limits["L"] < limits["Normal"] < limits["H"] < limits["HH"]
    assert 48.0 < limits["Normal"] < 52.0
    assert 65.0 < limits["H"] < 75.0
    assert 75.0 < limits["HH"] < 85.0
    assert 25.0 < limits["L"] < 35.0
    assert 15.0 < limits["LL"] < 25.0


def test_compute_all_limits():
    cfg = {"operating_limits": {"method": "percentile", "normal_stat": "median"}}
    calc = LimitsCalculator(cfg)
    df = pd.DataFrame({
        "Tag1": np.linspace(10, 50, 100),
        "Tag2": np.linspace(100, 200, 100),
    })

    records, summary_df = calc.compute_all_limits(df)
    # 2 tags * 5 limits = 10 records
    assert len(records) == 10
    assert len(summary_df) == 2
    assert "HH" in summary_df.columns
    assert "LL" in summary_df.columns


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
