"""
Generate a comprehensive Excel workbook listing:
1. Detailed Prediction & Anomaly Formulas for Case 1, Case 2, and Case 3 (with live Excel formula calculators).
2. All 158 Digital Twin Sensor Prediction Formulas (Ridge Regression coefficients, intercepts, residual stats, and closed-form equations).
3. Ranked Pairwise Sensor Correlations across the GT-2420A Gas Turbine.
4. Full 158 x 158 Pearson Correlation Matrix.
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
DATA_PATH = PROJECT_ROOT / "data" / "historical_data.parquet"
MODEL_PATH = PROJECT_ROOT / "models" / "gt2420a_digital_twin.pkl"
OUTPUT_ROOT_XLSX = PROJECT_ROOT / "GT2420A_Correlations_and_Prediction_Formulas.xlsx"
OUTPUT_REPORTS_XLSX = PROJECT_ROOT / "reports" / "GT2420A_Correlations_and_Prediction_Formulas.xlsx"


def parse_tag_parts(full_path: str):
    sep = "\\" if "\\" in str(full_path) else "|"
    parts = str(full_path).split(sep)
    if len(parts) >= 6:
        # e.g. MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 7
        return parts[4], parts[4], parts[-1]
    elif len(parts) == 5:
        return parts[3], parts[3], parts[-1]
    elif len(parts) >= 2:
        return parts[-2], parts[-2], parts[-1]
    return "Unknown", "Unknown", str(full_path)


def short_label(full_path: str) -> str:
    _, _, tag = parse_tag_parts(full_path)
    return tag


def build_formula_string(target_short: str, intercept: float, peers: list, coefs: list, use_short: bool = True) -> str:
    terms = [f"{intercept:.6f}"]
    for p, c in zip(peers, coefs):
        p_name = short_label(p) if use_short else p
        sign = "+" if c >= 0 else "-"
        terms.append(f"{sign} ({abs(c):.6f} * [{p_name}])")
    return f"Expected([{target_short}]) = " + " ".join(terms)


def build_zscore_string(target_short: str, mu_r: float, sigma_r: float) -> str:
    op = "-" if mu_r >= 0 else "+"
    return f"Z([{target_short}]) = (Actual([{target_short}]) - Expected([{target_short}]) {op} {abs(mu_r):.6f}) / {sigma_r:.6f}"


def get_row_at_ts(df: pd.DataFrame, ts_str: str) -> pd.Series:
    ts = pd.to_datetime(ts_str, utc=True)
    if ts in df.index:
        row = df.loc[ts]
        return row.iloc[0] if isinstance(row, pd.DataFrame) else row
    idx = df.index.get_indexer([ts], method="nearest")[0]
    return df.iloc[idx]


def main():
    print("Loading telemetry data (read-only) and trained CorrelationDigitalTwin model...")
    df = pd.read_parquet(DATA_PATH)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    elif df.index.tz is None:
        df.index = df.index.tz_localize("UTC")

    twin_data = joblib.load(MODEL_PATH)

    models = twin_data["models"]
    peer_map = twin_data["peer_map"]
    residual_means = twin_data["residual_means"]
    residual_stds = twin_data["residual_stds"]
    sys_thresh = twin_data["system_anomaly_threshold"]

    # Compute correlation matrices
    numeric_df = df.select_dtypes(include=[np.number]).dropna(axis=1, how="all")
    split_idx = int(len(numeric_df) * 0.70)
    train_df = numeric_df.iloc[:split_idx]

    print("Computing Pearson correlation matrices...")
    corr_full = numeric_df.corr(method="pearson")
    corr_train = train_df.corr(method="pearson")

    # Compute baseline R2 for each sensor model on train_df
    r2_scores = {}
    for target, model in models.items():
        peers = peer_map.get(target, [])
        if not peers or target not in train_df.columns:
            r2_scores[target] = np.nan
            continue
        sub_df = train_df[[target] + peers].dropna()
        if len(sub_df) < 10:
            r2_scores[target] = np.nan
            continue
        X = sub_df[peers]
        y = sub_df[target].values
        r2_scores[target] = float(model.score(X, y))

    wb = openpyxl.Workbook()
    default_ws = wb.active

    # Styles
    title_font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    section_font = Font(name="Calibri", size=11, bold=True, color="1F4E79")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=10, bold=True)
    regular_font = Font(name="Calibri", size=10)
    formula_font = Font(name="Consolas", size=10, bold=True, color="0B5394")
    calc_font = Font(name="Calibri", size=10, bold=True, color="9C0006")
    ok_font = Font(name="Calibri", size=10, bold=True, color="006100")

    title_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
    subhdr_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    formula_fill = PatternFill(start_color="F2F4F8", end_color="F2F4F8", fill_type="solid")
    alert_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    ok_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    zebra_fill = PatternFill(start_color="F9FAFC", end_color="F9FAFC", fill_type="solid")

    thin_side = Side(border_style="thin", color="D9D9D9")
    grid_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    # =========================================================================
    # SHEET 1: Case_1_2_3_Formulas
    # =========================================================================
    ws1 = wb.create_sheet(title="Case_1_2_3_Formulas")
    ws1.views.sheetView[0].showGridLines = True

    ws1.merge_cells("A1:K1")
    ws1["A1"] = "GT-2420A CORRELATION DIGITAL TWIN — MATHEMATICAL PREDICTION FORMULAS (CASES 1, 2 & 3)"
    ws1["A1"].font = title_font
    ws1["A1"].fill = title_fill
    ws1["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[1].height = 28

    # Universal Governing Equations Block
    ws1.merge_cells("A3:K3")
    ws1["A3"] = "1. UNIVERSAL MATHEMATICAL FRAMEWORK (APPLIES TO ALL 158 SENSORS)"
    ws1["A3"].font = section_font
    ws1["A3"].fill = subhdr_fill

    framework_rows = [
        ("Step 1: Expected Baseline Formula", "Ŷ_i(t) = β₀ + β₁·X₁(t) + β₂·X₂(t) + β₃·X₃(t) + β₄·X₄(t) + β₅·X₅(t)", "Ridge Regression linear combination of the top k=5 most correlated peer sensors X₁..X₅."),
        ("Step 2: Residual Deviation Formula", "r_i(t) = Y_actual,i(t) - Ŷ_i(t)", "Instantaneous physical deviation (°C, bar, mm/s, etc.) between actual sensor reading and peer-predicted baseline."),
        ("Step 3: Standardized Z-Score Formula", "Z_i(t) = ( r_i(t) - μ_r,i ) / σ_r,i", "Normalizes the residual using healthy training baseline mean (μ_r,i) and standard deviation (σ_r,i)."),
        ("Step 4: Sensor Anomaly Trigger Rule", "|Z_i(t)| >= 3.0 (Warning)   |   |Z_i(t)| >= 4.0 (Critical Fault)", "Triggers early warning as soon as peer correlation breaks, before absolute DCS trip limits are breached."),
        ("Step 5: System SPE & Attribution (SCI%)", f"SPE(t) = Σ Z_j(t)²  (Threshold = {sys_thresh:.2f})   |   SCI_i(t) = [Z_i(t)² / SPE(t)] × 100%", "System-wide Squared Prediction Error and exact percentage root-cause isolation per sensor.")
    ]
    for idx, (step_name, eq_str, desc_str) in enumerate(framework_rows, start=4):
        ws1.cell(row=idx, column=1, value=step_name).font = bold_font
        ws1.merge_cells(start_row=idx, start_column=2, end_row=idx, end_column=5)
        c_eq = ws1.cell(row=idx, column=2, value=eq_str)
        c_eq.font = formula_font
        c_eq.fill = formula_fill
        ws1.merge_cells(start_row=idx, start_column=6, end_row=idx, end_column=11)
        ws1.cell(row=idx, column=6, value=desc_str).font = regular_font
        for col_i in range(1, 12):
            ws1.cell(row=idx, column=col_i).border = grid_border

    cases_meta = [
        {
            "case_num": 1,
            "title": "CASE 1: EXHAUST TEMPERATURE 7 — BURNER NOZZLE COKING / FLAMEOUT PLUNGE (2025-12-26)",
            "target": r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 7",
            "normal_ts": "2025-12-26 22:30:00",
            "peak_ts": "2025-12-26 23:12:00",
            "dcs_formula": "TTXS = MAX(Exhaust Temp 1..13) - MIN(Exhaust Temp 1..13)   [DCS Alarm >= 55.0 °C | DCS Trip >= 80.0 °C]",
            "lead_time": "Digital Twin Trigger at 23:10 UTC (SPE=18,949 > 732) before 23:11 UTC Spread Trip (TTXS=207.8°C) & 23:12 Flameout (158.5°C)",
        },
        {
            "case_num": 2,
            "title": "CASE 2: COMPRESSOR JOURNAL BEARING TEMPERATURE 4 — BABBITT FRICTION SURGE (2026-10-02)",
            "target": r"MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Journal Bearing Temperature 4",
            "normal_ts": "2026-10-02 05:00:00",
            "peak_ts": "2026-10-02 07:42:00",
            "dcs_formula": "BT_4 >= 140.3 °C (DCS BT_HH High-High Trip Limit)   |   API 670 Babbitt Softening Limit = 115.0 °C",
            "lead_time": "1h 42m Actual Early Warning (Trigger at 06:00 UTC, SPE=42,082 > 732; DCS BT_HH Breach to 795.6°C at 07:42 UTC)",
        },
        {
            "case_num": 3,
            "title": "CASE 3: EXHAUST TEMPERATURE 2 — COMBUSTION CAN HOT-STREAK DURING DELOAD (2026-01-05)",
            "target": r"MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 2",
            "normal_ts": "2026-01-05 01:00:00",
            "peak_ts": "2026-01-05 01:25:00",
            "dcs_formula": "TTXS = MAX(Exhaust Temp 1..13) - MIN(Exhaust Temp 1..13)   [DCS Alarm >= 55.0 °C | DCS Trip >= 80.0 °C]",
            "lead_time": "62 min before DCS Spread Alarm (02:27 UTC, 61.0°C) & 84 min before DCS Spread Trip (02:49 UTC, 80.6°C)",
        },
    ]

    df_ffill = df.ffill().bfill()
    curr_row = 11
    for case in cases_meta:
        target = case["target"]
        t_short = short_label(target)
        model = models[target]
        peers = peer_map[target]
        intercept = float(model.intercept_)
        coefs = [float(c) for c in model.coef_]
        mu_r = float(residual_means[target])
        sigma_r = float(residual_stds[target])
        r2 = r2_scores.get(target, np.nan)

        norm_row = get_row_at_ts(df_ffill, case["normal_ts"])
        peak_row = get_row_at_ts(df_ffill, case["peak_ts"])

        # Section Banner
        ws1.merge_cells(start_row=curr_row, start_column=1, end_row=curr_row, end_column=11)
        ws1.cell(row=curr_row, column=1, value=f"2.{case['case_num']} {case['title']}").font = title_font
        ws1.cell(row=curr_row, column=1).fill = header_fill
        ws1.row_dimensions[curr_row].height = 22
        curr_row += 1

        eq_expected = build_formula_string(t_short, intercept, peers, coefs, use_short=True)
        eq_zscore = build_zscore_string(t_short, mu_r, sigma_r)

        info_lines = [
            ("Target Sensor Path", target, f"Baseline R² = {r2:.4f}"),
            ("Expected Value Formula (Ŷ)", eq_expected, f"Intercept β₀ = {intercept:.6f}"),
            ("Z-Score Formula (Z)", eq_zscore, f"μ_r = {mu_r:.6f}, σ_r = {sigma_r:.6f}"),
            ("DCS Protection Formula", case["dcs_formula"], case["lead_time"]),
        ]
        for lbl, val_str, right_note in info_lines:
            ws1.cell(row=curr_row, column=1, value=lbl).font = bold_font
            ws1.merge_cells(start_row=curr_row, start_column=2, end_row=curr_row, end_column=8)
            c_v = ws1.cell(row=curr_row, column=2, value=val_str)
            c_v.font = formula_font if "Formula" in lbl else regular_font
            if "Formula" in lbl:
                c_v.fill = formula_fill
            ws1.merge_cells(start_row=curr_row, start_column=9, end_row=curr_row, end_column=11)
            ws1.cell(row=curr_row, column=9, value=right_note).font = bold_font
            for col_i in range(1, 12):
                ws1.cell(row=curr_row, column=col_i).border = grid_border
            curr_row += 1

        # Table Header for Peer Coefficients & Live Excel Calculator
        headers = [
            "Term / Variable",
            "Peer Sensor Short Name",
            "Full PI Tag Path",
            "Train Pearson r",
            "Full Pearson r",
            "Ridge Weight (β_i)",
            f"Normal Value ({case['normal_ts']} UTC)",
            "Normal Term Contribution (β_i × X_i)",
            f"Event Value ({case['peak_ts']} UTC)",
            "Event Term Contribution (β_i × X_i)",
            "Physical Role in Formula"
        ]
        for col_i, h_text in enumerate(headers, start=1):
            c = ws1.cell(row=curr_row, column=col_i, value=h_text)
            c.font = header_font
            c.fill = header_fill
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = grid_border
        ws1.row_dimensions[curr_row].height = 24
        curr_row += 1

        # Row 0: Intercept β₀
        intercept_row = curr_row
        ws1.cell(row=curr_row, column=1, value="β₀ (Intercept)").font = bold_font
        ws1.cell(row=curr_row, column=2, value="Constant Offset").font = regular_font
        ws1.cell(row=curr_row, column=3, value="N/A (Ridge Regression Intercept)").font = regular_font
        ws1.cell(row=curr_row, column=4, value="-").alignment = Alignment(horizontal="center")
        ws1.cell(row=curr_row, column=5, value="-").alignment = Alignment(horizontal="center")
        c_b0 = ws1.cell(row=curr_row, column=6, value=intercept)
        c_b0.number_format = "0.000000"
        c_b0.font = bold_font
        ws1.cell(row=curr_row, column=7, value=1.0).number_format = "0.0"
        c_norm_b0 = ws1.cell(row=curr_row, column=8, value=f"=F{curr_row}*G{curr_row}")
        c_norm_b0.number_format = "0.0000"
        ws1.cell(row=curr_row, column=9, value=1.0).number_format = "0.0"
        c_peak_b0 = ws1.cell(row=curr_row, column=10, value=f"=F{curr_row}*I{curr_row}")
        c_peak_b0.number_format = "0.0000"
        ws1.cell(row=curr_row, column=11, value="Baseline Offset").font = regular_font
        for col_i in range(1, 12):
            ws1.cell(row=curr_row, column=col_i).border = grid_border
        curr_row += 1

        # Rows 1..5: Peers
        for p_idx, (p_path, coef_val) in enumerate(zip(peers, coefs), start=1):
            p_short = short_label(p_path)
            r_tr = float(corr_train.loc[target, p_path]) if p_path in corr_train.columns else np.nan
            r_fl = float(corr_full.loc[target, p_path]) if p_path in corr_full.columns else np.nan
            val_norm = float(norm_row[p_path]) if not pd.isna(norm_row[p_path]) else 0.0
            val_peak = float(peak_row[p_path]) if not pd.isna(peak_row[p_path]) else 0.0

            ws1.cell(row=curr_row, column=1, value=f"X_{p_idx} (Peer {p_idx})").font = bold_font
            ws1.cell(row=curr_row, column=2, value=p_short).font = bold_font
            ws1.cell(row=curr_row, column=3, value=p_path).font = regular_font

            c_rtr = ws1.cell(row=curr_row, column=4, value=r_tr)
            c_rtr.number_format = "0.0000"
            c_rfl = ws1.cell(row=curr_row, column=5, value=r_fl)
            c_rfl.number_format = "0.0000"
            c_cf = ws1.cell(row=curr_row, column=6, value=coef_val)
            c_cf.number_format = "0.000000"
            c_cf.font = bold_font

            c_vn = ws1.cell(row=curr_row, column=7, value=val_norm)
            c_vn.number_format = "0.000"
            c_tn = ws1.cell(row=curr_row, column=8, value=f"=F{curr_row}*G{curr_row}")
            c_tn.number_format = "0.0000"

            c_vp = ws1.cell(row=curr_row, column=9, value=val_peak)
            c_vp.number_format = "0.000"
            c_tp = ws1.cell(row=curr_row, column=10, value=f"=F{curr_row}*I{curr_row}")
            c_tp.number_format = "0.0000"

            ws1.cell(row=curr_row, column=11, value=f"Correlated Peer #{p_idx} (Weight={coef_val:+.4f})").font = regular_font
            for col_i in range(1, 12):
                ws1.cell(row=curr_row, column=col_i).border = grid_border
            curr_row += 1
        last_peer_row = curr_row - 1

        actual_norm = float(norm_row[target]) if not pd.isna(norm_row[target]) else 0.0
        actual_peak = float(peak_row[target]) if not pd.isna(peak_row[target]) else 0.0

        # Row: Expected Value Ŷ (Live Excel Formula =SUM(H...:H...))
        exp_row = curr_row
        ws1.cell(row=curr_row, column=1, value="Ŷ (Expected Value)").font = bold_font
        ws1.cell(row=curr_row, column=2, value=f"Predicted {t_short}").font = bold_font
        ws1.cell(row=curr_row, column=3, value=f"=SUM(H{intercept_row}:H{last_peer_row})  [Live Excel Formula]").font = formula_font
        ws1.cell(row=curr_row, column=7, value="Ŷ_normal =").alignment = Alignment(horizontal="right")
        c_exp_n = ws1.cell(row=curr_row, column=8, value=f"=SUM(H{intercept_row}:H{last_peer_row})")
        c_exp_n.number_format = "0.000"
        c_exp_n.font = bold_font
        c_exp_n.fill = ok_fill
        ws1.cell(row=curr_row, column=9, value="Ŷ_event =").alignment = Alignment(horizontal="right")
        c_exp_p = ws1.cell(row=curr_row, column=10, value=f"=SUM(J{intercept_row}:J{last_peer_row})")
        c_exp_p.number_format = "0.000"
        c_exp_p.font = bold_font
        c_exp_p.fill = subhdr_fill
        ws1.cell(row=curr_row, column=11, value="Digital Twin Expected Value (°C)").font = bold_font
        for col_i in range(1, 12):
            ws1.cell(row=curr_row, column=col_i).border = grid_border
        curr_row += 1

        # Row: Actual Sensor Reading Y_actual
        act_row = curr_row
        ws1.cell(row=curr_row, column=1, value="Y (Actual Value)").font = bold_font
        ws1.cell(row=curr_row, column=2, value=f"Actual {t_short}").font = bold_font
        ws1.cell(row=curr_row, column=3, value="Measured PI Sensor Telemetry (°C)").font = regular_font
        ws1.cell(row=curr_row, column=7, value="Y_normal =").alignment = Alignment(horizontal="right")
        c_act_n = ws1.cell(row=curr_row, column=8, value=actual_norm)
        c_act_n.number_format = "0.000"
        c_act_n.font = bold_font
        ws1.cell(row=curr_row, column=9, value="Y_event =").alignment = Alignment(horizontal="right")
        c_act_p = ws1.cell(row=curr_row, column=10, value=actual_peak)
        c_act_p.number_format = "0.000"
        c_act_p.font = calc_font
        c_act_p.fill = alert_fill
        ws1.cell(row=curr_row, column=11, value="Actual Measured Reading (°C)").font = bold_font
        for col_i in range(1, 12):
            ws1.cell(row=curr_row, column=col_i).border = grid_border
        curr_row += 1

        # Row: Residual r = Y - Ŷ
        res_row = curr_row
        ws1.cell(row=curr_row, column=1, value="r (Residual Deviation)").font = bold_font
        ws1.cell(row=curr_row, column=2, value="Y_actual - Ŷ_expected").font = bold_font
        ws1.cell(row=curr_row, column=3, value=f"=H{act_row}-H{exp_row}  [Live Excel Formula]").font = formula_font
        ws1.cell(row=curr_row, column=4, value=mu_r).number_format = "0.000000"
        ws1.cell(row=curr_row, column=5, value=sigma_r).number_format = "0.000000"
        ws1.cell(row=curr_row, column=6, value="← Col D=μ_r, Col E=σ_r").font = regular_font
        ws1.cell(row=curr_row, column=7, value="r_normal =").alignment = Alignment(horizontal="right")
        c_res_n = ws1.cell(row=curr_row, column=8, value=f"=H{act_row}-H{exp_row}")
        c_res_n.number_format = "+0.000;-0.000;0.000"
        c_res_n.font = bold_font
        ws1.cell(row=curr_row, column=9, value="r_event =").alignment = Alignment(horizontal="right")
        c_res_p = ws1.cell(row=curr_row, column=10, value=f"=J{act_row}-J{exp_row}")
        c_res_p.number_format = "+0.000;-0.000;0.000"
        c_res_p.font = calc_font
        c_res_p.fill = alert_fill
        ws1.cell(row=curr_row, column=11, value="Physical Residual Deviation (°C)").font = bold_font
        for col_i in range(1, 12):
            ws1.cell(row=curr_row, column=col_i).border = grid_border
        curr_row += 1

        # Row: Z-Score = (r - μ_r) / σ_r
        z_row = curr_row
        ws1.cell(row=curr_row, column=1, value="Z (Anomaly Z-Score)").font = bold_font
        ws1.cell(row=curr_row, column=2, value="(r - μ_r) / σ_r").font = bold_font
        ws1.cell(row=curr_row, column=3, value=f"=(H{res_row}-D{res_row})/E{res_row}  [Live Excel Formula]").font = formula_font
        ws1.cell(row=curr_row, column=7, value="Z_normal =").alignment = Alignment(horizontal="right")
        c_zn = ws1.cell(row=curr_row, column=8, value=f"=(H{res_row}-D{res_row})/E{res_row}")
        c_zn.number_format = "+0.00;-0.00;0.00"
        c_zn.font = ok_font
        c_zn.fill = ok_fill
        ws1.cell(row=curr_row, column=9, value="Z_event =").alignment = Alignment(horizontal="right")
        c_zp = ws1.cell(row=curr_row, column=10, value=f"=(J{res_row}-D{res_row})/E{res_row}")
        c_zp.number_format = "+0.00;-0.00;0.00"
        c_zp.font = calc_font
        c_zp.fill = alert_fill
        ws1.cell(row=curr_row, column=11, value=f"=IF(ABS(J{z_row})>=4.0, \"CRITICAL ANOMALY (|Z|>=4)\", IF(ABS(J{z_row})>=3.0, \"WARNING (|Z|>=3)\", \"HEALTHY\"))").font = calc_font
        for col_i in range(1, 12):
            ws1.cell(row=curr_row, column=col_i).border = grid_border
        curr_row += 2

    col_widths_s1 = [24, 34, 52, 15, 15, 18, 24, 24, 24, 24, 38]
    for idx, w in enumerate(col_widths_s1, start=1):
        ws1.column_dimensions[get_column_letter(idx)].width = w

    # =========================================================================
    # SHEET 2: All_158_Prediction_Formulas
    # =========================================================================
    ws2 = wb.create_sheet(title="All_158_Prediction_Formulas")
    ws2.views.sheetView[0].showGridLines = True

    ws2.merge_cells("A1:Z1")
    ws2["A1"] = "GT-2420A COMPLETE DIGITAL TWIN CATALOG — ALL 158 SENSOR CORRELATIONS & MATHEMATICAL PREDICTION FORMULAS"
    ws2["A1"].font = title_font
    ws2["A1"].fill = title_fill
    ws2["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 28

    s2_headers = [
        "Sensor #",
        "Subsystem",
        "Subcategory",
        "Sensor Short Name",
        "Full PI Tag Path",
        "Baseline R² Fit",
        "Intercept (β₀)",
        "Residual Mean (μ_r)",
        "Residual Std (σ_r)",
        "Expected Value Mathematical Formula (Ŷ = β₀ + Σ β_i·X_i)",
        "Standardized Anomaly Z-Score Formula (Z = (Y - Ŷ - μ_r) / σ_r)",
        "Peer 1 Name", "Peer 1 Corr (r)", "Peer 1 Weight (β₁)",
        "Peer 2 Name", "Peer 2 Corr (r)", "Peer 2 Weight (β₂)",
        "Peer 3 Name", "Peer 3 Corr (r)", "Peer 3 Weight (β₃)",
        "Peer 4 Name", "Peer 4 Corr (r)", "Peer 4 Weight (β₄)",
        "Peer 5 Name", "Peer 5 Corr (r)", "Peer 5 Weight (β₅)",
    ]

    for col_i, h in enumerate(s2_headers, start=1):
        c = ws2.cell(row=2, column=col_i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border
    ws2.row_dimensions[2].height = 26

    all_sensors = sorted(numeric_df.columns.tolist())
    highlight_targets = {m["target"] for m in cases_meta}

    for s_idx, sensor in enumerate(all_sensors, start=1):
        row_num = s_idx + 2
        sub, subcat, tag = parse_tag_parts(sensor)
        is_case = sensor in highlight_targets
        row_fill = alert_fill if is_case else (zebra_fill if s_idx % 2 == 0 else None)

        ws2.cell(row=row_num, column=1, value=s_idx).alignment = Alignment(horizontal="center")
        ws2.cell(row=row_num, column=2, value=sub)
        ws2.cell(row=row_num, column=3, value=subcat)
        c_tag = ws2.cell(row=row_num, column=4, value=tag)
        c_tag.font = bold_font
        ws2.cell(row=row_num, column=5, value=sensor)

        if sensor in models:
            model = models[sensor]
            peers = peer_map.get(sensor, [])
            intercept = float(model.intercept_)
            coefs = [float(x) for x in model.coef_]
            mu_r = float(residual_means[sensor])
            sigma_r = float(residual_stds[sensor])
            r2 = r2_scores.get(sensor, np.nan)

            c_r2 = ws2.cell(row=row_num, column=6, value=r2 if not np.isnan(r2) else 0.0)
            c_r2.number_format = "0.0000"
            c_b0 = ws2.cell(row=row_num, column=7, value=intercept)
            c_b0.number_format = "0.000000"
            c_mu = ws2.cell(row=row_num, column=8, value=mu_r)
            c_mu.number_format = "0.000000"
            c_sd = ws2.cell(row=row_num, column=9, value=sigma_r)
            c_sd.number_format = "0.000000"

            eq_str = build_formula_string(tag, intercept, peers, coefs, use_short=True)
            z_str = build_zscore_string(tag, mu_r, sigma_r)

            c_eq = ws2.cell(row=row_num, column=10, value=eq_str)
            c_eq.font = formula_font
            c_z = ws2.cell(row=row_num, column=11, value=z_str)
            c_z.font = formula_font

            for p_i in range(5):
                base_col = 12 + p_i * 3
                if p_i < len(peers):
                    p_path = peers[p_i]
                    p_short = short_label(p_path)
                    p_r = float(corr_train.loc[sensor, p_path]) if p_path in corr_train.columns else np.nan
                    p_b = coefs[p_i]
                    ws2.cell(row=row_num, column=base_col, value=p_short)
                    cr = ws2.cell(row=row_num, column=base_col + 1, value=p_r)
                    cr.number_format = "0.0000"
                    cb = ws2.cell(row=row_num, column=base_col + 2, value=p_b)
                    cb.number_format = "0.000000"
                else:
                    ws2.cell(row=row_num, column=base_col, value="-")
                    ws2.cell(row=row_num, column=base_col + 1, value="-")
                    ws2.cell(row=row_num, column=base_col + 2, value="-")
        else:
            ws2.cell(row=row_num, column=6, value="N/A")
            ws2.cell(row=row_num, column=10, value="No Peer Model (Insufficient Variance / Constant Tag)")

        for col_i in range(1, len(s2_headers) + 1):
            cell = ws2.cell(row=row_num, column=col_i)
            cell.border = grid_border
            if row_fill and col_i not in (10, 11):
                cell.fill = row_fill

    ws2.freeze_panes = "E3"
    ws2.auto_filter.ref = f"A2:{get_column_letter(len(s2_headers))}{len(all_sensors)+2}"

    s2_widths = [
        10, 22, 22, 34, 52, 14, 15, 16, 16, 95, 72,
        28, 13, 15, 28, 13, 15, 28, 13, 15, 28, 13, 15, 28, 13, 15
    ]
    for idx, w in enumerate(s2_widths, start=1):
        ws2.column_dimensions[get_column_letter(idx)].width = w

    # =========================================================================
    # SHEET 3: All_Pairwise_Correlations
    # =========================================================================
    ws3 = wb.create_sheet(title="All_Pairwise_Correlations")
    ws3.views.sheetView[0].showGridLines = True

    ws3.merge_cells("A1:K1")
    ws3["A1"] = "GT-2420A RANKED PAIRWISE SENSOR CORRELATIONS (|r| >= 0.30 ACROSS TURBINE SUBSYSTEMS)"
    ws3["A1"].font = title_font
    ws3["A1"].fill = title_fill
    ws3["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws3.row_dimensions[1].height = 28

    s3_headers = [
        "Rank",
        "Subsystem A",
        "Sensor A Short Name",
        "Sensor A Full Path",
        "Subsystem B",
        "Sensor B Short Name",
        "Sensor B Full Path",
        "Baseline Pearson r (Train)",
        "Full Dataset Pearson r",
        "Absolute |r| (Train)",
        "Correlation Scope & Strength"
    ]
    for col_i, h in enumerate(s3_headers, start=1):
        c = ws3.cell(row=2, column=col_i, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border
    ws3.row_dimensions[2].height = 24

    pairs = []
    cols = corr_train.columns.tolist()
    n_cols = len(cols)
    for i in range(n_cols):
        for j in range(i + 1, n_cols):
            s_a, s_b = cols[i], cols[j]
            r_tr = corr_train.iloc[i, j]
            r_fl = corr_full.iloc[i, j]
            if pd.isna(r_tr):
                continue
            abs_r = abs(float(r_tr))
            if abs_r >= 0.30:
                pairs.append((s_a, s_b, float(r_tr), float(r_fl), abs_r))

    pairs.sort(key=lambda x: x[4], reverse=True)
    print(f"Found {len(pairs)} sensor pairs with |r| >= 0.30. Writing to Sheet 3...")

    for rank_idx, (s_a, s_b, r_tr, r_fl, abs_r) in enumerate(pairs, start=1):
        row_num = rank_idx + 2
        sub_a, _, tag_a = parse_tag_parts(s_a)
        sub_b, _, tag_b = parse_tag_parts(s_b)
        scope = "Intra-Subsystem" if sub_a == sub_b else "Cross-Subsystem"
        direction = "Positive" if r_tr >= 0 else "Negative"
        strength = "Very Strong" if abs_r >= 0.85 else ("Strong" if abs_r >= 0.70 else ("Moderate" if abs_r >= 0.50 else "Weak-Moderate"))

        ws3.cell(row=row_num, column=1, value=rank_idx).alignment = Alignment(horizontal="center")
        ws3.cell(row=row_num, column=2, value=sub_a)
        ws3.cell(row=row_num, column=3, value=tag_a).font = bold_font
        ws3.cell(row=row_num, column=4, value=s_a)
        ws3.cell(row=row_num, column=5, value=sub_b)
        ws3.cell(row=row_num, column=6, value=tag_b).font = bold_font
        ws3.cell(row=row_num, column=7, value=s_b)

        c_tr = ws3.cell(row=row_num, column=8, value=r_tr)
        c_tr.number_format = "0.0000"
        c_fl = ws3.cell(row=row_num, column=9, value=r_fl)
        c_fl.number_format = "0.0000"
        c_ab = ws3.cell(row=row_num, column=10, value=abs_r)
        c_ab.number_format = "0.0000"
        ws3.cell(row=row_num, column=11, value=f"{strength} {direction} ({scope})")

        for col_i in range(1, 12):
            ws3.cell(row=row_num, column=col_i).border = grid_border

    ws3.freeze_panes = "A3"
    ws3.auto_filter.ref = f"A2:K{len(pairs)+2}"
    s3_widths = [8, 22, 34, 52, 22, 34, 52, 18, 18, 16, 36]
    for idx, w in enumerate(s3_widths, start=1):
        ws3.column_dimensions[get_column_letter(idx)].width = w

    # =========================================================================
    # SHEET 4: Full_158x158_Matrix
    # =========================================================================
    ws4 = wb.create_sheet(title="Full_158x158_Matrix")
    ws4.views.sheetView[0].showGridLines = True

    ws4.cell(row=1, column=1, value="Sensor Short Name").font = header_font
    ws4.cell(row=1, column=1).fill = header_fill
    ws4.cell(row=1, column=2, value="Subsystem").font = header_font
    ws4.cell(row=1, column=2).fill = header_fill

    matrix_cols = corr_train.columns.tolist()
    for c_idx, col_path in enumerate(matrix_cols, start=3):
        c = ws4.cell(row=1, column=c_idx, value=short_label(col_path))
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="bottom", textRotation=90)
    ws4.row_dimensions[1].height = 110

    for r_idx, row_path in enumerate(matrix_cols, start=2):
        sub_r, _, tag_r = parse_tag_parts(row_path)
        c_name = ws4.cell(row=r_idx, column=1, value=tag_r)
        c_name.font = bold_font
        ws4.cell(row=r_idx, column=2, value=sub_r)
        for c_idx, col_path in enumerate(matrix_cols, start=3):
            val = corr_train.iloc[r_idx - 2, c_idx - 3]
            cell = ws4.cell(row=r_idx, column=c_idx, value=float(val) if not pd.isna(val) else 0.0)
            cell.number_format = "0.00"

    ws4.freeze_panes = "C2"
    ws4.column_dimensions["A"].width = 34
    ws4.column_dimensions["B"].width = 22
    for c_idx in range(3, len(matrix_cols) + 3):
        ws4.column_dimensions[get_column_letter(c_idx)].width = 5.5

    last_col_letter = get_column_letter(len(matrix_cols) + 2)
    last_row_num = len(matrix_cols) + 1
    color_scale = ColorScaleRule(
        start_type="num", start_value=-1.0, start_color="F8696B",
        mid_type="num", mid_value=0.0, mid_color="FFFFFF",
        end_type="num", end_value=1.0, end_color="5A8AC6"
    )
    ws4.conditional_formatting.add(f"C2:{last_col_letter}{last_row_num}", color_scale)

    wb.remove(default_ws)

    OUTPUT_REPORTS_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_ROOT_XLSX)
    shutil.copy2(OUTPUT_ROOT_XLSX, OUTPUT_REPORTS_XLSX)
    print(f"Saved Excel workbook successfully to:\n  1) {OUTPUT_ROOT_XLSX}\n  2) {OUTPUT_REPORTS_XLSX}")

    print("\n=== SUMMARY OF CASE 1, 2, 3 FORMULAS ===")
    for case in cases_meta:
        t = case["target"]
        t_s = short_label(t)
        m = models[t]
        p = peer_map[t]
        b0 = float(m.intercept_)
        bs = [float(x) for x in m.coef_]
        mu = float(residual_means[t])
        sd = float(residual_stds[t])
        print(f"\nCase {case['case_num']} ({t_s}):")
        print("  " + build_formula_string(t_s, b0, p, bs, use_short=True))
        print("  " + build_zscore_string(t_s, mu, sd))


if __name__ == "__main__":
    main()
