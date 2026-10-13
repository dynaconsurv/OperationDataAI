"""Unit tests for Module 3 CorrelationDigitalTwin Predictive Engine."""

import numpy as np
import pandas as pd
import pytest

from src.module3_prediction.correlation_digital_twin import CorrelationDigitalTwin


@pytest.fixture
def synthetic_turbine_telemetry():
    """Generate synthetic telemetry with physically coupled sensors and an injected anomaly."""
    np.random.seed(42)
    n = 200
    time_idx = pd.date_range("2026-01-01", periods=n, freq="1h")

    # Base operating load
    load = 50 + 20 * np.sin(np.linspace(0, 10, n))

    # Tightly coupled exhaust temperature cluster
    tc7 = load * 10.0 + np.random.normal(0, 1.0, n) + 40.0
    tc8 = tc7 * 0.99 + np.random.normal(0, 0.5, n) + 5.0
    tc9 = tc7 * 1.01 + np.random.normal(0, 0.5, n) - 5.0

    # Bearing pair cluster
    b1 = load * 0.8 + 30.0 + np.random.normal(0, 0.3, n)
    b2 = b1 * 0.98 + np.random.normal(0, 0.2, n) + 1.0

    # Process compressor pressure & fuel gas
    pcd = load * 0.2 + 2.0 + np.random.normal(0, 0.1, n)
    fuel = pcd * 2.0 + np.random.normal(0, 0.2, n)

    # Inject progressive combustion anomaly on tc8 starting at t=160
    tc8_anom = np.copy(tc8)
    tc8_anom[160:] -= np.linspace(5, 60, n - 160)

    df = pd.DataFrame(
        {
            "Exhaust_Temp_7": tc7,
            "Exhaust_Temp_8": tc8_anom,
            "Exhaust_Temp_9": tc9,
            "Bearing_Temp_1": b1,
            "Bearing_Temp_2": b2,
            "Compressor_PCD": pcd,
            "Interstage_Fuel_Gas": fuel,
        },
        index=time_idx,
    )
    return df


def test_digital_twin_fit_and_peers(synthetic_turbine_telemetry):
    df = synthetic_turbine_telemetry
    catalog = [
        {"full_af_path": "Exhaust_Temp_8", "subsystem": "Gas Turbine Engine", "tag_name": "Exhaust Temp 8"},
        {"full_af_path": "Bearing_Temp_1", "subsystem": "Compressor", "tag_name": "Bearing Temp 1"},
    ]

    twin = CorrelationDigitalTwin(top_n_peers=3, min_correlation=0.7, sensor_catalog=catalog)
    twin.fit(df.iloc[:150])  # Train on healthy data only

    assert twin.is_trained
    assert len(twin.models) > 0
    assert "Exhaust_Temp_8" in twin.peer_map

    # TC8 should have selected TC7 and TC9 as peers
    peers_tc8 = twin.peer_map["Exhaust_Temp_8"]
    assert "Exhaust_Temp_7" in peers_tc8
    assert "Exhaust_Temp_9" in peers_tc8


def test_digital_twin_anomaly_detection_and_culprit(synthetic_turbine_telemetry):
    df = synthetic_turbine_telemetry
    twin = CorrelationDigitalTwin(top_n_peers=3, min_correlation=0.7)
    twin.fit(df.iloc[:150])

    scored = twin.score_telemetry(df)

    assert not scored.empty
    assert "composite_anomaly_score" in scored.columns
    assert "is_anomaly" in scored.columns
    assert "top_culprit_sensor" in scored.columns
    assert "top_culprit_sci_pct" in scored.columns

    # In healthy section (t < 150), anomaly rate should be very low
    healthy_anoms = scored.iloc[:140]["is_anomaly"].sum()
    assert healthy_anoms <= 3

    # In degraded section (t >= 180), anomaly should be flagged with TC8 as culprit
    tail_scores = scored.iloc[180:]
    assert tail_scores["is_anomaly"].any()

    # Verify TC8 is identified as primary culprit sensor
    culprits = tail_scores[tail_scores["is_anomaly"]]["top_culprit_sensor"].value_counts()
    assert "Exhaust_Temp_8" in culprits.index
    assert culprits.index[0] == "Exhaust_Temp_8"


def test_digital_twin_early_warning_diagnosis(synthetic_turbine_telemetry):
    df = synthetic_turbine_telemetry
    catalog = [
        {"full_af_path": "Exhaust_Temp_8", "subsystem": "Gas Turbine Engine", "tag_name": "Exhaust Temperature 8"},
    ]
    twin = CorrelationDigitalTwin(top_n_peers=3, sensor_catalog=catalog)
    twin.fit(df.iloc[:150])

    # Diagnose an anomalous timestamp in the degradation period
    anom_ts = df.index[190]
    alert = twin.diagnose_anomaly(df, timestamp=anom_ts)

    assert alert["is_anomaly"]
    assert alert["asset_id"] == "GT-2420A"
    assert alert["culprit_sensor"]["sensor_path"] == "Exhaust_Temp_8"
    assert alert["culprit_sensor"]["residual_deviation"] < -20.0
    assert alert["culprit_sensor"]["contribution_index_pct"] > 50.0

    # Verify supporting witness sensors are present
    assert len(alert["supporting_witness_sensors"]) > 0

    # Verify root cause and actions are generated
    assert "Combustion" in alert["root_cause_diagnosis"] or "flame" in alert["root_cause_diagnosis"].lower()
    assert len(alert["prescribed_operator_actions"]) >= 2


def test_digital_twin_serialization(synthetic_turbine_telemetry, tmp_path):
    df = synthetic_turbine_telemetry
    twin = CorrelationDigitalTwin()
    twin.fit(df.iloc[:100])

    model_file = tmp_path / "model.pkl"
    twin.save_model(model_file)
    assert model_file.exists()

    loaded_twin = CorrelationDigitalTwin.load_model(model_file)
    assert loaded_twin.is_trained
    assert len(loaded_twin.models) == len(twin.models)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
