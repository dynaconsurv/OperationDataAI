"""Tests for FastAPI REST service serving Module 3 to PI Vision."""

import pytest
from src.api import app as api_module
from src.api.app import (
    app,
    get_health,
    get_latest_advisory,
    get_sensor_catalog,
    lifespan,
    render_advisory_html_card,
    sync_telemetry_and_predict,
)


@pytest.fixture(scope="module", autouse=True)
def setup_api():
    """Ensure API model and cache are initialized."""
    import asyncio
    async def _init():
        async with lifespan(app):
            yield
    # Run lifecycle initialization
    ctx = lifespan(app)
    asyncio.run(ctx.__aenter__())
    yield
    asyncio.run(ctx.__aexit__(None, None, None))


def test_health_endpoint():
    data = get_health()
    assert data["status"] == "HEALTHY"
    assert data["asset_id"] == "GT-2420A"
    assert data["is_trained"] is True
    assert data["modeled_sensors_count"] > 100


def test_sensors_catalog_endpoint():
    data = get_sensor_catalog()
    assert data["asset_id"] == "GT-2420A"
    assert data["total_sensors"] > 100
    assert len(data["sensors"]) > 100
    first_sensor = data["sensors"][0]
    assert "tag_name" in first_sensor
    assert "peer_sensors" in first_sensor


def test_latest_advisory_endpoint():
    data = get_latest_advisory(lookback=24)
    assert "alert_id" in data
    assert "health_score" in data
    assert "predicted_incident" in data
    assert "culprit_sensor" in data
    assert "prescribed_operator_actions" in data


def test_simulate_fault_endpoint():
    data = get_latest_advisory(lookback=24, simulate_fault="combustion")
    assert data["is_anomaly"] is True
    assert data["severity"] == "CRITICAL"
    assert "Exhaust Temperature 8" in data["culprit_sensor"]["tag_name"]
    assert data["culprit_sensor"]["contribution_index_pct"] > 50.0


def test_card_html_endpoint():
    html_text = render_advisory_html_card(simulate="combustion")
    assert "PTTEP GT-2420A DIGITAL TWIN" in html_text
    assert "TURBINE HEALTH SCORE" in html_text
    assert "CRITICAL" in html_text


def test_sync_telemetry_endpoint():
    data = sync_telemetry_and_predict(save_parquet=False, sync_hours=1)
    assert data["status"] == "SYNCED_AND_EVALUATED"
    assert data["ingested_points"] > 0
    assert "advisory" in data
    assert "health_score" in data["advisory"]


def test_historical_advisory_query():
    # Query a specific historical time in September 2026
    data = get_latest_advisory(timestamp="2026-09-18 06:24:00", lookback=24)
    assert "alert_id" in data
    assert "20260918" in data["alert_id"]
    assert "health_score" in data
    assert "culprit_sensor" in data


