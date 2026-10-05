"""CLI Entry Point for PTTEP GT-2420A PI Analytics Application.
Provides command-line commands for headless pipeline execution, correlation analysis,
and database inspection.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
import pandas as pd
from rich.console import Console
from rich.table import Table

from src.config_manager import ConfigManager
from src.module1_pi_ingestion.pipeline import Module1Pipeline
from src.module1_pi_ingestion.sql_storage import SQLStorageManager
from src.module2_correlation.correlation_engine import CorrelationEngine
from src.module2_correlation.clustering import SensorClusterer

console = Console()


def cmd_status(args: argparse.Namespace) -> None:
    """Display last run status, database counts, and system configuration."""
    cm = ConfigManager()
    cfg = cm.load_config()
    meta = cm.load_last_run_meta()

    table = Table(title="PTTEP GT-2420A Analytics System Status", show_header=True, header_style="bold cyan")
    table.add_column("Parameter", style="bold")
    table.add_column("Value")

    table.add_row("Application", cfg.get("app_name", "N/A"))
    table.add_row("PI Web API URL", cfg.get("pi_web_api", {}).get("url", "N/A"))
    table.add_row("PI AF Database", cfg.get("pi_web_api", {}).get("af_db", "N/A"))
    table.add_row("PI Web API User", cfg.get("pi_web_api", {}).get("username", "N/A"))
    table.add_row("PI Web API Mode", "MOCK (Safe Development Mode)" if cfg.get("pi_web_api", {}).get("mock_mode") else "LIVE PI SERVER")
    table.add_row("Database Engine", cfg.get("database", {}).get("engine", "N/A"))
    table.add_row("Database Name", cfg.get("database", {}).get("database", "N/A"))
    table.add_row("Database User", cfg.get("database", {}).get("user", "N/A"))
    table.add_row("Database Table", cfg.get("database", {}).get("table_name", "N/A"))
    table.add_row("Active DB Backend", meta.get("backend_db", "N/A"))
    table.add_row("Last Pull Timestamp", str(meta.get("last_pull_timestamp", "Never")))
    table.add_row("Time Taken (Duration)", f"{meta.get('duration_seconds', 0.0)} seconds")
    table.add_row("Last Ingestion Mode", str(meta.get("pull_mode", "N/A")))
    table.add_row("Time Range Covered", str(meta.get("time_range", "N/A")))
    table.add_row("Tags Requested / Successful", f"{meta.get('tags_requested', 0)} / {meta.get('tags_successful', 0)}")
    table.add_row("Total Data Points", f"{meta.get('data_points_collected', 0):,}")
    table.add_row("Operating Limits Calculated", f"{meta.get('limits_calculated', 0):,}")
    table.add_row("SQL Records Inserted", str(meta.get("sql_inserted", 0)))
    table.add_row("SQL Records Skipped (Unchanged)", str(meta.get("sql_skipped", 0)))
    table.add_row("Last Run Status", f"[bold green]{meta.get('status', 'Ready')}[/bold green]" if meta.get("status") == "Success" else f"[bold yellow]{meta.get('status', 'Ready')}[/bold yellow]")

    console.print(table)


def cmd_run_module1(args: argparse.Namespace) -> None:
    """Run Module 1 pipeline (pull telemetry, calculate limits, persist to SQL)."""
    cm = ConfigManager()
    force_mock = None
    if args.mock:
        force_mock = True
    elif args.live:
        force_mock = False

    custom_start = None
    if getattr(args, "start", None):
        try:
            custom_start = dt.datetime.fromisoformat(args.start)
        except ValueError:
            console.print(f"[bold red]Invalid start timestamp format: {args.start}. Use 'YYYY-MM-DD HH:MM'.[/bold red]")
            return

    custom_end = None
    if getattr(args, "end", None):
        try:
            custom_end = dt.datetime.fromisoformat(args.end)
        except ValueError:
            console.print(f"[bold red]Invalid end timestamp format: {args.end}. Use 'YYYY-MM-DD HH:MM'.[/bold red]")
            return

    interval_info = f", interval={args.interval}" if getattr(args, "interval", None) else ""
    console.print(f"[bold green]Starting Module 1 Pipeline (mode={args.mode}{interval_info}, mock={force_mock})...[/bold green]")

    def cli_progress(fraction: float, message: str, details: Optional[Dict[str, Any]] = None):
        pct = int(min(1.0, max(0.0, fraction)) * 100)
        details = details or {}
        elapsed = details.get("elapsed", 0.0)
        eta = details.get("eta")
        eta_str = f" | ETA: {eta}s" if eta is not None and eta > 0 else ""
        points = details.get("points_collected", 0)
        points_str = f" | {points:,} pts" if points > 0 else ""

        bar_len = 20
        filled = int(bar_len * fraction)
        bar = "=" * filled + (">" if filled < bar_len else "") + " " * max(0, bar_len - filled - (1 if filled < bar_len else 0))
        clean_msg = message[:35]
        sys.stdout.write(f"\r[{bar}] {pct:3d}% | {clean_msg:<35} ({elapsed:.1f}s{eta_str}{points_str})")
        sys.stdout.flush()
        if fraction >= 1.0:
            sys.stdout.write("\n")

    pipeline = Module1Pipeline(config_manager=cm)
    resume = not getattr(args, "no_resume", False)
    res = pipeline.run(
        mode=args.mode,
        force_mock=force_mock,
        custom_start=custom_start,
        custom_end=custom_end,
        custom_interval=getattr(args, "interval", None),
        resume=resume,
        progress_callback=cli_progress,
    )

    console.print(f"\n[bold cyan]Pipeline Result:[/bold cyan] {res['status']}")
    console.print(f"Time Taken: [bold yellow]{res['duration_seconds']}s[/bold yellow]")
    console.print(f"Tags Ingested: {res['tags_successful']}/{res['tags_requested']}")
    console.print(f"Limits Generated: {res['limits_calculated']}")
    console.print(f"SQL Inserted: {res['sql_inserted']} | SQL Skipped (Unchanged): {res['sql_skipped']}")


def cmd_run_module2(args: argparse.Namespace) -> None:
    """Run Module 2 correlation engine."""
    cm = ConfigManager()
    cfg = cm.load_config()
    sensors = cm.load_sensors()

    data_path = cm.get_telemetry_path()
    if not data_path.exists():
        console.print(f"[bold red]Error:[/bold red] Telemetry data not found at {data_path}. Please run Module 1 first.")
        sys.exit(1)

    if str(data_path).lower().endswith(".parquet"):
        df: pd.DataFrame = pd.read_parquet(data_path, engine="pyarrow")
    else:
        import pickle
        with open(data_path, "rb") as f:
            df: pd.DataFrame = pickle.load(f)

    console.print(f"[bold green]Computing {args.method.upper()} correlation matrix on {df.shape[1]} sensors ({df.shape[0]} timestamps)...[/bold green]")
    engine = CorrelationEngine(method=args.method)
    corr_df = engine.compute_correlation_matrix(df)

    # Save to CSV
    corr_csv_rel = cfg.get("storage", {}).get("correlation_file", "data/correlation_matrix.csv")
    corr_csv_path = cm.resolve_path(corr_csv_rel)
    engine.save_matrix_csv(corr_csv_path)

    # Extract Top Pairs
    top_pairs = engine.extract_top_pairs(top_n=args.top_n, filter_mode=args.filter, sensors_meta=sensors)

    table = Table(title=f"Top {len(top_pairs)} Sensor Correlations ({args.method.title()}, Filter={args.filter})", show_header=True)
    table.add_column("#", justify="right")
    table.add_column("Sensor 1", style="cyan")
    table.add_column("Sensor 2", style="cyan")
    table.add_column("Subsystems", style="magenta")
    table.add_column("Correlation", justify="right", style="bold green")

    for i, row in top_pairs.iterrows():
        s1 = row["Sensor_1"].split("\\")[-1]
        s2 = row["Sensor_2"].split("\\")[-1]
        subsys = f"{row['Subsystem_1']} <-> {row['Subsystem_2']}"
        val = row["Correlation"]
        color = "green" if val > 0 else "red"
        table.add_row(str(i + 1), s1, s2, subsys, f"[{color}]{val:+.4f}[/{color}]")

    console.print(table)
    console.print(f"Full correlation matrix saved to: [underline]{corr_csv_path}[/underline]")


def cmd_show_limits(args: argparse.Namespace) -> None:
    """Display current operating limits stored in the SQL database."""
    cm = ConfigManager()
    cfg = cm.load_config()
    storage = SQLStorageManager(cfg)

    pivot_df = storage.fetch_current_limits_pivot()
    if pivot_df.empty:
        console.print("[yellow]No operating limits found in the database. Please run Module 1 first.[/yellow]")
        return

    if args.filter:
        pivot_df = pivot_df[pivot_df["af_path"].str.contains(args.filter, case=False, na=False)]

    table = Table(title=f"Current Operating Limits (Total: {len(pivot_df)})", show_header=True)
    table.add_column("Sensor AF Path", style="cyan")
    for col in ["LL", "L", "Normal", "H", "HH"]:
        if col in pivot_df.columns:
            table.add_column(col, justify="right")

    for _, row in pivot_df.head(args.limit).iterrows():
        af_short = row["af_path"].replace(r"MALAYSIA\BORF\GTG\GT-2420A\\", "")
        vals = [f"{row[c]:.4f}" if pd.notna(row.get(c)) else "N/A" for c in ["LL", "L", "Normal", "H", "HH"] if c in pivot_df.columns]
        table.add_row(af_short, *vals)

    console.print(table)
    if len(pivot_df) > args.limit:
        console.print(f"[dim]Showing first {args.limit} of {len(pivot_df)} sensors. Use --limit to show more.[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="PTTEP GT-2420A PI Analytics Application")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    subparsers.add_parser("status", help="Show system status and last run metrics")

    # run-module1
    p_m1 = subparsers.add_parser("run-module1", help="Execute Module 1 (PI Ingestion, Limits, SQL Sync)")
    p_m1.add_argument("--mode", choices=["test", "full"], default="test", help="Test (1-day) or Full (12-month)")
    p_m1.add_argument("--interval", type=str, default=None, help="Sampling interval (e.g. 1m, 5m, 10m, 15m, 30m, 1h)")
    p_m1.add_argument("--start", type=str, default=None, help="Custom start timestamp (YYYY-MM-DD HH:MM)")
    p_m1.add_argument("--end", type=str, default=None, help="Custom end timestamp (YYYY-MM-DD HH:MM)")
    p_m1.add_argument("--mock", action="store_true", help="Force mock telemetry generation")
    p_m1.add_argument("--live", action="store_true", help="Force live PI Web API connection")
    p_m1.add_argument("--no-resume", action="store_true", help="Start fresh without resuming from existing checkpoint")

    # run-module2
    p_m2 = subparsers.add_parser("run-module2", help="Execute Module 2 (Correlation Analysis)")
    p_m2.add_argument("--method", choices=["pearson", "spearman"], default="pearson", help="Correlation method")
    p_m2.add_argument("--top-n", type=int, default=20, help="Number of top correlated pairs to display")
    p_m2.add_argument("--filter", choices=["all", "positive", "negative", "cross_subsystem"], default="all")

    # show-limits
    p_lim = subparsers.add_parser("show-limits", help="Query operating limits from SQL")
    p_lim.add_argument("--filter", type=str, default="", help="Filter sensors by substring")
    p_lim.add_argument("--limit", type=int, default=30, help="Max rows to display")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "run-module1":
        cmd_run_module1(args)
    elif args.command == "run-module2":
        cmd_run_module2(args)
    elif args.command == "show-limits":
        cmd_show_limits(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
