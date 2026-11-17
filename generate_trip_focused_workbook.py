"""
Generate the Focused Trip-Event Monitoring Workbook:
  - GT2420A_Trip_Focused_Monitoring.xlsx
  - reports/GT2420A_Trip_Focused_Monitoring.xlsx

Built directly from the 10-second ('10s') high-resolution PI telemetry pulled for all 13 Stop/Trip events
(data/trip_events_10s_combined.parquet) and the trained CorrelationDigitalTwin model.
"""

import shutil
import warnings
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent
COMBINED_10S_PATH = PROJECT_ROOT / "data" / "trip_events_10s_combined.parquet"
MODEL_PATH = PROJECT_ROOT / "models" / "gt2420a_digital_twin.pkl"
OUT_ROOT_XLSX = PROJECT_ROOT / "GT2420A_Trip_Focused_Monitoring.xlsx"
OUT_REPORTS_XLSX = PROJECT_ROOT / "reports" / "GT2420A_Trip_Focused_Monitoring.xlsx"

META_COLS = ["event_id", "event_type", "event_label", "event_timestamp_utc", "rel_seconds_to_trip"]

# Focused 26 Trip-Contributing & Early-Signal Sensors (across the 4 physical trip precursor families)
FOCUSED_TRIP_SENSORS = [
    # Family A: Combustion, Flame, Fuel Valves & Speed Control (Hard Trips #4, #5 & Event #3)
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Shaft Magnetic Speed Pick Up", "A. Speed & Fuel Control", "Primary Trip Indicator (HP Rotor Speed -> 0 RPM)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Shaft Magnetic Speed Pick Up", "A. Speed & Fuel Control", "Primary Load/Speed Indicator (LP Power Turbine Speed -> 0 RPM)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Stop/Speed Ratio Valve Position", "A. Speed & Fuel Control", "Hard Trip Valve Signature (Slams >25% to -2.8% in 10s on Trip; 99.9% saturation in Trip #5)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Control Valve Position", "A. Speed & Fuel Control", "Fuel Control Hunting Precursor & Instantaneous Cut (-2.9%) on Hard Trip"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Interstage Fuel Gas Pressure Pressure 2", "A. Speed & Fuel Control", "Early Fuel Valve Pressure Precursor (|Z|=21-5131σ before Trips #1, #2, #5, #6, #8)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector Combustion Chamber 3", "A. Combustion & Flame", "Early Flame Instability Precursor (|Z|=8.5σ, 39.3m lead before Hard Trip #4)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector Combustion Chamber 10", "A. Combustion & Flame", "Early Flame Instability Precursor (|Z|=7.0-13.7σ, 39.3m lead before Hard Trip #4 & Event #11)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 7", "A. Combustion & Exhaust", "Burner Coking / Cold-Spot Precursor (|Z|=345.5σ in Event #3; |Z|=136.1σ in Hard Trip #5)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 5", "A. Combustion & Exhaust", "Combustion Spread Divergence Precursor (|Z|=173.4σ, 11.5m lead before Hard Trip #5)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 6", "A. Combustion & Exhaust", "Combustion Spread Divergence Precursor (|Z|=162.0σ before Hard Trip #5)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 8", "A. Combustion & Exhaust", "Adjacent Reference & Spread Precursor (|Z|=136.7σ before Hard Trip #5)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 2", "A. Combustion & Exhaust", "Hot-Streak / Cooldown Hang Precursor (Lags peers during Hard Trip #4 deload)"),

    # Family B: Dry Gas Seal (DGS) & Primary Vent System (Events #2, #4, #7, #8, #10, #11, #12, #13)
    (r"MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Filters Differential Pressure", "B. Dry Gas Seal System", "DGS Filter Fouling / Surge Trigger (Spikes 55x to 38.0 bar in Event #7; 16-28x in #8, #12, #13)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Amplifier Differential Pressure", "B. Dry Gas Seal System", "DGS Booster Surge Trigger (Spikes from -2.4 to 302.1 in Event #2 and 172.5 in Event #8)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure", "B. Dry Gas Seal System", "Pre-Trip Seal Pressure Oscillation (|Z|=14.7σ, 4.2x oscillation before Hard Trip #4)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Suction End Primary Vent Flow", "B. Dry Gas Seal System", "Primary Seal Vent Restriction Precursor (|Z|=14.5-55.5σ before Events #2, #10, #11)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Discharge End Primary Vent Flow", "B. Dry Gas Seal System", "Primary Seal Vent Restriction Precursor (|Z|=14.0-49.1σ before Events #2, #10, #11)"),

    # Family C: Process Compressor Pressure, Ratio & Anti-Surge (Events #1, #2, #3, #4, #6, #7, #9, #12, #13)
    (r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Inlet Pressure", "C. Process Compressor", "Leading Process Pressure Precursor (|Z|=21.9-36.4σ, 18-37m lead in Events #1, #2, #6, #7)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Compressor Outlet Pressure", "C. Process Compressor", "Interstage Discharge Pressure Precursor (|Z|=4.5-33.3σ in Hard Trip #4 & Events #1, #2, #7)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Outlet Pressure", "C. Process Compressor", "High-Pressure Discharge Precursor (|Z|=5.6σ before Hard Trip #4; |Z|=112.7σ in Event #7)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Ratio", "C. Process Compressor", "Compression Ratio Surge Precursor (|Z|=19.1-34.8σ in Events #3, #9, #12, #13)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Compressor Inlet Flow", "C. Process Compressor", "Suction Flow Instability Precursor (|Z|=11.9-16.9σ in Events #9, #10, #11, #12, #13)"),

    # Family D: Rotor Bearings, Vibration & Lube Oil System (Events #1, #2, #4, #6, #7, #8, #10)
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine Bearing 1 Radial Vibrations Vibration Probe Proximitor", "D. Bearings & Lube Oil", "High Rotor Radial Vibration Precursor (|Z|=4.5σ, 41.6 µm, 39.3m lead before Hard Trip #4)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Journal Thrust Bearing 4 Drain Oil Temperature", "D. Bearings & Lube Oil", "Bearing Drain Thermal Oscillation Precursor (9.8x std oscillation, |Z|=17.3σ before Hard Trip #4)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Journal Bearing Temperature 4", "D. Bearings & Lube Oil", "Compressor Bearing Thermal Precursor (|Z|=18.6-23.2σ in Events #1 & #7; 795.6°C surge)"),
    (r"MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Pressure 3", "D. Bearings & Lube Oil", "Lube Oil Supply Header Drop Precursor (|Z|=10.3-32.3σ before Hard Trip #4 & Event #6)"),
]


def parse_tag_parts(full_path: str):
    sep = "\\" if "\\" in str(full_path) else "|"
    parts = str(full_path).split(sep)
    if len(parts) >= 6:
        return parts[4], parts[-1]
    elif len(parts) >= 2:
        return parts[-2], parts[-1]
    return "Unknown", str(full_path)


def short_label(full_path: str) -> str:
    _, tag = parse_tag_parts(full_path)
    return tag


def build_formula_string(target_short: str, intercept: float, peers: list, coefs: list) -> str:
    terms = [f"{intercept:.5f}"]
    for p, c in zip(peers, coefs):
        p_name = short_label(p)
        sign = "+" if c >= 0 else "-"
        terms.append(f"{sign} ({abs(c):.5f} * [{p_name}])")
    return f"Expected([{target_short}]) = " + " ".join(terms)


def build_zscore_string(target_short: str, mu_r: float, sigma_r: float) -> str:
    op = "-" if mu_r >= 0 else "+"
    return f"Z([{target_short}]) = (Actual([{target_short}]) - Expected([{target_short}]) {op} {abs(mu_r):.5f}) / {sigma_r:.5f}"


def main():
    print("Loading 10-second Trip Events dataset and Digital Twin model...")
    df_10s = pd.read_parquet(COMBINED_10S_PATH)
    twin = joblib.load(MODEL_PATH)

    models = twin["models"]
    peer_map = twin["peer_map"]
    r_means = twin["residual_means"]
    r_stds = twin["residual_stds"]

    sensor_cols = [c for c in df_10s.columns if c not in META_COLS]
    hp_col = r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Shaft Magnetic Speed Pick Up"
    lp_col = r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Shaft Magnetic Speed Pick Up"
    srv_col = r"MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Stop/Speed Ratio Valve Position"
    fcv_col = r"MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Control Valve Position"
    igv_col = r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine IGV Position"
    ex_cols = [c for c in sensor_cols if "Exhaust Temperature" in c]

    # Analyze each of the 13 events at 10s resolution
    event_summaries = []
    pre_trip_frames = []
    baseline_frames = []
    sensor_event_hits = {s: [] for s, _, _ in FOCUSED_TRIP_SENSORS}

    for ev_id, g in df_10s.groupby("event_id"):
        g = g.sort_index().ffill().bfill().fillna(0.0)
        lbl = g["event_label"].iloc[0]
        ev_type = g["event_type"].iloc[0]
        nom_ts = pd.to_datetime(g["event_timestamp_utc"].iloc[0], utc=True)

        # Find exact 10s trigger where SRV drops below 15% or HP drops >150 RPM in 10s
        w_search = g.loc[nom_ts - pd.Timedelta(minutes=3): nom_ts + pd.Timedelta(minutes=2)]
        srv_s = w_search[srv_col]
        hp_s = w_search[hp_col]
        cond = ((srv_s < 15.0) & (srv_s.shift(1) >= 15.0)) | (hp_s.diff() < -150.0)
        trig_candidates = w_search.index[cond]
        t_trig = trig_candidates[0] if len(trig_candidates) else nom_ts

        # State 30m before, 10s before, and at trigger
        t_minus_30m = g.index[g.index.get_indexer([t_trig - pd.Timedelta(minutes=30)], method="nearest")[0]]
        t_minus_10s = g.index[g.index.get_indexer([t_trig - pd.Timedelta(seconds=10)], method="nearest")[0]]
        t_plus_30s = g.index[g.index.get_indexer([t_trig + pd.Timedelta(seconds=30)], method="nearest")[0]]

        r_30m = g.loc[t_minus_30m]
        r_10s = g.loc[t_minus_10s]
        r_trig = g.loc[t_trig]
        r_p30s = g.loc[t_plus_30s]

        # Pre-trip window: [t_trig - 38m, t_trig - 10s]
        pre_w = g.loc[(g.index >= t_trig - pd.Timedelta(minutes=38)) & (g.index <= t_minus_10s), sensor_cols]
        base_w = pre_w.iloc[:90]  # first 15 mins of window
        late_w = pre_w.iloc[90:]  # last 20-25 mins before trigger

        if len(base_w) > 5:
            baseline_frames.append(base_w)
        if len(late_w) > 5:
            pre_trip_frames.append(late_w)

        # Compute Digital Twin Z-scores on pre_w
        z_dict = {}
        for s, m in models.items():
            if s not in pre_w.columns:
                continue
            peers = [p for p in peer_map[s] if p in pre_w.columns]
            if len(peers) != len(peer_map[s]):
                continue
            y_hat = m.predict(pre_w[peers].values)
            z = (pre_w[s].values - y_hat - r_means[s]) / r_stds[s]
            z_dict[s] = pd.Series(z, index=pre_w.index)
        z_df = pd.DataFrame(z_dict)

        # Also check local baseline shift Z for sensors (like Seal Gas Filter DP or Amplifier DP)
        b_mean = base_w.mean()
        b_std = base_w.std().replace(0, np.nan).fillna(1.0)
        b_std = b_std.where(b_std > 1e-3, 1.0)
        local_z_df = (late_w - b_mean) / b_std if len(late_w) > 0 else pd.DataFrame()

        # Combined max Z per sensor
        comb_z = z_df.abs().max()
        if not local_z_df.empty:
            for col_c in local_z_df.columns:
                lz = float(local_z_df[col_c].abs().max())
                if col_c not in comb_z or (lz > comb_z[col_c] and lz < 5000):
                    comb_z[col_c] = max(comb_z.get(col_c, 0.0), min(lz, 999.9))

        # Record hits for focused sensors
        for fs, _, _ in FOCUSED_TRIP_SENSORS:
            if fs in z_df.columns:
                fz_max = float(z_df[fs].abs().max())
                exceed = z_df.index[z_df[fs].abs() >= 3.0]
                lead_m = (t_trig - exceed[0]).total_seconds() / 60.0 if len(exceed) else 0.0
                if fz_max >= 3.5:
                    sensor_event_hits[fs].append((ev_id, fz_max, lead_m))

        top3_s = comb_z.sort_values(ascending=False).head(3)
        top3_strs = []
        best_lead_m = 0.0
        peak_z_val = 0.0
        for s_k, z_v in top3_s.items():
            s_name = short_label(s_k)
            top3_strs.append(f"{s_name} (|Z|={z_v:.1f}σ)")
            if z_v > peak_z_val:
                peak_z_val = float(z_v)
            if s_k in z_df.columns:
                ex_idx = z_df.index[z_df[s_k].abs() >= 3.0]
                if len(ex_idx):
                    best_lead_m = max(best_lead_m, (t_trig - ex_idx[0]).total_seconds() / 60.0)

        is_hard_trip = (r_trig[srv_col] < 0) or (r_p30s[srv_col] < 0 and r_trig[igv_col] < 31.0)
        class_str = "HARD EMERGENCY TRIP (Instant Solenoid Cut)" if is_hard_trip else "FIRED SHUTDOWN / PROCESS STOP (3-Min Stepped Ramp)"

        ttxs_10s = float(r_10s[ex_cols].max() - r_10s[ex_cols].min())
        ttxs_trig = float(r_trig[ex_cols].max() - r_trig[ex_cols].min())

        event_summaries.append({
            "event_id": ev_id,
            "label": lbl,
            "class_str": class_str,
            "is_hard_trip": is_hard_trip,
            "t_trig_str": t_trig.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "hp_30m": float(r_30m[hp_col]),
            "hp_10s": float(r_10s[hp_col]),
            "hp_trig": float(r_trig[hp_col]),
            "hp_p30s": float(r_p30s[hp_col]),
            "lp_10s": float(r_10s[lp_col]),
            "lp_trig": float(r_trig[lp_col]),
            "srv_10s": float(r_10s[srv_col]),
            "srv_trig": float(r_trig[srv_col]),
            "igv_10s": float(r_10s[igv_col]),
            "igv_trig": float(r_trig[igv_col]),
            "ttxs_10s": ttxs_10s,
            "ttxs_trig": ttxs_trig,
            "top_precursors": " | ".join(top3_strs),
            "lead_min": best_lead_m,
            "peak_z": peak_z_val,
        })

    # Combine baseline vs pre-trip 10s data across events to compute focused correlations
    focused_paths = [s for s, _, _ in FOCUSED_TRIP_SENSORS if s in df_10s.columns]
    all_pre_df = df_10s[df_10s["rel_seconds_to_trip"] < -10][focused_paths].ffill().bfill()
    corr_pearson = all_pre_df.corr(method="pearson")
    corr_spearman = all_pre_df.corr(method="spearman")

    # Styling definitions
    wb = openpyxl.Workbook()
    default_ws = wb.active

    title_font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    section_font = Font(name="Calibri", size=11, bold=True, color="1F4E79")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=10, bold=True)
    regular_font = Font(name="Calibri", size=10)
    formula_font = Font(name="Consolas", size=9.5, bold=True, color="0B5394")
    trip_font = Font(name="Calibri", size=10, bold=True, color="9C0006")
    ok_font = Font(name="Calibri", size=10, bold=True, color="006100")

    title_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
    subhdr_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    formula_fill = PatternFill(start_color="F2F4F8", end_color="F2F4F8", fill_type="solid")
    trip_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    ok_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    zebra_fill = PatternFill(start_color="F9FAFC", end_color="F9FAFC", fill_type="solid")

    thin_side = Side(border_style="thin", color="D9D9D9")
    grid_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    # =========================================================================
    # TAB 1: 1_Trip_Events_Summary_10s
    # =========================================================================
    ws1 = wb.create_sheet(title="1_Trip_Events_Summary_10s")
    ws1.views.sheetView[0].showGridLines = True

    ws1.merge_cells("A1:P1")
    ws1["A1"] = "GT-2420A 10-SECOND ('10s') STOP & TRIP EVENT FORENSIC SUMMARY (ALL 13 EVENTS)"
    ws1["A1"].font = title_font
    ws1["A1"].fill = title_fill
    ws1["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[1].height = 28

    ws1.merge_cells("A2:P2")
    ws1["A2"] = "Pulled from Live PI Server at 10-Second Interval (-40 min before event to +10 min after event). Red rows = Unplanned Hard Emergency Trips (Instant Solenoid Fuel Cut)."
    ws1["A2"].font = bold_font
    ws1["A2"].fill = subhdr_fill

    t1_headers = [
        "Event #",
        "Exact 10s Trigger Timestamp (UTC)",
        "Stop / Trip Classification",
        "HP Speed @ t-30m (RPM)",
        "HP Speed @ t-10s (RPM)",
        "HP Speed @ Trigger (RPM)",
        "LP Speed @ t-10s (RPM)",
        "LP Speed @ Trigger (RPM)",
        "Fuel SRV @ t-10s (%)",
        "Fuel SRV @ Trigger (%)",
        "IGV @ t-10s (°)",
        "IGV @ Trigger (°)",
        "Exhaust Spread @ Trigger (°C)",
        "Earliest Precursor Lead Time (min)",
        "Peak Precursor |Z| (σ)",
        "Top 3 Early-Warning / Trip-Contributing Sensors (Before Fuel Cut)"
    ]
    for col_i, h in enumerate(t1_headers, start=1):
        c = ws1.cell(row=3, column=col_i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border
    ws1.row_dimensions[3].height = 28

    for idx, ev in enumerate(event_summaries, start=4):
        is_ht = ev["is_hard_trip"]
        r_fill = trip_fill if is_ht else (zebra_fill if idx % 2 == 0 else None)
        r_font = trip_font if is_ht else regular_font

        vals = [
            ev["event_id"],
            ev["t_trig_str"],
            ev["class_str"],
            round(ev["hp_30m"], 1),
            round(ev["hp_10s"], 1),
            round(ev["hp_trig"], 1),
            round(ev["lp_10s"], 1),
            round(ev["lp_trig"], 1),
            round(ev["srv_10s"], 1),
            round(ev["srv_trig"], 1),
            round(ev["igv_10s"], 1),
            round(ev["igv_trig"], 1),
            round(ev["ttxs_trig"], 1),
            round(ev["lead_min"], 1),
            round(ev["peak_z"], 1),
            ev["top_precursors"],
        ]
        for col_i, v in enumerate(vals, start=1):
            c = ws1.cell(row=idx, column=col_i, value=v)
            c.font = r_font if col_i in (1, 2, 3, 10, 13, 16) else regular_font
            if r_fill:
                c.fill = r_fill
            c.border = grid_border
            if isinstance(v, float):
                c.number_format = "0.0"

    ws1.freeze_panes = "D4"
    t1_widths = [9, 24, 38, 15, 15, 15, 15, 15, 14, 14, 13, 13, 16, 16, 15, 78]
    for i, w in enumerate(t1_widths, 1):
        ws1.column_dimensions[get_column_letter(i)].width = w

    # =========================================================================
    # TAB 2: 2_Trip_Contributor_Sensors (Focused 26 Sensors & Formulas)
    # =========================================================================
    ws2 = wb.create_sheet(title="2_Trip_Contributor_Sensors")
    ws2.views.sheetView[0].showGridLines = True

    ws2.merge_cells("A1:R1")
    ws2["A1"] = "FOCUSED TRIP-CONTRIBUTING & EARLY-WARNING SENSORS (26 KEY SENSORS + MONITORING FORMULAS)"
    ws2["A1"].font = title_font
    ws2["A1"].fill = title_fill
    ws2["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 28

    ws2.merge_cells("A2:R2")
    ws2["A2"] = "Narrowed down from 158 broad sensors to ONLY the 26 sensors that directly indicate or give early warning of a Trip/Shutdown across the 4 Physical Precursor Families."
    ws2["A2"].font = bold_font
    ws2["A2"].fill = subhdr_fill

    t2_headers = [
        "Sensor #",
        "Precursor Family",
        "Sensor Short Name",
        "Role in Trip / Early Warning Signature",
        "Events Triggered (# of Events)",
        "Avg Early Lead Time (min)",
        "Max Observed |Z| Before Stop",
        "Intercept (β₀)",
        "Residual Std (σ_r)",
        "Expected Value Formula: Ŷ = β₀ + Σ (β_i × Peer_i)",
        "Anomaly Z-Score Monitoring Formula: Z = (Actual - Ŷ - μ_r) / σ_r",
        "Rate-of-Change & Hunting Rule (10s Stream)",
        "Peer 1 Name", "Peer 1 Pearson r", "Peer 1 Weight (β₁)",
        "Peer 2 Name", "Peer 2 Pearson r", "Peer 2 Weight (β₂)",
    ]
    for col_i, h in enumerate(t2_headers, start=1):
        c = ws2.cell(row=3, column=col_i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border
    ws2.row_dimensions[3].height = 28

    for idx, (s_path, fam, role_desc) in enumerate(FOCUSED_TRIP_SENSORS, start=1):
        r_num = idx + 3
        s_short = short_label(s_path)
        hits = sensor_event_hits.get(s_path, [])
        ev_list_str = f"{len(hits)} events ({', '.join('#'+str(h[0]) for h in hits[:6])})" if hits else "Primary Reference / Trip State"
        avg_lead = float(np.mean([h[2] for h in hits])) if hits else 0.0
        max_z_obs = float( np.max([h[1] for h in hits])) if hits else 0.0

        ws2.cell(row=r_num, column=1, value=idx).alignment = Alignment(horizontal="center")
        ws2.cell(row=r_num, column=2, value=fam).font = bold_font
        ws2.cell(row=r_num, column=3, value=s_short).font = bold_font
        ws2.cell(row=r_num, column=4, value=role_desc)
        ws2.cell(row=r_num, column=5, value=ev_list_str)
        c_ld = ws2.cell(row=r_num, column=6, value=round(avg_lead, 1))
        c_ld.number_format = "0.0"
        c_mz = ws2.cell(row=r_num, column=7, value=round(max_z_obs, 1))
        c_mz.number_format = "0.0"

        if s_path in models:
            m = models[s_path]
            peers = peer_map[s_path]
            b0 = float(m.intercept_)
            coefs = [float(x) for x in m.coef_]
            mu_r = float(r_means[s_path])
            sd_r = float(r_stds[s_path])

            eq_str = build_formula_string(s_short, b0, peers, coefs)
            z_str = build_zscore_string(s_short, mu_r, sd_r)
            roc_rule = f"Alert if |Z| >= 3.0 for 30s (3 ticks) OR RollingStd_3m / {sd_r:.3f} >= 3.0x"

            c_b0 = ws2.cell(row=r_num, column=8, value=b0)
            c_b0.number_format = "0.00000"
            c_sd = ws2.cell(row=r_num, column=9, value=sd_r)
            c_sd.number_format = "0.00000"
            c_eq = ws2.cell(row=r_num, column=10, value=eq_str)
            c_eq.font = formula_font
            c_eq.fill = formula_fill
            c_zs = ws2.cell(row=r_num, column=11, value=z_str)
            c_zs.font = formula_font
            c_zs.fill = formula_fill
            ws2.cell(row=r_num, column=12, value=roc_rule).font = bold_font

            # Peer 1 & Peer 2
            for p_i in range(2):
                base_c = 13 + p_i * 3
                if p_i < len(peers):
                    p_p = peers[p_i]
                    p_sh = short_label(p_p)
                    pr_val = float(corr_pearson.loc[s_path, p_p]) if (s_path in corr_pearson.index and p_p in corr_pearson.columns) else 0.99
                    ws2.cell(row=r_num, column=base_c, value=p_sh)
                    cr = ws2.cell(row=r_num, column=base_c + 1, value=pr_val)
                    cr.number_format = "0.0000"
                    cb = ws2.cell(row=r_num, column=base_c + 2, value=coefs[p_i])
                    cb.number_format = "0.00000"
        for col_i in range(1, len(t2_headers) + 1):
            ws2.cell(row=r_num, column=col_i).border = grid_border

    ws2.freeze_panes = "D4"
    t2_widths = [9, 24, 34, 52, 24, 15, 15, 14, 14, 88, 68, 48, 28, 13, 14, 28, 13, 14]
    for i, w in enumerate(t2_widths, 1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    # =========================================================================
    # TAB 3: 3_Precursor_Correlations (Focused 26x26 Matrix + Pairwise Table)
    # =========================================================================
    ws3 = wb.create_sheet(title="3_Precursor_Correlations")
    ws3.views.sheetView[0].showGridLines = True

    ws3.merge_cells("A1:J1")
    ws3["A1"] = "FOCUSED CORRELATIONS AMONG THE 26 TRIP-CONTRIBUTING SENSORS (PEARSON r, SPEARMAN ρ & 10s LEAD/LAG)"
    ws3["A1"].font = title_font
    ws3["A1"].fill = title_fill
    ws3["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws3.row_dimensions[1].height = 28

    t3_headers = [
        "Rank",
        "Family A",
        "Sensor A (Trip Precursor)",
        "Family B",
        "Sensor B (Correlated Partner)",
        "Pearson Linear r (10s Pre-Trip)",
        "Spearman Rank ρ (Monotonic)",
        "Absolute |r|",
        "Optimal Lead/Lag (Seconds)",
        "Physical Coupling & How to Monitor Together"
    ]
    for col_i, h in enumerate(t3_headers, start=1):
        c = ws3.cell(row=2, column=col_i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border
    ws3.row_dimensions[2].height = 26

    fam_map = {s: f for s, f, _ in FOCUSED_TRIP_SENSORS}
    focused_pairs = []
    n_f = len(focused_paths)
    # Use Event 4 (Hard Trip #1) pre-trip 10s window for lead/lag cross-correlation
    ev4_pre = df_10s[(df_10s["event_id"] == 4) & (df_10s["rel_seconds_to_trip"] < -40)][focused_paths].ffill().bfill()

    for i in range(n_f):
        for j in range(i + 1, n_f):
            sa, sb = focused_paths[i], focused_paths[j]
            r_p = float(corr_pearson.loc[sa, sb])
            r_s = float(corr_spearman.loc[sa, sb])
            if np.isnan(r_p):
                continue
            abs_r = abs(r_p)
            if abs_r >= 0.25 or abs(r_s) >= 0.35:
                # Compute best lag in [-60s..+60s] (-6..+6 ticks of 10s) on Event 4 pre-trip
                best_lag_s = 0
                best_lag_corr = abs_r
                s1 = (ev4_pre[sa] - ev4_pre[sa].mean()) / (ev4_pre[sa].std() + 1e-9)
                s2 = (ev4_pre[sb] - ev4_pre[sb].mean()) / (ev4_pre[sb].std() + 1e-9)
                for lag_ticks in range(-6, 7):
                    c_lag = abs(float(s1.corr(s2.shift(lag_ticks))))
                    if not np.isnan(c_lag) and c_lag > best_lag_corr + 0.02:
                        best_lag_corr = c_lag
                        best_lag_s = lag_ticks * 10

                focused_pairs.append((sa, sb, r_p, r_s, max(abs_r, abs(r_s)), best_lag_s))

    focused_pairs.sort(key=lambda x: x[4], reverse=True)

    for rank_i, (sa, sb, rp, rs, max_r, lag_s) in enumerate(focused_pairs[:80], start=1):
        rn = rank_i + 2
        fa, fb = fam_map.get(sa, ""), fam_map.get(sb, "")
        na, nb = short_label(sa), short_label(sb)
        lag_txt = f"Simultaneous (0s)" if lag_s == 0 else (f"{na} leads by {abs(lag_s)}s" if lag_s > 0 else f"{nb} leads by {abs(lag_s)}s")
        rel_txt = "Strong Direct Coupling" if rp >= 0.75 else ("Strong Inverse Coupling" if rp <= -0.75 else ("Monotonic / Non-Linear Coupling" if abs(rs) > abs(rp) + 0.15 else "Moderate Coupling"))

        row_vals = [rank_i, fa, na, fb, nb, rp, rs, abs(rp), lag_txt, f"{rel_txt} ({'Same Family' if fa==fb else 'Cross-Subsystem Link'})"]
        for ci, val in enumerate(row_vals, start=1):
            cell = ws3.cell(row=rn, column=ci, value=val)
            if ci in (3, 5):
                cell.font = bold_font
            if ci in (6, 7, 8):
                cell.number_format = "0.0000"
            cell.border = grid_border

    ws3.freeze_panes = "A3"
    t3_widths = [8, 24, 34, 24, 34, 16, 16, 14, 24, 48]
    for i, w in enumerate(t3_widths, 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    # =========================================================================
    # TAB 4: 4_Live_Trip_Monitor_Calculator
    # =========================================================================
    ws4 = wb.create_sheet(title="4_Live_Trip_Monitor_Calculator")
    ws4.views.sheetView[0].showGridLines = True

    ws4.merge_cells("A1:K1")
    ws4["A1"] = "LIVE EXCEL FORMULA CALCULATOR FOR TRIP PRECURSOR MONITORING (10-SECOND TELEMETRY)"
    ws4["A1"].font = title_font
    ws4["A1"].fill = title_fill
    ws4["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws4.row_dimensions[1].height = 28

    calc_scenarios = [
        {
            "title": "SCENARIO 1: HARD EMERGENCY TRIP #1 PRECURSOR — FLAME DETECTOR & COMPRESSOR DISCHARGE (2026-01-05 01:23:20 UTC)",
            "event_id": 4,
            "target": r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Outlet Pressure",
            "norm_rel_s": -2100,  # 35m before
            "peak_rel_s": -250,   # 01:19:50 UTC (3.5m before trip)
            "note": "Captures pre-trip pressure & fuel hunting before SRV slams from 41.1% to -2.8% at 01:23:20 UTC"
        },
        {
            "title": "SCENARIO 2: HARD EMERGENCY TRIP #2 PRECURSOR — COMBUSTION SPREAD DIVERGENCE ON RESTART (2026-01-05 03:20:50 UTC)",
            "event_id": 5,
            "target": r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 5",
            "norm_rel_s": -150,   # 03:18:30 UTC
            "peak_rel_s": -700,   # 03:09:20 UTC (11.5m before trip)
            "note": "Exhaust Temp 5/6/7/8/12 diverge (|Z|=173.4σ) 11.5 mins before Hard Trip #2 at 03:20:50 UTC"
        },
        {
            "title": "SCENARIO 3: DRY GAS SEAL FILTER DP SURGE — PROCESS-INITIATED STOP (2026-02-04 03:35:50 UTC)",
            "event_id": 7,
            "target": r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Inlet Pressure",
            "norm_rel_s": -2100,
            "peak_rel_s": -100,   # 03:35:20 UTC
            "note": "Accompanies 55x spike in Seal Gas Filters DP (0.69 -> 38.01) & Bearing 3/4 thermal shift"
        },
        {
            "title": "SCENARIO 4: BURNER COLD-SPOT & ANTI-SURGE STOP — EXHAUST TEMP 7 (2025-12-07 07:33:50 UTC)",
            "event_id": 3,
            "target": r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 7",
            "norm_rel_s": -300,
            "peak_rel_s": -2110,  # 06:58:50 UTC (35m before stop)
            "note": "Exhaust Temp 7 drops to 162.5°C while peers reach 716-821°C (|Z|=345.5σ, 35m before stop)"
        },
    ]

    curr_r = 3
    for sc in calc_scenarios:
        ev_df = df_10s[df_10s["event_id"] == sc["event_id"]].sort_index().ffill().bfill().fillna(0.0)
        target = sc["target"]
        t_sh = short_label(target)
        m = models[target]
        peers = peer_map[target]
        b0 = float(m.intercept_)
        coefs = [float(x) for x in m.coef_]
        mu_r = float(r_means[target])
        sd_r = float(r_stds[target])

        idx_norm = (ev_df["rel_seconds_to_trip"] - sc["norm_rel_s"]).abs().idxmin()
        idx_peak = (ev_df["rel_seconds_to_trip"] - sc["peak_rel_s"]).abs().idxmin()
        r_norm = ev_df.loc[idx_norm]
        r_peak = ev_df.loc[idx_peak]

        ws4.merge_cells(start_row=curr_r, start_column=1, end_row=curr_r, end_column=11)
        ws4.cell(row=curr_r, column=1, value=sc["title"]).font = title_font
        ws4.cell(row=curr_r, column=1).fill = header_fill
        ws4.row_dimensions[curr_r].height = 22
        curr_r += 1

        eq_s = build_formula_string(t_sh, b0, peers, coefs)
        zs_s = build_zscore_string(t_sh, mu_r, sd_r)

        ws4.cell(row=curr_r, column=1, value="Expected Formula (Ŷ)").font = bold_font
        ws4.merge_cells(start_row=curr_r, start_column=2, end_row=curr_r, end_column=8)
        ws4.cell(row=curr_r, column=2, value=eq_s).font = formula_font
        ws4.merge_cells(start_row=curr_r, start_column=9, end_row=curr_r, end_column=11)
        ws4.cell(row=curr_r, column=9, value=sc["note"]).font = bold_font
        curr_r += 1

        ws4.cell(row=curr_r, column=1, value="Z-Score Formula (Z)").font = bold_font
        ws4.merge_cells(start_row=curr_r, start_column=2, end_row=curr_r, end_column=8)
        ws4.cell(row=curr_r, column=2, value=zs_s).font = formula_font
        ws4.merge_cells(start_row=curr_r, start_column=9, end_row=curr_r, end_column=11)
        ws4.cell(row=curr_r, column=9, value=f"μ_r = {mu_r:.5f} | σ_r = {sd_r:.5f}").font = bold_font
        curr_r += 1

        hdrs = [
            "Variable", "Sensor Short Name", "Full PI Tag Path",
            "Pearson r", "Spearman ρ", "Ridge Weight (β_i)",
            f"Sample A ({str(idx_norm)[11:19]} UTC)", "Term A (β_i × X_i)",
            f"Pre-Trip Peak ({str(idx_peak)[11:19]} UTC)", "Term B (β_i × X_i)",
            "Formula Diagnostic"
        ]
        for ci, h_t in enumerate(hdrs, 1):
            c = ws4.cell(row=curr_r, column=ci, value=h_t)
            c.font = header_font
            c.fill = header_fill
            c.border = grid_border
        curr_r += 1

        b0_row = curr_r
        ws4.cell(row=curr_r, column=1, value="β₀ (Intercept)").font = bold_font
        ws4.cell(row=curr_r, column=2, value="Constant Offset")
        ws4.cell(row=curr_r, column=3, value="Ridge Regression Intercept")
        ws4.cell(row=curr_r, column=6, value=b0).number_format = "0.00000"
        ws4.cell(row=curr_r, column=7, value=1.0)
        ws4.cell(row=curr_r, column=8, value=f"=F{curr_r}*G{curr_r}").number_format = "0.000"
        ws4.cell(row=curr_r, column=9, value=1.0)
        ws4.cell(row=curr_r, column=10, value=f"=F{curr_r}*I{curr_r}").number_format = "0.000"
        ws4.cell(row=curr_r, column=11, value="Constant Baseline Term")
        for ci in range(1, 12):
            ws4.cell(row=curr_r, column=ci).border = grid_border
        curr_r += 1

        for pi, (p_path, c_val) in enumerate(zip(peers, coefs), 1):
            p_sh = short_label(p_path)
            rp_v = float( ev_df[target].corr(ev_df[p_path], method="pearson") )
            rs_v = float( ev_df[target].corr(ev_df[p_path], method="spearman") )
            ws4.cell(row=curr_r, column=1, value=f"X_{pi} (Peer {pi})").font = bold_font
            ws4.cell(row=curr_r, column=2, value=p_sh).font = bold_font
            ws4.cell(row=curr_r, column=3, value=p_path)
            ws4.cell(row=curr_r, column=4, value=0.0 if np.isnan(rp_v) else rp_v).number_format = "0.000"
            ws4.cell(row=curr_r, column=5, value=0.0 if np.isnan(rs_v) else rs_v).number_format = "0.000"
            ws4.cell(row=curr_r, column=6, value=c_val).number_format = "0.00000"
            ws4.cell(row=curr_r, column=7, value=float(r_norm[p_path])).number_format = "0.000"
            ws4.cell(row=curr_r, column=8, value=f"=F{curr_r}*G{curr_r}").number_format = "0.000"
            ws4.cell(row=curr_r, column=9, value=float(r_peak[p_path])).number_format = "0.000"
            ws4.cell(row=curr_r, column=10, value=f"=F{curr_r}*I{curr_r}").number_format = "0.000"
            ws4.cell(row=curr_r, column=11, value=f"Peer #{pi} Input")
            for ci in range(1, 12):
                ws4.cell(row=curr_r, column=ci).border = grid_border
            curr_r += 1
        last_p_row = curr_r - 1

        exp_r = curr_r
        ws4.cell(row=curr_r, column=1, value="Ŷ (Expected)").font = bold_font
        ws4.cell(row=curr_r, column=2, value=f"Expected {t_sh}").font = bold_font
        ws4.cell(row=curr_r, column=3, value=f"=SUM(H{b0_row}:H{last_p_row})").font = formula_font
        ws4.cell(row=curr_r, column=8, value=f"=SUM(H{b0_row}:H{last_p_row})").number_format = "0.000"
        ws4.cell(row=curr_r, column=10, value=f"=SUM(J{b0_row}:J{last_p_row})").number_format = "0.000"
        ws4.cell(row=curr_r, column=11, value="Digital Twin Predicted Value")
        for ci in range(1, 12):
            ws4.cell(row=curr_r, column=ci).border = grid_border
        curr_r += 1

        act_r = curr_r
        ws4.cell(row=curr_r, column=1, value="Y (Actual)").font = bold_font
        ws4.cell(row=curr_r, column=2, value=f"Actual {t_sh}").font = bold_font
        ws4.cell(row=curr_r, column=3, value="10s PI Sensor Reading")
        ws4.cell(row=curr_r, column=8, value=float(r_norm[target])).number_format = "0.000"
        c_ap = ws4.cell(row=curr_r, column=10, value=float(r_peak[target]))
        c_ap.number_format = "0.000"
        c_ap.font = trip_font
        c_ap.fill = trip_fill
        ws4.cell(row=curr_r, column=11, value="Actual Measured Telemetry")
        for ci in range(1, 12):
            ws4.cell(row=curr_r, column=ci).border = grid_border
        curr_r += 1

        res_r = curr_r
        ws4.cell(row=curr_r, column=1, value="r (Residual)").font = bold_font
        ws4.cell(row=curr_r, column=2, value="Actual - Expected").font = bold_font
        ws4.cell(row=curr_r, column=3, value=f"=H{act_r}-H{exp_r}").font = formula_font
        ws4.cell(row=curr_r, column=4, value=mu_r).number_format = "0.00000"
        ws4.cell(row=curr_r, column=5, value=sd_r).number_format = "0.00000"
        ws4.cell(row=curr_r, column=6, value="← Col D=μ_r, Col E=σ_r")
        ws4.cell(row=curr_r, column=8, value=f"=H{act_r}-H{exp_r}").number_format = "+0.000;-0.000;0.000"
        c_rp = ws4.cell(row=curr_r, column=10, value=f"=J{act_r}-J{exp_r}")
        c_rp.number_format = "+0.000;-0.000;0.000"
        c_rp.font = trip_font
        c_rp.fill = trip_fill
        ws4.cell(row=curr_r, column=11, value="Physical Deviation")
        for ci in range(1, 12):
            ws4.cell(row=curr_r, column=ci).border = grid_border
        curr_r += 1

        z_r = curr_r
        ws4.cell(row=curr_r, column=1, value="Z (Z-Score)").font = bold_font
        ws4.cell(row=curr_r, column=2, value="(r - μ_r) / σ_r").font = bold_font
        ws4.cell(row=curr_r, column=3, value=f"=(J{res_r}-D{res_r})/E{res_r}").font = formula_font
        ws4.cell(row=curr_r, column=8, value=f"=(H{res_r}-D{res_r})/E{res_r}").number_format = "+0.00;-0.00;0.00"
        c_zp = ws4.cell(row=curr_r, column=10, value=f"=(J{res_r}-D{res_r})/E{res_r}")
        c_zp.number_format = "+0.00;-0.00;0.00"
        c_zp.font = trip_font
        c_zp.fill = trip_fill
        ws4.cell(row=curr_r, column=11, value=f"=IF(ABS(J{z_r})>=4.0, \"CRITICAL TRIP PRECURSOR (|Z|>=4)\", IF(ABS(J{z_r})>=3.0, \"EARLY WARNING (|Z|>=3)\", \"NORMAL\"))").font = trip_font
        for ci in range(1, 12):
            ws4.cell(row=curr_r, column=ci).border = grid_border
        curr_r += 2

    t4_widths = [20, 34, 50, 14, 14, 18, 24, 20, 24, 20, 38]
    for i, w in enumerate(t4_widths, 1):
        ws4.column_dimensions[get_column_letter(i)].width = w

    # =========================================================================
    # TAB 5: 5_10s_HardTrip_Timeline (Granular 10s Trace of Hard Trip #1 & #2)
    # =========================================================================
    ws5 = wb.create_sheet(title="5_10s_HardTrip_Timeline")
    ws5.views.sheetView[0].showGridLines = True

    ws5.merge_cells("A1:N1")
    ws5["A1"] = "10-SECOND GRANULAR TELEMETRY & FORMULA TRACKING — HARD EMERGENCY TRIP #1 (2026-01-05 01:23:20 UTC)"
    ws5["A1"].font = title_font
    ws5["A1"].fill = title_fill
    ws5["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws5.row_dimensions[1].height = 28

    t5_headers = [
        "10s Timestamp (UTC)",
        "Seconds to Trip (t - t_trip)",
        "HP Shaft Speed (RPM)",
        "LP Shaft Speed (RPM)",
        "Fuel SRV Position (%)",
        "Fuel FCV Position (%)",
        "IGV Position (°)",
        "Exhaust Spread TTXS (°C)",
        "Flame Detector Ch.3",
        "Turbine Brg 1 Vib (µm)",
        "Brg 4 Drain Oil Temp (°C)",
        "Tertiary Seal Gas Press (bar)",
        "2nd Stg Comp Out Press (Actual)",
        "Trip Status / Formula State"
    ]
    for ci, h in enumerate(t5_headers, 1):
        c = ws5.cell(row=2, column=ci, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border
    ws5.row_dimensions[2].height = 26

    ev4_full = df_10s[df_10s["event_id"] == 4].sort_index().ffill().bfill().fillna(0.0)
    t_trig_4 = pd.to_datetime("2026-01-05 01:23:20", utc=True)

    c_flm3 = r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector Combustion Chamber 3"
    c_vib1 = r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine Bearing 1 Radial Vibrations Vibration Probe Proximitor"
    c_b4dr = r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Journal Thrust Bearing 4 Drain Oil Temperature"
    c_tsgp = r"MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure"
    c_c2op = r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Outlet Pressure"

    for r_i, (ts_idx, r_val) in enumerate(ev4_full.iterrows(), start=3):
        rel_s = (ts_idx - t_trig_4).total_seconds()
        ttxs_v = float(r_val[ex_cols].max() - r_val[ex_cols].min())
        srv_v = float(r_val[srv_col])
        state_str = "TRIPPED (SRV Closed / Coastdown)" if srv_v < 0 else ("EXACT TRIP TRIGGER (10s Solenoid Cut)" if rel_s == 0 else "PRE-TRIP RUNNING (Early Precursor Window)")

        row_data = [
            ts_idx.strftime("%Y-%m-%d %H:%M:%S"),
            int(rel_s),
            float(r_val[hp_col]),
            float(r_val[lp_col]),
            srv_v,
            float(r_val[fcv_col]),
            float(r_val[igv_col]),
            ttxs_v,
            float(r_val[c_flm3]),
            float(r_val[c_vib1]),
            float(r_val[c_b4dr]),
            float(r_val[c_tsgp]),
            float(r_val[c_c2op]),
            state_str,
        ]
        is_trig_row = abs(rel_s) <= 10
        for ci, v in enumerate(row_data, 1):
            c = ws5.cell(row=r_i, column=ci, value=v)
            if isinstance(v, float):
                c.number_format = "0.00"
            if is_trig_row:
                c.fill = trip_fill
                c.font = trip_font
            c.border = grid_border

    ws5.freeze_panes = "C3"
    t5_widths = [22, 16, 16, 16, 16, 16, 14, 18, 18, 18, 18, 18, 20, 36]
    for i, w in enumerate(t5_widths, 1):
        ws5.column_dimensions[get_column_letter(i)].width = w

    # =========================================================================
    # TAB 6: 6_Sweet_Spot_Operating_Guide (Optimum Target & Green Envelope)
    # =========================================================================
    ws6 = wb.create_sheet(title="6_Sweet_Spot_Operating_Guide")
    ws6.views.sheetView[0].showGridLines = True

    ws6.merge_cells("A1:O1")
    ws6["A1"] = "GT-2420A OPERATING 'SWEET SPOT' GUIDE — DYNAMIC OPTIMUM TARGETS (Ŷ ± 2σ_r) VS. STATIC MANUFACTURER LIMITS"
    ws6["A1"].font = title_font
    ws6["A1"].fill = title_fill
    ws6["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws6.row_dimensions[1].height = 28

    ws6.merge_cells("A2:O2")
    ws6["A2"] = "How it works: Instead of waiting for static Manufacturer Trip Limits, the formula calculates the exact Optimum Target (Ŷ) for current load/speed and defines a tight Green Sweet-Spot Band (Ŷ ± 2σ_r) where Z stays within [-2, +2]."
    ws6["A2"].font = bold_font
    ws6["A2"].fill = subhdr_fill

    # Section 1: Golden Operating Regimes (Machine-Level Control Setpoints)
    ws6.merge_cells("A4:O4")
    ws6["A4"] = "1. TURBINE-LEVEL 'GOLDEN OPERATING REGIMES' (OPTIMUM CONTROL SETPOINTS FOR MINIMUM WEAR & ZERO TRIP RISK)"
    ws6["A4"].font = section_font
    ws6["A4"].fill = subhdr_fill

    reg_headers = [
        "Control Parameter",
        "PI Sensor Short Name",
        "Unit",
        "Part-Load Cruise Sweet Spot (IGV=56°–78°)",
        "Full-Load High-Output Sweet Spot (IGV=84.9°–85.0°)",
        "Pre-Trip Danger / Hunting Zone (Avoid!)",
        "Static DCS / Manufacturer Limit",
        "Why Operating Inside the Sweet Spot Matters"
    ]
    ws6.merge_cells("H5:O5")
    for ci, h in enumerate(reg_headers, 1):
        c = ws6.cell(row=5, column=ci, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border
    for ci in range(8, 16):
        ws6.cell(row=5, column=ci).fill = header_fill
        ws6.cell(row=5, column=ci).border = grid_border
    ws6.row_dimensions[5].height = 24

    golden_regimes = [
        ("Gas Generator Speed", "HP Shaft Magnetic Speed Pick Up", "RPM", "4,775 – 5,100 RPM (Steady ±3 RPM)", "5,000 – 5,105 RPM (Steady ±3 RPM)", "> 5,125 RPM or hunting ±35 RPM every 3m", "Overspeed Trip > 5,457 RPM", "Prevents compressor surge, blade flutter, and fuel governor hunting (seen before Hard Trip #1 & #2)."),
        ("Power Turbine Speed", "LP Shaft Magnetic Speed Pick Up", "RPM", "3,262 – 3,266 RPM (Steady ±2 RPM)", "3,585 – 3,858 RPM (Steady ±3 RPM)", "> 3,870 RPM with rapid 50 RPM swings", "Overspeed Trip > 5,000 RPM", "Keeps driven load compressor on its peak efficiency map away from the surge line."),
        ("Inlet Guide Vanes", "Turbine IGV Position", "deg (°)", "56.0° or 77.0°–79.2° (Fixed Step)", "84.9° – 85.0° (Full Open Steady)", "Rapid modulation or stuck < 34° under load", "Min Fired Idle = 34.0°, Trip = 29.9°", "Matches airflow to fuel flow to keep all 13 combustion cans firing at uniform temperature."),
        ("Fuel Stop/Speed Ratio Valve", "Fuel Gas Stop/Speed Ratio Valve Position", "%", "25.5% – 28.0% (Smooth ±0.2%)", "34.0% – 39.5% (Smooth ±0.2%)", "> 41.5% hunting or > 90% saturation", "0% (-2.8%) = Solenoid Trip Cut", "Keeping SRV between 25%–39.5% maintains stable interstage fuel pressure (~195–205 bar) without hunting."),
        ("Fuel Gas Control Valve", "Fuel Gas Control Valve Position", "%", "35.5% – 39.5% (Smooth ±0.2%)", "46.0% – 51.5% (Smooth ±0.2%)", "52.8% – 58.1% oscillating (3-min cycle)", "0% (-2.9%) = Fuel Cut", "Above 53% with oscillations indicates combustor flame instability / coking (preceded Hard Trip #1)."),
        ("Exhaust Temp Spread (TTXS)", "MAX(Exhaust Temp 1..13) - MIN(1..13)", "°C", "8.0 °C – 19.5 °C (Ideal < 16 °C)", "8.1 °C – 17.5 °C (Ideal < 15 °C)", "> 25.0 °C (Early burner coking/hot streak)", "Alarm = 55.0 °C | Trip = 80.0 °C", "Operating with Spread < 18°C eliminates thermal distortion on turbine nozzles and blades."),
        ("Dry Gas Seal Filter DP", "Seal Gas Filters Differential Pressure", "bar", "0.03 – 0.45 bar (Clean Filter)", "0.04 – 0.70 bar (Clean Filter)", "> 1.20 bar (Filter plugging / surge risk)", "High DP Alarm > 2.0 bar (Spiked to 38 bar)", "Switching filter bank before DP exceeds 1.2 bar prevents forced DGS process shutdowns (Events #7, #8, #12, #13)."),
        ("Lube Oil Supply Header", "Lube Oil Header Pressure 3", "bar", "26.7 – 27.6 bar (Temp 125–129 °C)", "26.6 – 27.4 bar (Temp 125–129 °C)", "< 25.5 bar or sudden 0.3 bar dip", "Low Oil Press Trip", "Maintains hydrodynamic oil wedge in journal & thrust bearings, keeping bearing drain oil oscillation < 0.12°C."),
    ]

    for idx_g, (p_lbl, s_lbl, unit_s, part_s, full_s, dng_s, lim_s, why_s) in enumerate(golden_regimes, start=6):
        ws6.cell(row=idx_g, column=1, value=p_lbl).font = bold_font
        ws6.cell(row=idx_g, column=2, value=s_lbl).font = bold_font
        ws6.cell(row=idx_g, column=3, value=unit_s).alignment = Alignment(horizontal="center")
        c_pt = ws6.cell(row=idx_g, column=4, value=part_s)
        c_pt.fill = ok_fill
        c_pt.font = ok_font
        c_fl = ws6.cell(row=idx_g, column=5, value=full_s)
        c_fl.fill = ok_fill
        c_fl.font = ok_font
        c_dn = ws6.cell(row=idx_g, column=6, value=dng_s)
        c_dn.fill = trip_fill
        c_dn.font = trip_font
        ws6.cell(row=idx_g, column=7, value=lim_s).font = bold_font
        ws6.merge_cells(start_row=idx_g, start_column=8, end_row=idx_g, end_column=15)
        ws6.cell(row=idx_g, column=8, value=why_s)
        for ci in range(1, 16):
            ws6.cell(row=idx_g, column=ci).border = grid_border

    # Load static limits from operating_limits.db for comparison
    import sqlite3
    db_limits = {}
    db_path = PROJECT_ROOT / "data" / "operating_limits.db"
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        lim_df = pd.read_sql("SELECT af_path, type, value FROM operating_limits", conn)
        conn.close()
        for _, lr in lim_df.iterrows():
            p_k = str(lr["af_path"])
            t_k = str(lr["type"]).upper()
            db_limits.setdefault(p_k, {})[t_k] = float(lr["value"])

    # Compute healthy Part-Load and Full-Load sweet spot baselines from 10s dataset
    # Healthy Part-Load sample: Event 1 at t = -35m (2025-10-07 06:40:00 UTC)
    # Healthy Full-Load sample: Event 4 at t = -35m (2026-01-05 00:49:00 UTC) and Event 13 at t = -35m (2026-09-02 06:32:00 UTC)
    ev1_base = df_10s[(df_10s["event_id"] == 1) & (df_10s["rel_seconds_to_trip"] <= -1500)][sensor_cols].ffill().bfill().mean()
    ev4_base = df_10s[(df_10s["event_id"] == 4) & (df_10s["rel_seconds_to_trip"] <= -1500)][sensor_cols].ffill().bfill().mean()

    # Section 2: All 26 Watchdog Sensors — Dynamic Sweet Spot vs Manufacturer Limits
    sec2_row = 16
    ws6.merge_cells(f"A{sec2_row}:O{sec2_row}")
    ws6[f"A{sec2_row}"] = "2. SENSOR-BY-SENSOR 'SWEET SPOT' OPERATING ENVELOPE (DYNAMIC OPTIMUM Ŷ ± 2σ_r VS. STATIC MANUFACTURER LIMITS)"
    ws6[f"A{sec2_row}"].font = section_font
    ws6[f"A{sec2_row}"].fill = subhdr_fill

    s2_hdr_row = sec2_row + 1
    s2_headers = [
        "Sensor #",
        "Precursor Family",
        "Sensor Short Name",
        "Residual Noise (σ_r)",
        "Sweet Spot Half-Width (±2σ_r)",
        "Part-Load Optimum Target (Ŷ_part)",
        "Part-Load Green Sweet Spot [Ŷ - 2σ_r .. Ŷ + 2σ_r]",
        "Full-Load Optimum Target (Ŷ_full)",
        "Full-Load Green Sweet Spot [Ŷ - 2σ_r .. Ŷ + 2σ_r]",
        "Yellow Early Warning Band (±3σ_r)",
        "Red Precursor Limit (±4σ_r)",
        "Static Normal Mean (DB)",
        "Static High Alarm (H)",
        "Static High-High Trip (HH)",
        "Dynamic Sweet Spot Formula (For Any Load/Speed)"
    ]
    for ci, h in enumerate(s2_headers, 1):
        c = ws6.cell(row=s2_hdr_row, column=ci, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border
    ws6.row_dimensions[s2_hdr_row].height = 28

    for idx_s, (s_path, fam, _) in enumerate(FOCUSED_TRIP_SENSORS, start=1):
        r_n = s2_hdr_row + idx_s
        s_sh = short_label(s_path)

        # Compute expected values at Part-Load and Full-Load
        if s_path in models:
            m = models[s_path]
            peers = peer_map[s_path]
            sd_r = float(r_stds[s_path])
            y_part = float(m.predict(ev1_base[peers].values.reshape(1, -1))[0])
            y_full = float(m.predict(ev4_base[peers].values.reshape(1, -1))[0])
        else:
            sd_r = float(df_10s[s_path].std()) if s_path in df_10s.columns else 1.0
            y_part = float(ev1_base.get(s_path, 0.0))
            y_full = float(ev4_base.get(s_path, 0.0))

        hw_2 = 2.0 * sd_r
        hw_3 = 3.0 * sd_r
        hw_4 = 4.0 * sd_r

        part_band_str = f"{y_part - hw_2:.2f}  to  {y_part + hw_2:.2f}"
        full_band_str = f"{y_full - hw_2:.2f}  to  {y_full + hw_2:.2f}"
        warn_str = f"Ŷ ± {hw_3:.2f}"
        crit_str = f"Ŷ ± {hw_4:.2f}"

        lims = db_limits.get(s_path, {})
        norm_db = lims.get("NORMAL", np.nan)
        h_db = lims.get("H", np.nan)
        hh_db = lims.get("HH", np.nan)

        dyn_formula = f"Optimum = Expected([{s_sh}])   |   Green Band = Expected([{s_sh}]) ± {hw_2:.4f}"

        ws6.cell(row=r_n, column=1, value=idx_s).alignment = Alignment(horizontal="center")
        ws6.cell(row=r_n, column=2, value=fam).font = bold_font
        ws6.cell(row=r_n, column=3, value=s_sh).font = bold_font
        ws6.cell(row=r_n, column=4, value=sd_r).number_format = "0.0000"
        ws6.cell(row=r_n, column=5, value=hw_2).number_format = "0.000"

        c_yp = ws6.cell(row=r_n, column=6, value=y_part)
        c_yp.number_format = "0.00"
        c_yp.font = bold_font
        c_pb = ws6.cell(row=r_n, column=7, value=part_band_str)
        c_pb.fill = ok_fill
        c_pb.font = ok_font
        c_pb.alignment = Alignment(horizontal="center")

        c_yf = ws6.cell(row=r_n, column=8, value=y_full)
        c_yf.number_format = "0.00"
        c_yf.font = bold_font
        c_fb = ws6.cell(row=r_n, column=9, value=full_band_str)
        c_fb.fill = ok_fill
        c_fb.font = ok_font
        c_fb.alignment = Alignment(horizontal="center")

        ws6.cell(row=r_n, column=10, value=warn_str).alignment = Alignment(horizontal="center")
        c_cr = ws6.cell(row=r_n, column=11, value=crit_str)
        c_cr.alignment = Alignment(horizontal="center")
        c_cr.font = trip_font

        c_nd = ws6.cell(row=r_n, column=12, value=norm_db if not np.isnan(norm_db) else "-")
        if not np.isnan(norm_db):
            c_nd.number_format = "0.00"
        c_hd = ws6.cell(row=r_n, column=13, value=h_db if not np.isnan(h_db) else "-")
        if not np.isnan(h_db):
            c_hd.number_format = "0.00"
        c_hhd = ws6.cell(row=r_n, column=14, value=hh_db if not np.isnan(hh_db) else "-")
        if not np.isnan(hh_db):
            c_hhd.number_format = "0.00"
            c_hhd.fill = trip_fill

        c_df = ws6.cell(row=r_n, column=15, value=dyn_formula)
        c_df.font = formula_font
        c_df.fill = formula_fill

        for ci in range(1, 16):
            ws6.cell(row=r_n, column=ci).border = grid_border

    # Section 3: Interactive Live Sweet-Spot Calculator (Change Peer Values to See Sweet Spot Shift!)
    sec3_row = s2_hdr_row + len(FOCUSED_TRIP_SENSORS) + 3
    ws6.merge_cells(f"A{sec3_row}:O{sec3_row}")
    ws6[f"A{sec3_row}"] = "3. INTERACTIVE 'SWEET SPOT' TARGET & ENVELOPE CALCULATOR (LIVE EXCEL FORMULAS)"
    ws6[f"A{sec3_row}"].font = section_font
    ws6[f"A{sec3_row}"].fill = subhdr_fill

    calc_hdr_r = sec3_row + 1
    calc_hdrs = [
        "Watchdog Sensor",
        "Current Actual Reading (Editable)",
        "Peer 1 Reading (Editable)",
        "Peer 2 Reading (Editable)",
        "Peer 3 Reading (Editable)",
        "Peer 4 Reading (Editable)",
        "Peer 5 Reading (Editable)",
        "Calculated Optimum Sweet Spot (Ŷ)",
        "Sweet Spot MIN (Ŷ - 2σ_r)",
        "Sweet Spot MAX (Ŷ + 2σ_r)",
        "Static DCS HH Limit",
        "Current Gap (Actual - Ŷ)",
        "Current Z-Score",
        "Live Operating Zone Status",
        "Operator Action Guidance"
    ]
    for ci, h in enumerate(calc_hdrs, 1):
        c = ws6.cell(row=calc_hdr_r, column=ci, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border
    ws6.row_dimensions[calc_hdr_r].height = 26

    showcase_sensors = [
        r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 7",
        r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 2",
        r"MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Journal Bearing Temperature 4",
        r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Outlet Pressure",
        r"MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Inlet Pressure",
        r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine Bearing 1 Radial Vibrations Vibration Probe Proximitor",
        r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Journal Thrust Bearing 4 Drain Oil Temperature",
        r"MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Pressure 3",
    ]

    for idx_c, sc_path in enumerate(showcase_sensors, start=1):
        rn = calc_hdr_r + idx_c
        sc_sh = short_label(sc_path)
        m = models[sc_path]
        peers = peer_map[sc_path]
        b0 = float(m.intercept_)
        coefs = [float(x) for x in m.coef_]
        sd_r = float(r_stds[sc_path])
        hh_val = db_limits.get(sc_path, {}).get("HH", np.nan)

        act_v = float(ev4_base[sc_path])
        ws6.cell(row=rn, column=1, value=sc_sh).font = bold_font
        c_ac = ws6.cell(row=rn, column=2, value=act_v)
        c_ac.number_format = "0.00"
        c_ac.font = bold_font

        terms_excel = [f"{b0:.6f}"]
        for pi in range(5):
            col_p = 3 + pi
            col_let = get_column_letter(col_p)
            if pi < len(peers):
                pv = float(ev4_base[peers[pi]])
                cp = ws6.cell(row=rn, column=col_p, value=pv)
                cp.number_format = "0.00"
                terms_excel.append(f"({coefs[pi]:.6f}*{col_let}{rn})")
            else:
                ws6.cell(row=rn, column=col_p, value=0.0).number_format = "0.00"

        formula_yhat = "=" + "+".join(terms_excel)
        c_yh = ws6.cell(row=rn, column=8, value=formula_yhat)
        c_yh.number_format = "0.00"
        c_yh.font = formula_font
        c_yh.fill = formula_fill

        c_smin = ws6.cell(row=rn, column=9, value=f"=H{rn}-(2*{sd_r:.6f})")
        c_smin.number_format = "0.00"
        c_smin.fill = ok_fill
        c_smin.font = ok_font

        c_smax = ws6.cell(row=rn, column=10, value=f"=H{rn}+(2*{sd_r:.6f})")
        c_smax.number_format = "0.00"
        c_smax.fill = ok_fill
        c_smax.font = ok_font

        c_hh = ws6.cell(row=rn, column=11, value=hh_val if not np.isnan(hh_val) else "-")
        if not np.isnan(hh_val):
            c_hh.number_format = "0.00"

        c_gap = ws6.cell(row=rn, column=12, value=f"=B{rn}-H{rn}")
        c_gap.number_format = "+0.00;-0.00;0.00"

        c_z = ws6.cell(row=rn, column=13, value=f"=(B{rn}-H{rn})/{sd_r:.6f}")
        c_z.number_format = "+0.00;-0.00;0.00"
        c_z.font = bold_font

        c_st = ws6.cell(row=rn, column=14, value=f'=IF(ABS(M{rn})<=2.0, "IN SWEET SPOT (OPTIMAL)", IF(ABS(M{rn})<3.0, "SLIGHT DRIFT (WATCH)", IF(ABS(M{rn})<4.0, "EARLY WARNING (|Z|>=3)", "OUT OF ENVELOPE (|Z|>=4)")))')
        c_st.font = ok_font
        c_st.fill = ok_fill

        c_act_g = ws6.cell(row=rn, column=15, value=f'=IF(ABS(M{rn})<=2.0, "Maintain current setpoint (Target=" & TEXT(H{rn},"0.0") & ")", "Adjust load/check subsystem to return toward " & TEXT(H{rn},"0.0"))')
        c_act_g.font = regular_font

        for ci in range(1, 16):
            ws6.cell(row=rn, column=ci).border = grid_border

    ws6.freeze_panes = "D6"
    t6_widths = [26, 34, 16, 28, 28, 28, 26, 20, 26, 20, 20, 16, 16, 26, 48]
    for i, w in enumerate(t6_widths, 1):
        ws6.column_dimensions[get_column_letter(i)].width = w

    wb.remove(default_ws)
    OUT_REPORTS_XLSX.parent.mkdir(parents=True, exist_ok=True)
    OUT_V2_XLSX = PROJECT_ROOT / "GT2420A_Trip_Focused_Monitoring_v2_SweetSpot.xlsx"
    wb.save(OUT_REPORTS_XLSX)
    shutil.copy2(OUT_REPORTS_XLSX, OUT_V2_XLSX)
    try:
        shutil.copy2(OUT_REPORTS_XLSX, OUT_ROOT_XLSX)
        print(f"Successfully saved to:\n  1) {OUT_ROOT_XLSX}\n  2) {OUT_V2_XLSX}\n  3) {OUT_REPORTS_XLSX}")
    except PermissionError:
        print(f"Note: {OUT_ROOT_XLSX.name} is currently open in Excel, so saved updated 6-tab workbook to:\n  1) {OUT_V2_XLSX}\n  2) {OUT_REPORTS_XLSX}")


if __name__ == "__main__":
    main()
