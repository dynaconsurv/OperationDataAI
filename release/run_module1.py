#!/usr/bin/env python3
"""Standalone Runner for Module 1 Portable Release.

Extracts hourly telemetry from PI Web API for the preconfigured equipment taglist,
computes statistical operating limits (Normal, HH, H, L, LL), and persists them into
the SQL table with change-detection deduplication.

Usage:
    python run_module1.py                      # Run default 6-month hourly ingestion
    python run_module1.py --mock               # Run offline with synthetic data
    python run_module1.py --equipment GT-2420A # Target specific equipment
    python run_module1.py --months 6           # Custom duration in months
    python run_module1.py --interval 1h        # Custom sample interval
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

# Ensure release base directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config_manager import ConfigManager
from src.module1_pi_ingestion.pipeline import Module1Pipeline
from src.utils.logger import get_logger

logger = get_logger("Module1Runner")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PTTEP Module 1: Hourly PI Ingestion, Operating Limits & SQL Persistence",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--equipment",
        type=str,
        default=None,
        help="Target equipment identifier (e.g. 'GT-2420A', 'all'). Defaults to config.json target_equipment.",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=None,
        help="Historical duration in months (e.g. 6). Defaults to config.json duration_months.",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default=None,
        help="Sampling interval (e.g. '1h', '15m'). Defaults to config.json sample_interval.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force simulation mode (offline synthetic data generation).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Force live PI Web API connection.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not resume from existing checkpoint; perform a fresh ingestion.",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Custom start datetime in ISO or 'YYYY-MM-DD HH:MM' format.",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="Custom end datetime in ISO or 'YYYY-MM-DD HH:MM' format.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cm = ConfigManager()
    cfg = cm.load_config()

    # CLI Overrides
    target_eq = args.equipment or cfg.get("target_equipment", "GT-2420A")
    interval = args.interval or cfg.get("pi_web_api", {}).get("sample_interval", "1h")
    months = args.months or cfg.get("pi_web_api", {}).get("duration_months", 6)

    force_mock = None
    if args.mock:
        force_mock = True
    elif args.live:
        force_mock = False

    custom_start = None
    if args.start:
        try:
            custom_start = dt.datetime.fromisoformat(args.start)
        except ValueError:
            custom_start = dt.datetime.strptime(args.start, "%Y-%m-%d %H:%M")

    custom_end = None
    if args.end:
        try:
            custom_end = dt.datetime.fromisoformat(args.end)
        except ValueError:
            custom_end = dt.datetime.strptime(args.end, "%Y-%m-%d %H:%M")

    print("=" * 70)
    print("  PTTEP PI TELEMETRY INGESTION & OPERATING LIMITS ENGINE (MODULE 1)")
    print("=" * 70)
    print(f"  Target Equipment:     {target_eq}")
    print(f"  Sampling Interval:    {interval}")
    print(f"  Duration:             {months} months")
    print(f"  Execution Mode:       {'Mock (Simulation)' if (force_mock is True or (force_mock is None and cfg.get('pi_web_api', {}).get('mock_mode'))) else 'Live PI Web API'}")
    print(f"  Database Target:      {cfg.get('database', {}).get('engine', 'mssql').upper()} ({cfg.get('database', {}).get('database', 'PTTEP_AI')})")
    print(f"  Resume Checkpoint:    {not args.no_resume}")
    print("=" * 70)

    pipeline = Module1Pipeline(config_manager=cm, equipment_id=target_eq)

    def print_progress(fraction: float, message: str, details: dict):
        pct = int(fraction * 100)
        print(f"[{pct:3d}%] {message}")

    result = pipeline.run(
        mode="6month",
        force_mock=force_mock,
        custom_start=custom_start,
        custom_end=custom_end,
        custom_interval=interval,
        resume=not args.no_resume,
        progress_callback=print_progress,
    )

    print("\n" + "=" * 70)
    print(f"  PIPELINE EXECUTION STATUS: {result.get('status', 'Unknown').upper()}")
    print("=" * 70)
    print(f"  Duration:             {result.get('duration_seconds')} seconds")
    print(f"  Time Range:           {result.get('time_range')}")
    print(f"  Sensors Ingested:     {result.get('tags_successful')} / {result.get('tags_requested')}")
    print(f"  Telemetry Points:     {result.get('data_points_collected', 0):,}")
    print(f"  Limits Calculated:    {result.get('limits_calculated', 0)}")
    print(f"  SQL Inserted:         {result.get('sql_inserted', 0)} (new or updated thresholds)")
    print(f"  SQL Skipped:          {result.get('sql_skipped', 0)} (unchanged matching records)")
    print(f"  Backend Database:     {result.get('backend_db')}")
    print("=" * 70)

    if result.get("status") == "Success":
        print(">> Ingestion and operating limits synchronization completed successfully.")
        return 0
    else:
        print(f">> Ingestion failed: {result.get('last_error')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
