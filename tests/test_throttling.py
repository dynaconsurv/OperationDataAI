"""Unit tests for PI Web API batch call throttling to accommodate PI Vision users."""

from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from src.module1_pi_ingestion.pi_client import PIWebApiClient


def test_batch_call_throttling_delays():
    """Verify that a 5-second sleep is triggered after every 5 batch calls."""
    config = {
        "pi_web_api": {
            "url": "https://kul-pivision.pttep.com/piwebapi/",
            "batch_size": 2,
            "batch_throttle_calls": 5,
            "batch_throttle_delay_seconds": 5.0,
        }
    }

    # 12 tags with batch_size=2 results in exactly 6 batches
    tags = {f"sensor_{i}": f"webid_{i}" for i in range(12)}
    sensors = [{"full_af_path": k} for k in tags.keys()]

    client = PIWebApiClient(config=config, sensors=sensors)

    # Mock session.post to simulate successful responses without network
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        f"sensor_{i}": {
            "Status": 200,
            "Content": {"Items": [{"Timestamp": "2026-10-06T00:00:00Z", "Value": 42.0}]},
        }
        for i in range(12)
    }

    progress_messages = []

    def mock_cb(frac, msg, details):
        progress_messages.append(msg)

    with patch.object(client.session, "post", return_value=mock_resp), patch("time.sleep") as mock_sleep:
        results = client.fetch_batch_data_live(
            tag_webid_map=tags,
            start_time_str="2026-10-06T00:00:00Z",
            end_time_str="2026-10-06T01:00:00Z",
            interval="1m",
            progress_callback=mock_cb,
        )

        assert len(results) > 0
        assert client.batch_call_count == 6

        # Batch 5 should have triggered time.sleep(5.0) exactly once
        mock_sleep.assert_called_once_with(5.0)

        # Check that throttling pause message was passed to callback
        assert any("Pausing 5.0s for PI Vision" in msg for msg in progress_messages)


def test_custom_throttling_interval_and_delay():
    """Verify that custom throttle intervals (e.g. pause 2s every 3 batches) are respected."""
    config = {
        "pi_web_api": {
            "batch_size": 1,
            "batch_throttle_calls": 3,
            "batch_throttle_delay_seconds": 2.5,
        }
    }

    # 7 tags with batch_size=1 results in 7 batches
    tags = {f"sensor_{i}": f"webid_{i}" for i in range(7)}
    sensors = [{"full_af_path": k} for k in tags.keys()]

    client = PIWebApiClient(config=config, sensors=sensors)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        f"sensor_{i}": {
            "Status": 200,
            "Content": {"Items": [{"Timestamp": "2026-10-06T00:00:00Z", "Value": 10.0}]},
        }
        for i in range(7)
    }

    with patch.object(client.session, "post", return_value=mock_resp), patch("time.sleep") as mock_sleep:
        client.fetch_batch_data_live(
            tag_webid_map=tags,
            start_time_str="2026-10-06T00:00:00Z",
            end_time_str="2026-10-06T01:00:00Z",
            interval="1m",
        )

        assert client.batch_call_count == 7
        # 7 batches with interval 3 should pause at batch #3 and batch #6 (twice)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2.5)
