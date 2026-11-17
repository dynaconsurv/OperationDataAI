"""
Pull 10-second ('10s') high-resolution PI telemetry across all 158 sensors
for all 13 Stop/Trip events identified in data/historical_data.parquet.

Window per event: [t_event - 35 minutes, t_event + 10 minutes] (45 mins @ 10s = 271 rows/event).
Saves:
  - Individual event Parquet files in: data/trip_events_10s/event_XX_YYYYMMDD_HHMM.parquet
  - Combined master Parquet file in: data/trip_events_10s_combined.parquet
Does NOT touch or alter data/historical_data.parquet.
"""

import time
from pathlib import Path
import pandas as pd

from src.config_manager import ConfigManager
from src.module1_pi_ingestion.pi_client import PIWebApiClient
from src.utils.logger import get_logger

logger = get_logger("PullTripEvents10s")

PROJECT_ROOT = Path(__file__).resolve().parent
OUT_DIR = PROJECT_ROOT / "data" / "trip_events_10s"
COMBINED_PATH = PROJECT_ROOT / "data" / "trip_events_10s_combined.parquet"

# All 13 full-speed Stop / Trip events (UTC timestamps where drop initiated)
TRIP_EVENTS = [
    {"event_id": 1,  "ts": "2025-10-07 07:15:00", "type": "Fired_Shutdown",     "label": "Event01_20251007_0715_FiredShutdown"},
    {"event_id": 2,  "ts": "2025-10-31 07:05:00", "type": "Fired_Shutdown_DGS", "label": "Event02_20251031_0705_SealGasAmpDP"},
    {"event_id": 3,  "ts": "2025-12-07 07:34:00", "type": "Fired_Shutdown_ASV", "label": "Event03_20251207_0734_AntiSurge"},
    {"event_id": 4,  "ts": "2026-01-05 01:24:00", "type": "Hard_Trip_FullLoad", "label": "Event04_20260105_0124_HardTrip1"},
    {"event_id": 5,  "ts": "2026-01-05 03:21:00", "type": "Hard_Trip_Restart",  "label": "Event05_20260105_0321_HardTrip2"},
    {"event_id": 6,  "ts": "2026-01-15 04:42:00", "type": "Fired_Shutdown",     "label": "Event06_20260115_0442_FiredShutdown"},
    {"event_id": 7,  "ts": "2026-02-04 03:37:00", "type": "Fired_Shutdown_DGS", "label": "Event07_20260204_0337_SealGasFilterDP"},
    {"event_id": 8,  "ts": "2026-04-23 05:41:00", "type": "Fired_Shutdown_DGS", "label": "Event08_20260423_0541_SealGasAmpDP"},
    {"event_id": 9,  "ts": "2026-08-19 05:25:00", "type": "Fired_Shutdown",     "label": "Event09_20260819_0525_FiredShutdown"},
    {"event_id": 10, "ts": "2026-08-22 09:06:00", "type": "Fired_Shutdown_Vib", "label": "Event10_20260822_0906_CompVib"},
    {"event_id": 11, "ts": "2026-08-25 07:11:00", "type": "Fired_Shutdown",     "label": "Event11_20260825_0711_FiredShutdown"},
    {"event_id": 12, "ts": "2026-08-29 09:11:00", "type": "Fired_Shutdown",     "label": "Event12_20260829_0911_FiredShutdown"},
    {"event_id": 13, "ts": "2026-09-02 07:07:00", "type": "Fired_Shutdown",     "label": "Event13_20260902_0707_FiredShutdown"},
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cm = ConfigManager()
    config = cm.load_config()
    sensors = cm.load_sensors()

    client = PIWebApiClient(config, sensors)
    client.mock_mode = False  # Force LIVE PI Web API mode over VPN

    print(f"Connecting to LIVE PI Web API at: {client.base_url}")
    tag_webid_map = {}
    for s in sensors:
        parent = s.get("parent", "")
        attr_name = s.get("attribute_name", "Parameter")
        path_key = s.get("full_af_path", parent)
        web_id = s.get("web_id") or client.resolve_attribute_webid(parent, attr_name)
        if web_id:
            tag_webid_map[path_key] = web_id

    print(f"Resolved {len(tag_webid_map)} / {len(sensors)} sensor WebIDs.")
    if not tag_webid_map:
        raise RuntimeError("Could not resolve any WebIDs! Check VPN / PI Server connection.")

    all_dfs = []
    t_all_start = time.time()

    for ev in TRIP_EVENTS:
        ev_id = ev["event_id"]
        t_ev = pd.to_datetime(ev["ts"], utc=True)
        # Collect 40 minutes before event until +10 minutes after event (50 mins @ 10s = 301 rows)
        t_start = t_ev - pd.Timedelta(minutes=40)
        t_end = t_ev + pd.Timedelta(minutes=10)

        start_str = t_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = t_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        out_file = OUT_DIR / f"{ev['label']}_10s.parquet"

        print(f"\n[{ev_id:02d}/13] Pulling {ev['label']} ({start_str} to {end_str}, interval=10s)...")
        t0 = time.time()

        batch_series = client.fetch_batch_data_live(
            tag_webid_map=tag_webid_map,
            start_time_str=start_str,
            end_time_str=end_str,
            interval="10s",
        )

        if not batch_series or getattr(client, "last_batch_network_error", False):
            print(f"  WARNING: Network error or empty response on Event {ev_id}. Retrying once after 3s...")
            time.sleep(3.0)
            batch_series = client.fetch_batch_data_live(
                tag_webid_map=tag_webid_map,
                start_time_str=start_str,
                end_time_str=end_str,
                interval="10s",
            )

        ev_df = pd.DataFrame(batch_series)
        ev_df.index = pd.to_datetime(ev_df.index, utc=True)
        ev_df.index.name = "timestamp"
        ev_df = ev_df.sort_index()

        # Save individual sensor-only parquet for this event
        ev_df.to_parquet(out_file, engine="pyarrow", compression="snappy", index=True)
        dt_sec = time.time() - t0
        print(f"  -> Saved {out_file.name}: shape={ev_df.shape} in {dt_sec:.1f}s")

        # Add metadata columns for combined file
        comb_df = ev_df.copy()
        comb_df["event_id"] = ev_id
        comb_df["event_type"] = ev["type"]
        comb_df["event_label"] = ev["label"]
        comb_df["event_timestamp_utc"] = ev["ts"]
        comb_df["rel_seconds_to_trip"] = (comb_df.index - t_ev).total_seconds()
        all_dfs.append(comb_df)

    if all_dfs:
        master_df = pd.concat(all_dfs, axis=0)
        master_df.to_parquet(COMBINED_PATH, engine="pyarrow", compression="snappy", index=True)
        total_sec = time.time() - t_all_start
        print(f"\n==================================================================")
        print(f"COMPLETED ALL 13 EVENTS AT 10s INTERVAL IN {total_sec:.1f}s!")
        print(f"Combined file saved to: {COMBINED_PATH} (Shape: {master_df.shape})")
        print(f"Individual files saved in: {OUT_DIR}")
        print(f"==================================================================")


if __name__ == "__main__":
    main()
