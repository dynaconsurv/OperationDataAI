# Focused Trip-Driven Monitoring Plan (`focusplan.md`)

**Objective:** Replace the broad 158-sensor catalog with a **Trip-Event-Focused Early Warning & Monitoring Workbook** ([`GT2420A_Trip_Focused_Monitoring.xlsx`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/GT2420A_Trip_Focused_Monitoring.xlsx)) built directly from actual GT-2420A Trip events, 10-second (`10s`) high-resolution PI telemetry, and only the specific sensors that contribute to or give early warning of a trip.

---

## Step-by-Step Execution Status

### ✅ Step 1: Identify & Classify Trip Events in Collected PI Data *(COMPLETED)*
- **What we did:**
  - Scanned [`data/historical_data.parquet`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/data/historical_data.parquet) using 4 complementary physical detection methods:
    1. **Rotor Speed Crash (`HP` & `LP Shaft Speed -> 0 RPM`)**
    2. **Fuel Stop/Speed Ratio Valve (`SRV`) & `IGV` Instantaneous Slam (`SRV -> -2.8%`, `IGV -> 29.9°`) vs. 3-Minute Fired Shutdown (`IGV = 34.0°`, `FCV ~ 11%`)**
    3. **Pre-Stop Load Profile (Full-Load Abrupt Cut vs. Operator Deloading Ramp)**
    4. **Pre-Stop Subsystem Z-Score & Oscillation Scan**
- **Output:** [`trip_events_log.md`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/trip_events_log.md)

---

### ✅ Step 2: Pull 10-Second (`10s`) High-Resolution PI Data Over VPN *(COMPLETED)*
- **What we did:**
  - Executed [`pull_trip_events_10s.py`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/pull_trip_events_10s.py) against `https://kul-pivision.pttep.com/piwebapi`.
  - Pulled **40 minutes before** to **+10 minutes after** each of the **13 Stop/Trip Events** at **`10s` interval** (`301 rows × 158 sensors` per event = `3,913 rows` total).
- **Outputs Saved:**
  - Combined 10s dataset: [`data/trip_events_10s_combined.parquet`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/data/trip_events_10s_combined.parquet)
  - 13 individual 10s event files in: [`data/trip_events_10s/`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/data/trip_events_10s)

---

### ✅ Step 3: Isolate the Exact Trip Contributors & Early-Signal Sensors (`10s` Forensics) *(COMPLETED)*
- **What the `10s` data revealed:**
  - **Hard Emergency Trip #1 (`Event 04`):** Pinpointed the exact solenoid fuel-cut trigger to **`2026-01-05 01:23:20 UTC`** (40 seconds earlier than visible in 1-minute data), where `SRV` slammed from `41.1%` to `-2.8%`, `FCV` slammed from `55.9%` to `-2.9%`, `IGV` slammed from `84.9°` to `29.9°`, and `Exhaust Spread (TTXS)` jumped to **`105.5 °C`** (`> 80.0 °C` Trip Limit).
  - **Hard Emergency Trip #2 (`Event 05`):** Pinpointed the restart trip trigger to **`2026-01-05 03:20:50 UTC`**, preceded 11.5 minutes earlier (`03:09:20 UTC`) by severe combustion spread divergence across `Exhaust Temp 5, 6, 7, 8, 12` ($|Z| = 136\sigma - 173\sigma$, `TTXS = 379.3 °C`) and `SRV` saturation at `99.9%`.
  - Narrowed all 158 sensors down to **26 Focused Trip-Contributing & Early-Warning Sensors** grouped into **4 Physical Precursor Families**:
    1. **Family A — Speed, Fuel Control & Combustion Spread** (`HP/LP Speed`, `SRV`, `FCV`, `Interstage Fuel Gas Pressure 2`, `Flame Detectors Ch.3 & Ch.10`, `Exhaust Temp 2, 5, 6, 7, 8`)
    2. **Family B — Dry Gas Seal (DGS) & Primary Vent System** (`Seal Gas Filters DP`, `Seal Gas Amplifier DP`, `Tertiary Seal Gas Pressure`, `Compressor Suction/Discharge End Primary Vent Flow`)
    3. **Family C — Process Compressor Stage Pressure, Ratio & Flow** (`2nd Stage Comp Inlet Pressure`, `1st/2nd Stage Comp Outlet Pressure`, `2nd Stage Comp Ratio`, `1st Stage Comp Inlet Flow`)
    4. **Family D — Rotor Bearings, Vibration & Lube Oil Supply** (`Turbine Bearing 1 Radial Vibration`, `Journal Thrust Bearing 4 Drain Oil Temp`, `Compressor Journal Bearing Temp 4`, `Lube Oil Header Pressure 3`)

---

### ✅ Step 4: Relationship Discovery (Pearson, Spearman & 10s Lead/Lag Cross-Correlation) *(COMPLETED)*
- Computed **Pearson linear correlation ($r$)**, **Spearman rank correlation ($\rho$)**, and **10-second time-lagged cross-correlation ($\Delta \tau$)** across the 26 focused sensors in Tab 3 of the focused workbook.

---

### ✅ Step 5: Build the Focused Trip-Monitoring Formulas & Targeted Excel Workbook *(COMPLETED)*
- Generated [`GT2420A_Trip_Focused_Monitoring.xlsx`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/GT2420A_Trip_Focused_Monitoring.xlsx) (and [`reports/GT2420A_Trip_Focused_Monitoring.xlsx`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/reports/GT2420A_Trip_Focused_Monitoring.xlsx)) via [`generate_trip_focused_workbook.py`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/generate_trip_focused_workbook.py) with 5 focused sheets:
  1. `1_Trip_Events_Summary_10s` — All 13 Stop/Trip events at `10s` resolution with exact trigger timestamps, valve/speed states, lead times, and top 3 precursor sensors.
  2. `2_Trip_Contributor_Sensors` — Only the 26 Trip-Contributing sensors, their precursor family, events triggered, average lead time, Expected Value formula ($\hat{Y}$), Z-Score formula ($Z$), and 10s Rate-of-Change/Hunting rules.
  3. `3_Precursor_Correlations` — Ranked Pearson ($r$), Spearman ($\rho$), and 10-second Lead/Lag relationships exclusively among the 26 Trip-Contributing sensors.
  4. `4_Live_Trip_Monitor_Calculator` — Interactive Excel formula calculators pre-loaded with 10s telemetry for Hard Trip #1, Hard Trip #2, Dry Gas Seal DP Stop, and Burner Cold-Spot Stop.
  5. `5_10s_HardTrip_Timeline` — Full 10-second-by-10-second telemetry trace across Hard Emergency Trip #1 (`2026-01-05 00:44:00` to `01:34:00 UTC`).
