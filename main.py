"""CLI Entry Point for PTTEP GT-2420A PI Analytics Application.
Provides command-line commands for headless pipeline execution, correlation analysis,
and database inspection.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config_manager import ConfigManager
from src.module1_pi_ingestion.pipeline import Module1Pipeline
from src.module1_pi_ingestion.limits_calculator import LimitsCalculator
from src.module1_pi_ingestion.sql_storage import SQLStorageManager
from src.module2_correlation.correlation_engine import CorrelationEngine
from src.module2_correlation.clustering import SensorClusterer
from src.module3_prediction.correlation_digital_twin import CorrelationDigitalTwin

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


def cmd_calc_limits(args: argparse.Namespace) -> None:
    """Compute Operating Limits directly from cached telemetry Parquet and sync to SQL."""
    import time
    cm = ConfigManager()
    cfg = cm.load_config()
    data_path = cm.get_telemetry_path()
    if not data_path.exists():
        console.print(f"[bold red]Error:[/bold red] Telemetry data not found at {data_path}. Please run ingestion first.")
        return

    console.print(f"[bold green]Reading cached telemetry from {data_path}...[/bold green]")
    t0 = time.time()
    df = None
    for attempt in range(3):
        try:
            if str(data_path).lower().endswith(".parquet"):
                df = pd.read_parquet(data_path, engine="pyarrow")
            else:
                import pickle
                with open(data_path, "rb") as f:
                    df = pickle.load(f)
            break
        except (PermissionError, IOError):
            time.sleep(0.5)

    if df is None or df.empty:
        console.print("[bold red]Failed to read telemetry or dataset is empty.[/bold red]")
        return

    console.print(f"Loaded [bold cyan]{len(df):,} timestamps[/bold cyan] across [bold cyan]{len(df.columns)} sensors[/bold cyan] ({time.time() - t0:.2f}s).")
    console.print(f"Available range in cache: [bold yellow]{df.index.min()} to {df.index.max()}[/bold yellow]")

    # Filter by timeframe if specified
    if getattr(args, "days", None):
        max_ts = df.index.max()
        cutoff_ts = max_ts - dt.timedelta(days=args.days)
        df = df[df.index >= cutoff_ts]
        console.print(f"Filtered to last [bold cyan]{args.days} days[/bold cyan]: {cutoff_ts} to {max_ts} ({len(df):,} rows)")

    if getattr(args, "start", None):
        try:
            start_ts = dt.datetime.fromisoformat(args.start)
            if df.index.tz is not None and start_ts.tzinfo is None:
                start_ts = start_ts.replace(tzinfo=dt.timezone.utc)
            df = df[df.index >= start_ts]
            console.print(f"Applied start filter >= [bold cyan]{start_ts}[/bold cyan]")
        except ValueError:
            console.print(f"[bold red]Invalid start timestamp format: {args.start}. Use 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'.[/bold red]")
            return

    if getattr(args, "end", None):
        try:
            end_ts = dt.datetime.fromisoformat(args.end)
            if df.index.tz is not None and end_ts.tzinfo is None:
                end_ts = end_ts.replace(tzinfo=dt.timezone.utc)
            df = df[df.index <= end_ts]
            console.print(f"Applied end filter <= [bold cyan]{end_ts}[/bold cyan]")
        except ValueError:
            console.print(f"[bold red]Invalid end timestamp format: {args.end}. Use 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'.[/bold red]")
            return

    if df.empty:
        console.print("[bold red]No telemetry points found within the specified time frame filter.[/bold red]")
        return

    console.print(f"Computing limits on active window: [bold green]{df.index.min()} to {df.index.max()}[/bold green] ({len(df):,} rows)")

    if getattr(args, "method", None):
        cfg["operating_limits"] = cfg.get("operating_limits", {})
        cfg["operating_limits"]["method"] = args.method

    calc = LimitsCalculator(config=cfg)
    console.print(f"[bold green]Calculating Operating Limits using method='{calc.method}'...[/bold green]")
    t1 = time.time()
    records, summary_df = calc.compute_all_limits(df)
    console.print(f"Computed [bold cyan]{len(records)} limits[/bold cyan] across {len(summary_df)} sensors ({time.time() - t1:.2f}s).")

    # Save summary CSV
    limits_csv_rel = cfg.get("storage", {}).get("limits_csv_file", "data/operating_limits.csv")
    limits_csv_path = cm.resolve_path(limits_csv_rel)
    limits_csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(limits_csv_path, index=False)

    # Sync to SQL
    sql_storage = SQLStorageManager(config=cfg)
    console.print(f"[bold green]Synchronizing into {sql_storage.active_backend} database (`{sql_storage.table_name}`)...[/bold green]")
    inserted, skipped = sql_storage.save_limits(records)

    console.print(f"[bold green][OK] Limits Synchronization Complete![/bold green] Inserted: [bold cyan]{inserted}[/bold cyan] | Skipped (Unchanged): [bold yellow]{skipped}[/bold yellow]")


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
    console.print(f"Full correlation matrix saved to: [underline]{corr_csv_path}[/underline]\n")

    if not getattr(args, "no_explain", False):
        print_correlation_explanation(method=args.method, top_pairs=top_pairs, filter_mode=args.filter)


def print_correlation_explanation(method: str, top_pairs: pd.DataFrame, filter_mode: str) -> None:
    """Print an intuitive, operator-friendly guide explaining how to interpret the correlation results."""
    method_name = method.title()
    method_desc = (
        "measures the direct linear relationship (do sensors move together in fixed proportion?)"
        if method.lower() == "pearson"
        else "measures monotonic relationship (do sensors move together regardless of linearity?)"
    )

    explanation_lines = [
        f"[bold cyan][?] WHAT IS {method.upper()} CORRELATION (EXPLAINED IN PLAIN ENGLISH)?[/bold cyan]",
        f"You don't need a statistics background to understand this! The [bold]{method_name}[/bold] method {method_desc}.",
        "Think of correlation as measuring whether two sensors [bold]dance together in lockstep[/bold] over time:",
        "",
        "  * [bold green]+1.0000 (Perfect Positive)[/bold green] : When Sensor 1 goes UP, Sensor 2 goes UP at the exact same time in lockstep.",
        "  * [dim] 0.0000 (No Correlation)[/dim]     : Sensor 1 and Sensor 2 move independently (no relationship at all).",
        "  * [bold red]-1.0000 (Perfect Inverse)[/bold red]  : When Sensor 1 goes UP, Sensor 2 goes DOWN (move in opposite directions).",
        "",
        "[bold yellow][*] HOW TO READ THE CORRELATION VALUE (BENCHMARK GUIDE):[/bold yellow]",
        "  * [bold green]+0.80 to +1.00[/bold green] : [bold]Very Strong Positive[/bold] (Redundant sensors or sensors in the exact same thermal/pressure zone)",
        "  * [green]+0.50 to +0.79[/green] : [bold]Moderate / Strong[/bold] (Sensors that follow the same general operational turbine load)",
        "  * [yellow]+0.20 to +0.49[/yellow] : [bold]Weak Connection[/bold] (Minor shared influence)",
        "  * [dim]-0.19 to +0.19[/dim] : [bold]Uncorrelated / Independent[/bold] (Noise or unrelated physical systems)",
        "  * [red]-0.50 to -0.79[/red] : [bold]Moderate Inverse[/bold] (e.g., flow rate vs pressure drop across a filter)",
        "  * [bold red]-0.80 to -1.00[/bold red] : [bold]Very Strong Inverse[/bold] (e.g., cooling valve opening % vs downstream temperature)",
        "",
        "[bold cyan][!] ENGINEERING INTERPRETATION FOR GT-2420A (WHY THIS MATTERS):[/bold cyan]"
    ]

    # Specific insights based on sensors present in the top pairs table
    sensors_str = " ".join(top_pairs["Sensor_1"].tolist() + top_pairs["Sensor_2"].tolist()).lower() if not top_pairs.empty else ""

    insight_idx = 1
    if "exhaust temperature" in sensors_str:
        explanation_lines.extend([
            f"  {insight_idx}. [bold]Exhaust Thermocouples Cluster (+1.0000)[/bold]:",
            "     Sensors such as 'Exhaust Temperature 4, 5, 6, 7, 8, 9' form the circumferential exhaust ring.",
            "     Because gas turbine combustion cans fire simultaneously, all exhaust thermocouples naturally rise and",
            "     fall together with MW turbine load. This confirms normal symmetrical combustion.",
            "     [italic yellow][EARLY WARNING][/italic yellow] If one thermocouple suddenly drops to +0.20 while others remain at +0.99,",
            "     that indicates combustion flame-out, nozzle clogging, or a failing thermocouple probe before a trip occurs!"
        ])
        insight_idx += 1

    if "axial displacement" in sensors_str or "rotor" in sensors_str:
        explanation_lines.extend([
            f"  {insight_idx}. [bold]Rotor Axial Displacement Probes (+1.0000)[/bold]:",
            "     HP and LP Rotor Axial Displacement Proximity Probes are paired redundant sensors measuring shaft position.",
            "     Near-perfect (+1.0000) correlation proves both dual-channel probes agree on rotor mechanical position.",
            "     [italic yellow][HEALTH CHECK][/italic yellow] A divergence between redundant probes flags loose mounting or calibration drift."
        ])
        insight_idx += 1

    if "fuel gas" in sensors_str or "compressor discharge" in sensors_str or "control oil" in sensors_str:
        explanation_lines.extend([
            f"  {insight_idx}. [bold]Thermodynamic & Hydraulic Cross-Coupling (+0.999)[/bold]:",
            "     Fuel Gas Pressure, Compressor Discharge Pressure (PCD), and Control Oil Header Pressure track together.",
            "     As turbine load ramps, hydraulic control oil modulates fuel gas valves, and higher combustion drives PCD.",
            "     [italic yellow][PROCESS COUPLING][/italic yellow] Proves core engine thermodynamic loop and governor control are behaving synchronously."
        ])
        insight_idx += 1

    if insight_idx == 1:
        explanation_lines.extend([
            "  1. [bold]Physical Process Coupling[/bold]:",
            "     Sensors with correlation > 0.80 indicate strong aerodynamic, thermal, or mechanical linkages across the unit.",
            "     Pairs with correlation near 0.00 operate independently, while negative values indicate opposing control responses."
        ])

    explanation_lines.extend([
        "",
        "[bold magenta][>] NEXT STEPS / ADVANCED FILTERS:[/bold magenta]",
        "  * Find cross-system coupling:  [bold white]python main.py run-module2 --filter cross_subsystem --top-n 15[/bold white]",
        "  * Find opposing / inverse trends: [bold white]python main.py run-module2 --filter negative --top-n 15[/bold white]",
        "  * Capture non-linear trends:      [bold white]python main.py run-module2 --method spearman --top-n 15[/bold white]"
    ])

    guide_box = "\n".join(explanation_lines)
    console.print(Panel(guide_box, title="[bold white]Operator Guide: How to Read & Interpret Module 2 Results[/bold white]", border_style="cyan", padding=(1, 2)))


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

    if len(pivot_df) > args.limit:
        console.print(f"[dim]Showing first {args.limit} of {len(pivot_df)} sensors. Use --limit to show more.[/dim]")


def render_early_warning_card(alert: Dict[str, Any]) -> None:
    """Render a structured Early Warning Advisory card with rich styling."""
    culprit = alert["culprit_sensor"]
    witnesses = alert.get("supporting_witness_sensors", [])

    is_anom = alert.get("is_anomaly", False)
    border_color = "red" if is_anom else "green"
    status_label = f"[bold red]{alert['severity']} (ANOMALY DETECTED)[/bold red]" if is_anom else f"[bold green]{alert['severity']} (NORMAL PROFILE)[/bold green]"

    lines = [
        f"[bold white]ASSET ID:[/bold white] {alert['asset_id']}  |  [bold white]TIMESTAMP:[/bold white] {alert['timestamp']}  |  [bold white]STATUS:[/bold white] {status_label}",
        f"[bold white]TURBINE HEALTH SCORE:[/bold white] {alert['health_score']}/100  |  [bold white]ANOMALY SCORE (SPE):[/bold white] {alert['composite_anomaly_score']} (Threshold: {alert['system_threshold']})",
        "",
        "[bold cyan]1. WHAT IS ABOUT TO HAPPEN (PREDICTED INCIDENT):[/bold cyan]",
        f"   * Predicted Incident:   [bold yellow]{alert['predicted_incident']}[/bold yellow]",
        f"   * Estimated Lead Time:  [bold cyan]~{alert['estimated_lead_time_hours']} Hours advance notice[/bold cyan]",
        f"   * Root Cause Verdict:   {alert['root_cause_diagnosis']}",
        "",
        "[bold cyan]2. WHICH SENSORS PROVE THE DATA (THE FAILURE SIGNAL & EVIDENCE):[/bold cyan]",
        f"   [bold yellow]PRIMARY CULPRIT SENSOR:[/bold yellow] [bold white]{culprit['tag_name']}[/bold white] (Subsystem: {culprit['subsystem']})",
        f"     - Actual Live Telemetry:       [bold yellow]{culprit['actual_value']}[/bold yellow]",
        f"     - Expected Digital Twin Value: [cyan]{culprit['expected_digital_twin_value']}[/cyan]",
        f"     - Residual Error Deviation:    [bold red]{culprit['residual_deviation']:+.2f}[/bold red] ({culprit['z_score']:+.2f} sigma deviation)",
        f"     - Contribution Index (SCI):    [bold magenta]{culprit['contribution_index_pct']:.1f}%[/bold magenta] of total turbine anomaly error",
        "",
        "   [bold yellow]SUPPORTING WITNESS SENSORS (PHYSICAL CORRELATION PEERS):[/bold yellow]",
    ]

    for w in witnesses[:5]:
        status_col = "green" if w["status"] == "NORMAL" else "red"
        lines.append(
            f"     * {w['tag_name'][:28]:<28} Live: {w['actual']:>7.2f} | Expected: {w['expected']:>7.2f} | Residual: {w['residual']:>+6.2f} [{status_col}]{w['status']}[/{status_col}]"
        )

    lines.extend([
        "",
        "[bold cyan]3. PRESCRIBED OPERATOR ACTIONS:[/bold cyan]",
    ])
    for idx, act in enumerate(alert.get("prescribed_operator_actions", []), 1):
        lines.append(f"   {idx}. {act}")

    box_text = "\n".join(lines)
    card_title = f"[bold white]PREDICTIVE EARLY WARNING ADVISORY: {alert['alert_id']}[/bold white]"
    console.print(Panel(box_text, title=card_title, border_style=border_color, padding=(1, 2)))


def cmd_run_module3(args: argparse.Namespace) -> None:
    """Execute Module 3: CorrelationDigitalTwin predictive anomaly engine and generate Early Warning alerts."""
    import json
    cm = ConfigManager()
    cfg = cm.load_config()
    sensors = cm.load_sensors()

    data_path = cm.get_telemetry_path()
    if not data_path.exists():
        console.print(f"[bold red]Error:[/bold red] Telemetry data not found at {data_path}. Please run Module 1 first.")
        sys.exit(1)

    if str(data_path).lower().endswith(".parquet"):
        df = pd.read_parquet(data_path, engine="pyarrow")
    else:
        import pickle
        with open(data_path, "rb") as f:
            df = pickle.load(f)

    corr_csv_rel = cfg.get("storage", {}).get("correlation_file", "data/correlation_matrix.csv")
    corr_csv_path = cm.resolve_path(corr_csv_rel)
    corr_df = None
    if corr_csv_path.exists():
        corr_df = pd.read_csv(corr_csv_path, index_col=0)

    load_model_path = getattr(args, "load_model", None)
    save_model_path = getattr(args, "save_model", None)

    if load_model_path and Path(load_model_path).exists():
        console.print(f"[bold green]Loading pre-calibrated CorrelationDigitalTwin from {load_model_path}...[/bold green]")
        twin = CorrelationDigitalTwin.load_model(load_model_path)
        if sensors and not twin.tag_name_map:
            twin._build_sensor_lookup_maps(sensors)
    else:
        console.print(f"[bold green]Calibrating CorrelationDigitalTwin across {df.shape[1]} sensors ({len(df):,} samples)...[/bold green]")
        twin = CorrelationDigitalTwin(
            top_n_peers=args.top_peers,
            min_correlation=args.min_corr,
            sensor_catalog=sensors,
        )
        twin.fit(df, correlation_matrix=corr_df)
        if save_model_path:
            twin.save_model(save_model_path)
            console.print(f"[bold cyan]Calibrated model successfully saved to {save_model_path}[/bold cyan]")

    # Identify active operational window if tail is in outage/shutdown
    numeric_df = df.select_dtypes(include=[np.number])
    running_mask = (numeric_df > 10.0).sum(axis=1) > (len(numeric_df.columns) * 0.3)
    if running_mask.any():
        last_running_ts = df[running_mask].index[-1]
        if (df.index[-1] - last_running_ts).total_seconds() > 3600 * 12:
            console.print(f"[dim]Latest timestamps are in unit outage/standby. Evaluating active operational window up to {last_running_ts}...[/dim]")
            eval_window = df.loc[:last_running_ts].tail(args.lookback).copy()
        else:
            eval_window = df.tail(args.lookback).copy()
    else:
        eval_window = df.tail(args.lookback).copy()

    # Optional synthetic fault injection for demonstration
    if args.inject_fault == "combustion":
        tc_cols = [c for c in eval_window.columns if "exhaust temperature 8" in c.lower()]
        if tc_cols:
            target_col = tc_cols[0]
            console.print(f"[bold yellow][TEST INJECTION] Simulating burner nozzle coking fault on '{target_col.split(chr(92))[-1]}'...[/bold yellow]")
            vals = eval_window[target_col].to_numpy().copy()
            vals[-10:] -= np.linspace(15, 65, 10)
            eval_window[target_col] = vals
    elif args.inject_fault == "bearing":
        b_cols = [c for c in eval_window.columns if "journal bearing" in c.lower() and "temperature" in c.lower()]
        if b_cols:
            target_col = b_cols[0]
            console.print(f"[bold yellow][TEST INJECTION] Simulating bearing babbitt heating fault on '{target_col.split(chr(92))[-1]}'...[/bold yellow]")
            vals = eval_window[target_col].to_numpy().copy()
            vals[-10:] += np.linspace(8, 25, 10)
            eval_window[target_col] = vals

    console.print(f"[bold green]Evaluating telemetry window ({len(eval_window)} timestamps: {eval_window.index.min()} to {eval_window.index.max()})...[/bold green]")
    scored = twin.score_telemetry(eval_window)

    anomaly_count = int(scored["is_anomaly"].sum())
    console.print(f"Scored {len(scored)} timestamps | [bold cyan]Anomalies Flagged: {anomaly_count}[/bold cyan] (System Threshold: {twin.system_anomaly_threshold:.2f})")

    target_ts = getattr(args, "timestamp", None)
    if target_ts is None:
        if anomaly_count > 0:
            target_ts = scored[scored["is_anomaly"]].index[-1]
        else:
            target_ts = eval_window.index[-1]

    alert = twin.diagnose_anomaly(eval_window, timestamp=target_ts)

    save_alert_path = getattr(args, "save_alert", None)
    if save_alert_path:
        out_p = Path(save_alert_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(alert, f, indent=2)
        console.print(f"[bold cyan]Advisory alert saved to {save_alert_path}[/bold cyan]")

    # Persist advisory historically into SQL database
    try:
        from src.module1_pi_ingestion.sql_storage import SQLStorageManager
        sql_mgr = SQLStorageManager(cfg)
        sql_mgr.save_predictive_advisory(alert)
    except Exception as e:
        pass

    if args.json:
        console.print_json(data=alert)
    else:
        render_early_warning_card(alert)


def cmd_serve_api(args: argparse.Namespace) -> None:
    """Launch the FastAPI REST service for PI Vision integration using Uvicorn."""
    import uvicorn
    console.print(f"[bold green]Starting PTTEP GT-2420A Predictive Anomaly API on {args.host}:{args.port}...[/bold green]")
    console.print(f"[dim]PI Vision endpoint: http://{args.host}:{args.port}/api/v1/advisory/latest[/dim]")
    console.print(f"[dim]Swagger Docs:       http://{args.host}:{args.port}/docs[/dim]")
    uvicorn.run("src.api.app:app", host=args.host, port=args.port, reload=args.reload)


def cmd_backfill_module3(args: argparse.Namespace) -> None:
    """Backfill past historical predictions across 1 year into SQL database."""
    import time
    cm = ConfigManager()
    cfg = cm.load_config()
    sensors = cm.load_sensors()

    data_path = cm.get_telemetry_path()
    if not data_path.exists():
        console.print(f"[bold red]Error:[/bold red] Telemetry data not found at {data_path}. Please run Module 1 first.")
        sys.exit(1)

    console.print(f"[bold green]Loading historical telemetry from {data_path}...[/bold green]")
    if str(data_path).lower().endswith(".parquet"):
        df = pd.read_parquet(data_path)
    else:
        import pickle
        with open(data_path, "rb") as f:
            df = pickle.load(f)

    # Filter to requested historical window
    if args.days:
        cutoff = df.index.max() - pd.Timedelta(days=args.days)
        df = df[df.index >= cutoff]

    console.print(f"Loaded {len(df):,} raw timestamps spanning {df.index.min()} to {df.index.max()}.")

    # Resample to evaluation interval (e.g. '1h' or '30m')
    numeric_df = df.select_dtypes(include=[np.number])
    console.print(f"[bold green]Resampling telemetry to interval '{args.interval}' for historical evaluation...[/bold green]")
    resampled_df = numeric_df.resample(args.interval).mean().dropna(how="all")
    console.print(f"Generated {len(resampled_df):,} discrete historical timestamps to score.")

    # Load pre-calibrated CorrelationDigitalTwin
    model_path = args.load_model or "models/gt2420a_digital_twin.pkl"
    if Path(model_path).exists():
        console.print(f"[bold green]Loading pre-calibrated CorrelationDigitalTwin from {model_path}...[/bold green]")
        twin = CorrelationDigitalTwin.load_model(model_path)
        if sensors and not twin.tag_name_map:
            twin._build_sensor_lookup_maps(sensors)
    else:
        console.print("[bold yellow]Calibrating digital twin from baseline telemetry...[/bold yellow]")
        corr_csv = cm.resolve_path("data/correlation_matrix.csv")
        corr_df = pd.read_csv(corr_csv, index_col=0) if corr_csv.exists() else None
        twin = CorrelationDigitalTwin(top_n_peers=5, min_correlation=0.65, sensor_catalog=sensors)
        twin.fit(df, correlation_matrix=corr_df)
        twin.save_model("models/gt2420a_digital_twin.pkl")

    # Vectorized scoring across the entire historical window
    t0 = time.time()
    console.print(f"[bold green]Scoring {len(resampled_df):,} timestamps through 158 sensor digital twins...[/bold green]")
    scored = twin.score_telemetry(resampled_df)
    score_elapsed = time.time() - t0
    console.print(f"[bold cyan]Scoring completed in {score_elapsed:.2f}s![/bold cyan]")

    anomalies_count = int(scored["is_anomaly"].sum())
    console.print(f"Total timestamps: {len(scored):,} | Anomalies detected: [bold red]{anomalies_count}[/bold red] (Threshold: {twin.system_anomaly_threshold:.2f})")

    # Generate structured advisories
    console.print("[bold green]Generating structured advisories for database archiving...[/bold green]")
    advisories = []
    for ts in resampled_df.index:
        alert = twin.diagnose_anomaly(resampled_df, timestamp=ts)
        advisories.append(alert)

    # Bulk insert into SQL database
    from src.module1_pi_ingestion.sql_storage import SQLStorageManager
    sql_mgr = SQLStorageManager(cfg)
    console.print(f"[bold green]Bulk inserting {len(advisories):,} historical advisories into SQL ({sql_mgr.active_backend})...[/bold green]")
    inserted = sql_mgr.bulk_save_predictive_advisories(advisories, batch_size=args.batch_size)
    console.print(f"[bold green]SUCCESS: Successfully archived {inserted:,} historical advisories into SQL table 'predictive_advisories'![/bold green]")



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
    p_m2.add_argument("--no-explain", action="store_true", help="Suppress the operator explanation guide box")

    # calc-limits
    p_cl = subparsers.add_parser("calc-limits", help="Compute Operating Limits directly from cached telemetry Parquet and sync to SQL")
    p_cl.add_argument("--start", type=str, default=None, help="Custom start timestamp (YYYY-MM-DD or YYYY-MM-DD HH:MM)")
    p_cl.add_argument("--end", type=str, default=None, help="Custom end timestamp (YYYY-MM-DD or YYYY-MM-DD HH:MM)")
    p_cl.add_argument("--days", type=int, default=None, help="Compute limits using only the last N days of telemetry")
    p_cl.add_argument("--method", choices=["percentile", "sigma"], default=None, help="Statistical method (percentile or sigma)")

    # run-module3
    p_m3 = subparsers.add_parser("run-module3", help="Execute Module 3 (CorrelationDigitalTwin Predictive Anomaly Engine)")
    p_m3.add_argument("--lookback", type=int, default=48, help="Number of recent telemetry timestamps to score")
    p_m3.add_argument("--top-peers", type=int, default=5, help="Number of correlated peers per digital twin")
    p_m3.add_argument("--min-corr", type=float, default=0.65, help="Minimum absolute correlation to accept a peer")
    p_m3.add_argument("--inject-fault", choices=["none", "combustion", "bearing"], default="none", help="Inject synthetic fault to test early warning detection")
    p_m3.add_argument("--timestamp", type=str, default=None, help="Specific timestamp to diagnose (default: latest timestamp)")
    p_m3.add_argument("--save-model", type=str, default=None, help="Save calibrated digital twin model pickle to path")
    p_m3.add_argument("--load-model", type=str, default=None, help="Load pre-calibrated digital twin model pickle from path")
    p_m3.add_argument("--save-alert", type=str, default=None, help="Save generated advisory alert JSON to path")
    p_m3.add_argument("--json", action="store_true", help="Print raw alert JSON object")

    # show-limits
    p_lim = subparsers.add_parser("show-limits", help="Query operating limits from SQL")
    p_lim.add_argument("--filter", type=str, default="", help="Filter sensors by substring")
    p_lim.add_argument("--limit", type=int, default=30, help="Max rows to display")

    # serve-api
    p_api = subparsers.add_parser("serve-api", help="Launch FastAPI REST service for PI Vision integration")
    p_api.add_argument("--host", type=str, default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    p_api.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    p_api.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    # backfill-module3
    p_bf = subparsers.add_parser("backfill-module3", help="Backfill historical predictive advisories into SQL across past telemetry")
    p_bf.add_argument("--days", type=int, default=365, help="Number of historical days to backfill (default: 365 for 1 full year)")
    p_bf.add_argument("--interval", type=str, default="1h", help="Historical evaluation sampling interval (e.g. 1h, 30m, 15m; default: 1h)")
    p_bf.add_argument("--load-model", type=str, default=None, help="Path to pre-calibrated digital twin model (default: models/gt2420a_digital_twin.pkl)")
    p_bf.add_argument("--batch-size", type=int, default=1000, help="SQL bulk insertion batch size (default: 1000)")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "run-module1":
        cmd_run_module1(args)
    elif args.command == "calc-limits":
        cmd_calc_limits(args)
    elif args.command == "run-module2":
        cmd_run_module2(args)
    elif args.command == "run-module3":
        cmd_run_module3(args)
    elif args.command == "backfill-module3":
        cmd_backfill_module3(args)
    elif args.command == "serve-api":
        cmd_serve_api(args)
    elif args.command == "show-limits":
        cmd_show_limits(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
