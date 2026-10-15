"""Generate updated publication-grade PNG trend figures and interactive Chart.js HTML dashboard
visualizing the 3 key historical anomaly events detected on GT-2420A, with explicit DCS alarm and
trip limits, exact timestamps, and rigorous physical definitions.
"""

from pathlib import Path
import json
import sqlite3
import shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from src.module3_prediction.correlation_digital_twin import CorrelationDigitalTwin

plt.rcParams["font.sans-serif"] = "DejaVu Sans"
plt.rcParams["axes.edgecolor"] = "#333333"
plt.rcParams["axes.linewidth"] = 0.8

# Load Digital Twin Model and Telemetry
print("Loading Digital Twin model and Parquet telemetry...")
twin = CorrelationDigitalTwin.load_model("models/gt2420a_digital_twin.pkl")
df = pd.read_parquet("data/historical_data.parquet")

# Ensure index is datetime
if not isinstance(df.index, pd.DatetimeIndex):
    df.index = pd.to_datetime(df.index)

figures_dir = Path("reports/figures")
figures_dir.mkdir(parents=True, exist_ok=True)
artifact_dir = Path(r"C:\Users\Fuad\.gemini\antigravity-cli\brain\ec640fef-7175-401d-9956-eb1e8687274e")

# All exhaust thermocouple tags
exhaust_cols = [c for c in df.columns if "Exhaust Temperature" in c]
exhaust_cols.sort()

# -------------------------------------------------------------
# EVENT 1: Exhaust Temperature 7 (Burner Coking / Flame Degradation)
# -------------------------------------------------------------
print("Generating Event 1 visualization (Exhaust Temperature 7 & TTXS Limits)...")
e1_start = "2025-12-26 22:30:00"
e1_end = "2025-12-27 00:30:00"
tc7_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Gas Turbine Engine\\Exhaust Temperature 7"
tc1_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Gas Turbine Engine\\Exhaust Temperature 1"
tc6_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Gas Turbine Engine\\Exhaust Temperature 6"
tc8_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Gas Turbine Engine\\Exhaust Temperature 8"

full_w1 = df.loc[e1_start:e1_end].copy()
exp1 = twin.predict_expected_values(full_w1)
w1 = full_w1[[tc7_col, tc1_col, tc6_col, tc8_col]].dropna(how="all")

# Calculate exact Spread TTXS = max(TT) - min(TT) across all 13 thermocouples
all_ex1 = full_w1[exhaust_cols]
ttxs_1 = all_ex1.max(axis=1) - all_ex1.min(axis=1)

t_alarm_1 = pd.to_datetime("2025-12-26 23:10:00+00:00")
t_trip_1 = pd.to_datetime("2025-12-26 23:11:00+00:00")  # TTXS reaches 207.8°C (>80°C limit)
t_plunge_1 = pd.to_datetime("2025-12-26 23:12:00+00:00") # Peak plunge to 158.5°C, TTXS=640.8°C

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(13, 10), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.5, 1.0]})
fig.patch.set_facecolor("#0f172a")
for ax in (ax1, ax2, ax3):
    ax.set_facecolor("#1e293b")
    ax.grid(True, linestyle="--", alpha=0.3, color="#94a3b8")
    ax.tick_params(colors="#cbd5e1", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#475569")

# Panel 1: Thermocouple Sensor Trends
ax1.plot(w1.index, w1[tc7_col], color="#ef4444", linewidth=2.5, label="Culprit: Exhaust Temp 7 (Actual)", zorder=4)
ax1.plot(w1.index, exp1[tc7_col], color="#38bdf8", linestyle="--", linewidth=1.8, label="Digital Twin Expected Baseline", zorder=3)
ax1.plot(w1.index, w1[tc1_col], color="#94a3b8", alpha=0.7, linewidth=1.2, label="Peer: Exhaust Temp 1")
ax1.plot(w1.index, w1[tc6_col], color="#a855f7", alpha=0.7, linewidth=1.2, label="Peer: Exhaust Temp 6")
ax1.plot(w1.index, w1[tc8_col], color="#3b82f6", alpha=0.7, linewidth=1.2, label="Peer: Exhaust Temp 8")

ax1.axvline(t_alarm_1, color="#f59e0b", linestyle="-.", linewidth=2, label="T_alarm: Early Advisory Trigger (23:10 UTC)", zorder=5)
ax1.axvline(t_plunge_1, color="#dc2626", linestyle=":", linewidth=2.2, label="T_peak: Severe Flameout Plunge 158.5°C (23:12 UTC)", zorder=5)

ax1.annotate("EARLY ADVISORY TRIGGER (23:10)\nAnomaly Score: 18,949 > 732\nPredicted: Spread Trip TTXS_ALM",
             xy=(mdates.date2num(t_alarm_1), 512),
             xytext=(mdates.date2num(t_alarm_1) - 0.035, 300),
             arrowprops=dict(facecolor="#f59e0b", edgecolor="#f59e0b", shrink=0.05, width=1.5, headwidth=6),
             color="#fef08a", fontweight="bold", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.4", fc="#78350f", ec="#f59e0b", lw=1.2))

ax1.annotate("FLAMEOUT DIVERGENCE (23:12)\nTemp 7 plunges to 158.5°C\nPeers rise to 799°C - 886°C",
             xy=(mdates.date2num(t_plunge_1), 158),
             xytext=(mdates.date2num(t_plunge_1) + 0.008, 160),
             arrowprops=dict(facecolor="#ef4444", edgecolor="#ef4444", shrink=0.05, width=1.5, headwidth=6),
             color="#fecaca", fontweight="bold", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.4", fc="#7f1d1d", ec="#ef4444", lw=1.2))

ax1.set_ylabel("Temperature (°C)", color="#e2e8f0", fontsize=10, fontweight="bold")
ax1.set_title("EVENT 1: Burner Nozzle Coking & Flame Degradation (Exhaust Temp 7)", color="#f8fafc", fontsize=12, fontweight="bold", pad=10)
ax1.legend(loc="upper left", facecolor="#0f172a", edgecolor="#475569", labelcolor="#e2e8f0", fontsize=8)

# Panel 2: Actual Exhaust Temperature Spread (TTXS) vs DCS Limits
ax2.plot(ttxs_1.index, ttxs_1, color="#ec4899", linewidth=2.2, label="Actual Exhaust Spread TTXS = max(TT) - min(TT)", zorder=4)
ax2.axhline(55.0, color="#f59e0b", linestyle="--", linewidth=1.5, label="DCS Spread Alarm Limit (TTXS_ALM = 55.0°C)", zorder=3)
ax2.axhline(80.0, color="#dc2626", linestyle="-", linewidth=1.8, label="DCS Spread Trip Limit (TTXS_TRIP = 80.0°C)", zorder=3)

ax2.axvline(t_alarm_1, color="#f59e0b", linestyle="-.", linewidth=1.5)
ax2.axvline(t_trip_1, color="#ef4444", linestyle="--", linewidth=1.8, label="T_trip: DCS Trip Limit Breach (23:11 UTC, TTXS=208°C)")
ax2.axvline(t_plunge_1, color="#dc2626", linestyle=":", linewidth=1.5)

ax2.annotate("DCS TRIP BREACH: 207.8°C at 23:11\nPeak Spread: 640.8°C at 23:12",
             xy=(mdates.date2num(t_trip_1), 208),
             xytext=(mdates.date2num(t_trip_1) - 0.038, 420),
             arrowprops=dict(facecolor="#dc2626", edgecolor="#dc2626", shrink=0.05, width=1.5, headwidth=6),
             color="#fecaca", fontweight="bold", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.4", fc="#7f1d1d", ec="#dc2626", lw=1.2))

ax2.set_ylabel("Spread TTXS (°C)", color="#e2e8f0", fontsize=10, fontweight="bold")
ax2.legend(loc="upper left", facecolor="#0f172a", edgecolor="#475569", labelcolor="#e2e8f0", fontsize=8)

# Panel 3: Culprit Residual Deviation
res1 = w1[tc7_col] - exp1[tc7_col]
ax3.plot(w1.index, res1, color="#f43f5e", linewidth=1.8, label="Culprit Temp 7 Residual Deviation (°C)")
ax3.fill_between(w1.index, 0, res1, color="#f43f5e", alpha=0.2)
ax3.axhline(0, color="#64748b", linestyle=":", linewidth=1)
ax3.axvline(t_alarm_1, color="#f59e0b", linestyle="-.", linewidth=1.5)
ax3.axvline(t_plunge_1, color="#dc2626", linestyle=":", linewidth=1.5)
ax3.set_ylabel("Residual (°C)", color="#e2e8f0", fontsize=9, fontweight="bold")
ax3.set_xlabel("Timestamp (UTC)", color="#cbd5e1", fontsize=10)
ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%b %d"))
ax3.legend(loc="lower left", facecolor="#0f172a", edgecolor="#475569", labelcolor="#e2e8f0", fontsize=8)

fig.tight_layout()
p1 = figures_dir / "event1_exhaust_temp7_coking.png"
fig.savefig(p1, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
plt.close(fig)
print(f"Saved: {p1}")


# -------------------------------------------------------------
# EVENT 2: Compressor Journal Bearing 4 Overheating
# -------------------------------------------------------------
print("Generating Event 2 visualization (Journal Bearing 4 & BT_HH Limits)...")
e2_start = "2026-10-02 04:00:00"
e2_end = "2026-10-02 10:00:00"
b4_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Compressor\\Compressor Journal Bearing Temperature 4"
b1_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Compressor\\Compressor Journal Bearing Temperature 1"
gw_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Gearbox\\Gearbox Wheel DE Journal Bearing Temperature 1"

full_w2 = df.loc[e2_start:e2_end].copy()
exp2 = twin.predict_expected_values(full_w2)
w2 = full_w2[[b4_col, b1_col, gw_col]].dropna(how="all")

t_alarm_2 = pd.to_datetime("2026-10-02 06:00:00+00:00")
t_trip_2 = pd.to_datetime("2026-10-02 07:42:00+00:00")
t_normal_2 = pd.to_datetime("2026-10-02 07:50:00+00:00")

bt_hh_limit = 140.3  # DCS High-High Trip Limit in operating_limits.db
bt_api_trip = 115.0  # Standard API 670 Babbitt Metal Trip threshold

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
fig.patch.set_facecolor("#0f172a")
for ax in (ax1, ax2):
    ax.set_facecolor("#1e293b")
    ax.grid(True, linestyle="--", alpha=0.3, color="#94a3b8")
    ax.tick_params(colors="#cbd5e1", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#475569")

# Panel 1: Bearing Trends & Limits
ax1.plot(w2.index, w2[b4_col], color="#ef4444", linewidth=2.5, label="Culprit: Bearing 4 Temp (Actual)", zorder=4)
ax1.plot(w2.index, exp2[b4_col], color="#38bdf8", linestyle="--", linewidth=1.8, label="Digital Twin Expected Baseline (28.4°C)", zorder=3)
ax1.plot(w2.index, w2[gw_col], color="#10b981", alpha=0.8, linewidth=1.4, label="Peer: Gearbox DE Bearing (Normal ~28°C)")
if b1_col in w2.columns and not w2[b1_col].isna().all():
    ax1.plot(w2.index, w2[b1_col], color="#94a3b8", alpha=0.7, linewidth=1.2, label="Peer: Bearing 1 Temp")

# DCS Limits
ax1.axhline(bt_hh_limit, color="#dc2626", linestyle="-", linewidth=1.8, label=f"DCS Trip Limit: BT_HH = {bt_hh_limit}°C", zorder=3)
ax1.axhline(bt_api_trip, color="#f59e0b", linestyle=":", linewidth=1.5, label=f"API 670 Babbitt Softening Trip ({bt_api_trip}°C)", zorder=3)

# Markers
ax1.axvline(t_alarm_2, color="#f59e0b", linestyle="-.", linewidth=2, label="T_alarm: Early Warning Trigger (06:00 UTC)", zorder=5)
ax1.axvline(t_trip_2, color="#dc2626", linestyle=":", linewidth=2.2, label="T_trip: DCS BT_HH Trip Breach to 795.6°C (07:42 UTC)", zorder=5)
ax1.axvspan(t_alarm_2, t_trip_2, color="#f59e0b", alpha=0.15, label="Actual Lead Time: 1h 42m (Catalog Horizon: 48.0h)")

ax1.annotate("EARLY ADVISORY TRIGGER (06:00 UTC)\nAnomaly Score: 42,082 > 732\nPredicted: Babbitt Metal Trip (BT_HH)\nCatalog Horizon: 48h | Actual Window: 1h 42m",
             xy=(mdates.date2num(t_alarm_2), 27.5),
             xytext=(mdates.date2num(t_alarm_2) - 0.045, 380),
             arrowprops=dict(facecolor="#f59e0b", edgecolor="#f59e0b", shrink=0.05, width=1.5, headwidth=6),
             color="#fef08a", fontweight="bold", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.4", fc="#78350f", ec="#f59e0b", lw=1.2))

ax1.annotate("DCS BT_HH BREACH & SURGE (07:42 UTC)\nTemperature reaches 795.58°C (Crosses 140.3°C)\nPeers stay normal at 28.5°C\nDuration: 8 min until reset at 07:50",
             xy=(mdates.date2num(t_trip_2), 795.6),
             xytext=(mdates.date2num(t_trip_2) - 0.075, 620),
             arrowprops=dict(facecolor="#ef4444", edgecolor="#ef4444", shrink=0.05, width=1.5, headwidth=6),
             color="#fecaca", fontweight="bold", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.4", fc="#7f1d1d", ec="#ef4444", lw=1.2))

ax1.set_ylabel("Temperature (°C)", color="#e2e8f0", fontsize=10, fontweight="bold")
ax1.set_title("EVENT 2: Bearing Babbitt Metal Friction Surge & DCS Trip Breach (Journal Bearing 4)", color="#f8fafc", fontsize=12, fontweight="bold", pad=10)
ax1.legend(loc="upper left", facecolor="#0f172a", edgecolor="#475569", labelcolor="#e2e8f0", fontsize=8)

# Panel 2: Residual Deviation
res2 = w2[b4_col] - exp2[b4_col]
ax2.plot(w2.index, res2, color="#f43f5e", linewidth=1.8, label="Bearing 4 Residual Deviation (+767.2°C at peak)")
ax2.fill_between(w2.index, 0, res2, color="#f43f5e", alpha=0.2)
ax2.axhline(0, color="#64748b", linestyle=":", linewidth=1)
ax2.axvline(t_alarm_2, color="#f59e0b", linestyle="-.", linewidth=1.5)
ax2.axvline(t_trip_2, color="#dc2626", linestyle=":", linewidth=1.5)
ax2.set_ylabel("Residual (°C)", color="#e2e8f0", fontsize=9, fontweight="bold")
ax2.set_xlabel("Timestamp (UTC)", color="#cbd5e1", fontsize=10)
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%b %d"))
ax2.legend(loc="upper left", facecolor="#0f172a", edgecolor="#475569", labelcolor="#e2e8f0", fontsize=8)

fig.tight_layout()
p2 = figures_dir / "event2_bearing4_babbitt_overheat.png"
fig.savefig(p2, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
plt.close(fig)
print(f"Saved: {p2}")


# -------------------------------------------------------------
# EVENT 3: Exhaust Temperature 2 (Combustion Can Hot Streak During Deload)
# -------------------------------------------------------------
print("Generating Event 3 visualization (Exhaust Temperature 2 & Spread Limits)...")
e3_start = "2026-01-05 01:00:00"
e3_end = "2026-01-05 04:00:00"
tc2_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Gas Turbine Engine\\Exhaust Temperature 2"
tc6_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Gas Turbine Engine\\Exhaust Temperature 6"
tc8_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Gas Turbine Engine\\Exhaust Temperature 8"
tc13_col = "MALAYSIA\\BORF\\GTG\\GT-2420A\\Gas Turbine Engine\\Exhaust Temperature 13"

full_w3 = df.loc[e3_start:e3_end].copy()
exp3 = twin.predict_expected_values(full_w3)
w3 = full_w3[[tc2_col, tc6_col, tc8_col, tc13_col]].dropna(how="all")

# Calculate exact Spread TTXS
all_ex3 = full_w3[exhaust_cols]
ttxs_3 = all_ex3.max(axis=1) - all_ex3.min(axis=1)

t_alarm_3 = pd.to_datetime("2026-01-05 01:35:00+00:00")
t_alarm_dcs_3 = pd.to_datetime("2026-01-05 02:27:00+00:00")  # TTXS reaches 61.0°C (>55°C alarm)
t_trip_dcs_3 = pd.to_datetime("2026-01-05 02:49:00+00:00")   # TTXS reaches 80.6°C (>80°C trip)
t_diverge_3 = pd.to_datetime("2026-01-05 02:30:00+00:00")    # Temp 2 hung at 370.4°C

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(13, 10), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.5, 1.0]})
fig.patch.set_facecolor("#0f172a")
for ax in (ax1, ax2, ax3):
    ax.set_facecolor("#1e293b")
    ax.grid(True, linestyle="--", alpha=0.3, color="#94a3b8")
    ax.tick_params(colors="#cbd5e1", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#475569")

# Panel 1: Thermocouple Trends
ax1.plot(w3.index, w3[tc2_col], color="#ef4444", linewidth=2.5, label="Culprit: Exhaust Temp 2 (Hot Streak Actual)", zorder=4)
ax1.plot(w3.index, exp3[tc2_col], color="#38bdf8", linestyle="--", linewidth=1.8, label="Digital Twin Expected Cooldown Profile", zorder=3)
ax1.plot(w3.index, w3[tc6_col], color="#10b981", alpha=0.8, linewidth=1.4, label="Peer: Exhaust Temp 6 (Coldest Can ~320°C)")
ax1.plot(w3.index, w3[tc8_col], color="#94a3b8", alpha=0.7, linewidth=1.2, label="Peer: Exhaust Temp 8 (Drops to 324.8°C)")
ax1.plot(w3.index, w3[tc13_col], color="#f59e0b", alpha=0.8, linewidth=1.4, label="Peer: Exhaust Temp 13 (Hottest Can ~408°C)")

# Markers
ax1.axvline(t_alarm_3, color="#f59e0b", linestyle="-.", linewidth=2, label="T_alarm: Early Digital Twin Trigger (01:35 UTC)", zorder=5)
ax1.axvline(t_diverge_3, color="#a855f7", linestyle=":", linewidth=2.0, label="Exact Divergence: Temp 2 at 370.4°C vs Peers at 324°C-346°C (02:30 UTC)", zorder=5)
ax1.axvline(t_trip_dcs_3, color="#dc2626", linestyle="--", linewidth=2.0, label="T_trip: DCS Spread Trip Breach (02:49 UTC, TTXS=80.6°C)", zorder=5)
ax1.axvspan(t_alarm_3, t_trip_dcs_3, color="#f59e0b", alpha=0.12, label="Lead Time Window (74 min before DCS Trip Breach)")

ax1.annotate("EARLY ADVISORY TRIGGER (01:35 UTC)\nAnomaly Score: 2,653 > 732\nPredicted: Spread Trip TTXS_ALM",
             xy=(mdates.date2num(t_alarm_3), 480),
             xytext=(mdates.date2num(t_alarm_3) - 0.038, 300),
             arrowprops=dict(facecolor="#f59e0b", edgecolor="#f59e0b", shrink=0.05, width=1.5, headwidth=6),
             color="#fef08a", fontweight="bold", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.4", fc="#78350f", ec="#f59e0b", lw=1.2))

ax1.annotate("EXACT TIMESTAMP: 2026-01-05 02:30 UTC\nTemp 2 hangs at 370.35°C\nTemp 6 at 346.0°C (drops to 319.9°C at 02:38)\nTemp 8 drops to 324.8°C at 02:40",
             xy=(mdates.date2num(t_diverge_3), 370.35),
             xytext=(mdates.date2num(t_diverge_3) + 0.008, 450),
             arrowprops=dict(facecolor="#a855f7", edgecolor="#a855f7", shrink=0.05, width=1.5, headwidth=6),
             color="#f3e8ff", fontweight="bold", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.4", fc="#581c87", ec="#a855f7", lw=1.2))

ax1.set_ylabel("Temperature (°C)", color="#e2e8f0", fontsize=10, fontweight="bold")
ax1.set_title("EVENT 3: Combustion Hot Streak & Can Spread Divergence During Deload (Exhaust Temp 2)", color="#f8fafc", fontsize=12, fontweight="bold", pad=10)
ax1.legend(loc="upper right", facecolor="#0f172a", edgecolor="#475569", labelcolor="#e2e8f0", fontsize=8)

# Panel 2: Exhaust Temperature Spread TTXS vs DCS Limits
ax2.plot(ttxs_3.index, ttxs_3, color="#ec4899", linewidth=2.2, label="Actual Exhaust Spread TTXS across 13 Thermocouples", zorder=4)
ax2.axhline(55.0, color="#f59e0b", linestyle="--", linewidth=1.5, label="DCS Spread Alarm Limit (TTXS_ALM = 55.0°C)", zorder=3)
ax2.axhline(80.0, color="#dc2626", linestyle="-", linewidth=1.8, label="DCS Spread Trip Limit (TTXS_TRIP = 80.0°C)", zorder=3)

ax2.axvline(t_alarm_3, color="#f59e0b", linestyle="-.", linewidth=1.5)
ax2.axvline(t_alarm_dcs_3, color="#f59e0b", linestyle="--", linewidth=1.5, label="T_alarm_DCS: Spread Alarm Crossed (02:27 UTC, TTXS=61.0°C)")
ax2.axvline(t_trip_dcs_3, color="#dc2626", linestyle="--", linewidth=1.8, label="T_trip_DCS: Spread Trip Crossed (02:49 UTC, TTXS=80.6°C)")

ax2.annotate("DCS ALARM BREACH: 61.0°C at 02:27\n(+52 min after Twin Alert)",
             xy=(mdates.date2num(t_alarm_dcs_3), 61.0),
             xytext=(mdates.date2num(t_alarm_dcs_3) - 0.045, 95),
             arrowprops=dict(facecolor="#f59e0b", edgecolor="#f59e0b", shrink=0.05, width=1.5, headwidth=6),
             color="#fef08a", fontweight="bold", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.4", fc="#78350f", ec="#f59e0b", lw=1.2))

ax2.annotate("DCS TRIP BREACH: 80.6°C at 02:49\n(+74 min after Twin Alert)",
             xy=(mdates.date2num(t_trip_dcs_3), 80.6),
             xytext=(mdates.date2num(t_trip_dcs_3) + 0.005, 95),
             arrowprops=dict(facecolor="#dc2626", edgecolor="#dc2626", shrink=0.05, width=1.5, headwidth=6),
             color="#fecaca", fontweight="bold", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.4", fc="#7f1d1d", ec="#dc2626", lw=1.2))

ax2.set_ylabel("Spread TTXS (°C)", color="#e2e8f0", fontsize=10, fontweight="bold")
ax2.legend(loc="upper left", facecolor="#0f172a", edgecolor="#475569", labelcolor="#e2e8f0", fontsize=8)

# Panel 3: Residual
res3 = w3[tc2_col] - exp3[tc2_col]
ax3.plot(w3.index, res3, color="#f43f5e", linewidth=1.8, label="Exhaust Temp 2 Residual Deviation (°C)")
ax3.fill_between(w3.index, 0, res3, color="#f43f5e", alpha=0.2)
ax3.axhline(0, color="#64748b", linestyle=":", linewidth=1)
ax3.axvline(t_alarm_3, color="#f59e0b", linestyle="-.", linewidth=1.5)
ax3.axvline(t_trip_dcs_3, color="#dc2626", linestyle=":", linewidth=1.5)
ax3.set_ylabel("Residual (°C)", color="#e2e8f0", fontsize=9, fontweight="bold")
ax3.set_xlabel("Timestamp (UTC)", color="#cbd5e1", fontsize=10)
ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%b %d"))
ax3.legend(loc="upper right", facecolor="#0f172a", edgecolor="#475569", labelcolor="#e2e8f0", fontsize=8)

fig.tight_layout()
p3 = figures_dir / "event3_exhaust_temp2_hotstreak.png"
fig.savefig(p3, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
plt.close(fig)
print(f"Saved: {p3}")

# Copy to artifacts directory
for p in [p1, p2, p3]:
    target = artifact_dir / p.name
    shutil.copy2(p, target)
    print(f"Copied to artifact dir: {target}")

print("All PNG charts updated successfully.")
