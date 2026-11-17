# GT-2420A Trip & Shutdown Event Log (From Collected 1-Minute PI Telemetry)

**Dataset Scanned:** `data/historical_data.parquet` (`2025-10-04 16:00:00 UTC` to `2026-10-08 11:32:00 UTC`, 480,152 rows × 158 sensors)  
**Purpose:** Identify and classify all Turbine Trip and Shutdown events to select the exact time windows for **10-second (`10s`) high-resolution PI Web API extraction** and focused trip-precursor modeling.

---

## 1. How We Detected & Classified Trip Events (4 Complementary Methods)

Relying only on `Speed -> 0 RPM` mixes together **Planned Normal Shutdowns** and **Unplanned Emergency Trips**. To separate true **Hard Emergency Trips** from **Normal Fired Shutdowns**, we combined four physical detection methods across the PI telemetry:

| Method | Primary PI Tags Used | Physical Signature |
| :--- | :--- | :--- |
| **Method 1: Rotor Speed Crash (`Speed -> 0`)** | `HP Shaft Magnetic Speed Pick Up`<br>`LP Shaft Magnetic Speed Pick Up` | Detects every transition where the Gas Generator (`HP Shaft`, normal `4,750–5,150 RPM`) and Power Turbine (`LP Shaft`, normal `3,260–3,870 RPM`) drop below `1,000 RPM` down to `0 RPM`. Found **13 full-speed stop events**. |
| **Method 2: Fuel Stop Valve (`SRV`) & `IGV` Instantaneous Slam vs. 3-Min Fired Coastdown** | `Fuel Gas Stop/Speed Ratio Valve Position` (`SRV`)<br>`Fuel Gas Control Valve Position` (`FCV`)<br>`Turbine IGV Position` (`IGV`) | **True Hard Emergency Trip:** The trip solenoid de-energizes instantaneously—`SRV` and `FCV` slam from operating opening (`21%–56%`) straight to **`-2.8% / -2.9%` (`0%` physical stop)** and `IGV` slams straight to **`29.9°`** within a single step.<br>**Normal Fired Shutdown:** Controller executes a **3-minute stepped ramp** where `IGV` holds at **`34.0°` (idle stop)** and `FCV` holds at **`10.5%–13.1%` (minimum flame)** for 3 minutes before fuel cut. |
| **Method 3: Pre-Stop Load & Speed Profile** | `LP Shaft Speed Control`<br>`Axial Compressor Discharge Pressure` (`CDP`)<br>`Exhaust Temperature 1..13` | Checks whether the turbine was running at **100% full load** (`LP ~ 3,870 RPM`, `IGV = 84.9°`, `Exhaust Mean ~ 788°C`) right up to the second of fuel cut (**Unplanned Full-Load Trip**), or gradually deloaded by the operator beforehand. |
| **Method 4: Pre-Stop Subsystem Anomaly Scan** | All 158 Sensors (`Dry Gas Seal`, `Compressor Process`, `Lube Oil`, `Bearings`, `Exhaust`) | Compares the 15–60 minutes prior to the stop against the preceding healthy baseline to identify severe control hunting, valve saturation, or abnormal differential pressures that triggered the stop. |

---

## 2. Primary Confirmed Hard Emergency Trips (Priority Targets for `10s` PI Pull)

Out of the 13 full-speed stops in the dataset, **2 events (occurring back-to-back on `2026-01-05`) are confirmed Unplanned Hard Emergency Trips** where fuel was cut instantaneously without the 3-minute fired-shutdown sequence:

### 🔴 HARD TRIP #1 (Primary Full-Load Emergency Trip): `2026-01-05 01:24:00 UTC`
- **Operating State Before Trip (`01:23:00 UTC`):**
  - Continuous run duration before trip: **218.6 hours (~9.1 days)**
  - `HP Shaft Magnetic Speed Pick Up`: **`5,129.1 RPM`**
  - `LP Shaft Magnetic Speed Pick Up`: **`3,870.6 RPM`** (Full Load)
  - `Fuel Gas Stop/Speed Ratio Valve (SRV)`: **`41.1%`**
  - `Fuel Gas Control Valve (FCV)`: **`55.9%`**
  - `Axial Compressor Discharge Pressure (CDP)`: **`112.3`**
  - `Turbine IGV Position`: **`84.9°`** (Full Open)
  - `Exhaust Temperature Mean`: **`787.6 °C`** (Spread `TTXS = 18.9 °C`)
- **Trip Execution Signature (`01:23:00 -> 01:24:00 UTC`):**
  - `SRV` slammed instantaneously from **`41.1%` $\rightarrow$ `-2.8%` (`0%`)**
  - `FCV` slammed instantaneously from **`55.9%` $\rightarrow$ `-2.9%` (`0%`)**
  - `IGV` slammed instantaneously from **`84.9°` $\rightarrow$ `29.9°`** (completely bypassed the `34.0°` normal shutdown step)
  - `HP Speed` plunged **`5,129.1` $\rightarrow$ `2,687.7` $\rightarrow$ `1,188.6` $\rightarrow$ `0 RPM`**
  - `LP Speed` plunged **`3,870.6` $\rightarrow$ `814.3` $\rightarrow$ `296.3` $\rightarrow$ `1.4 RPM`**
  - `Exhaust Mean` plunged **`-289.2 °C` in 60 seconds** (`787.6 °C` $\rightarrow$ `498.4 °C`), while `Exhaust Temperature 2` lagged behind peers (creating a `98.2 °C` post-trip cooldown spread).
- **Preliminary Pre-Trip Signals Found in 1-Min Data (`00:30` – `01:23 UTC`):**
  1. **3–4 Minute Fuel/Speed Control Hunting:** Between `01:09` and `01:23 UTC`, `HP Speed` (`5,063` $\leftrightarrow$ `5,136 RPM`), `SRV` (`37.7%` $\leftrightarrow$ `42.4%`), `FCV` (`52.8%` $\leftrightarrow$ `58.1%`), and `Exhaust Mean` (`774.5 °C` $\leftrightarrow$ `795.5 °C`) exhibited pronounced periodic oscillation.
  2. **Bearing Drain Oil & Tertiary Seal Gas Oscillation:** `Journal Thrust Bearing 4 Drain Oil Temperature` variability increased **`9.79x`** (mean shifted `-1.86 °C`, $|Z| = 17.27\sigma$), `Journal Bearing 1/2/3 Drain Oil Temperatures` variability increased **`4.1x–5.3x`**, and `Tertiary Seal Gas Pressure` variability increased **`4.2x`**.
  3. **Process Compressor Shift:** `1st Stage Compressor Inlet Temperature` rose `+3.1 °C` ($|Z| = 10.37\sigma$) while `1st Stage Compressor Ratio` dropped ($|Z| = 7.75\sigma$) and `Lube Oil Header Pressure 1 & 3` shifted downward.
  4. **Why 10-Second Data Is Essential Here:** Because 1-minute sampling only captures `01:23:00` (still running at full load) and `01:24:00` (already tripped), the exact **first-out initiating sensor spike** between `01:23:00` and `01:24:00` happened *between* 1-minute samples!

---

### 🔴 HARD TRIP #2 (Post-Trip Restart Emergency Trip): `2026-01-05 03:21:00 UTC`
- **Operating State Before Trip (`03:06:00 – 03:20:00 UTC`):**
  - Operators attempted a hot restart at `03:06 UTC` (1 hour 42 minutes after Hard Trip #1).
  - During ramp-up (`03:09–03:14 UTC`), `Exhaust Spread (TTXS)` spiked to **`379.3 °C`** and peak exhaust temperature hit **`931.3 °C`**.
  - At `03:17–03:18 UTC`, `Fuel Gas Stop/Speed Ratio Valve (SRV)` saturated at **`99.9%` (`100%` wide open)** while accelerating through `HP = 4,718 -> 5,047 RPM`.
  - At `03:19 UTC`, `HP Speed` overshot to **`5,152.3 RPM`**, and at `03:20 UTC` (`HP = 5,090.7 RPM`, `LP = 3,257.1 RPM`, `SRV = 21.0%`, `FCV = 37.5%`, `IGV = 56.0°`), the unit ran for only 2 minutes at speed.
- **Trip Execution Signature (`03:20:00 -> 03:21:00 UTC`):**
  - `SRV` slammed instantaneously from **`21.0%` $\rightarrow$ `-2.5%` (`0%`)**
  - `FCV` slammed instantaneously from **`37.5%` $\rightarrow$ `-2.9%` (`0%`)**
  - `IGV` slammed instantaneously from **`56.0°` $\rightarrow$ `29.9°`**
  - `Exhaust Spread (TTXS)` breached the `80.0 °C` DCS Trip Limit, spiking to **`102.2 °C`** as `HP Speed` crashed to `0 RPM`.

---

## 3. Complete Catalog of All 13 Full-Speed Stop Events in Collected PI Data

For completeness, below are all 13 events where `HP Shaft Speed` dropped from operating speed (`~4,800–5,150 RPM`) to `0 RPM`, classified by their control & process signatures:

| Event # | Timestamp (UTC) | Stop Classification | Pre-Stop Speed (`HP` / `LP` RPM) | Valve Action at `t0` (`SRV` / `FCV` / `IGV`) | Run Duration Before Stop | Key Pre-Event Anomaly / Process Precursor Observed |
| :---: | :--- | :--- | :--- | :--- | :---: | :--- |
| **1** | `2025-10-07 07:15:00` | Fired Shutdown (3-min step) | `4,785` / `3,264` | `SRV: 26.1%->5.7%`, `IGV: 79.1°->34.0°` | `63.3 h` | `1st Stage Comp Inlet Temp` & `Wheel Space 2nd Stage Fwd` shift |
| **2** | `2025-10-31 07:05:00` | Fired Shutdown (Deload + Stop) | `5,052->4,315` / `3,656->2,244` | `SRV: 8.8%->3.7%`, `IGV: 34.1°` | `4.5 h` | **`Seal Gas Amplifier DP` surged from `-2.3` to `302.1`** + `Seal Gas Filter DP` rose `11x` (`0.43 -> 4.95`) |
| **3** | `2025-12-07 07:34:00` | Fired Shutdown (from Part Load) | `5,101` / `3,264` | `SRV: 25.7%->6.7%`, `IGV: 56.0°->34.0°` | `0.75 h` | **`Anti-Surge Valve 1 & 2` opened (`0.7% -> 24.1%` and `0.1% -> 17.7%`)** + `2nd Stage Comp Ratio` jump |
| **4** | **`2026-01-05 01:24:00`** | **🔴 HARD EMERGENCY TRIP #1** | **`5,129` / `3,871` (Full Load)** | **`SRV: 41.1%->-2.8%`, `FCV: 55.9%->-2.9%`, `IGV: 84.9°->29.9°`** | **`218.6 h`** | **Fuel/Speed hunting + `Bearing 4 Drain Oil Temp` oscillation (`9.8x`) + `Lube Oil Header Pressure` drop** |
| **5** | **`2026-01-05 03:21:00`** | **🔴 HARD EMERGENCY TRIP #2** | **`5,091` / `3,257` (Restart)** | **`SRV: 21.0%->-2.5%`, `FCV: 37.5%->-2.9%`, `IGV: 56.0°->29.9°`** | **`0.27 h`** | **`SRV` saturated at `99.9%`, `HP Speed` overshot to `5,152 RPM`, `Exhaust Spread` hit `102.2 °C`** |
| **6** | `2026-01-15 04:42:00` | Fired Shutdown (from Part Load) | `5,103` / `3,264` | `SRV: 26.0%->6.5%`, `IGV: 56.0°->34.0°` | `238.9 h` | Deloaded from `LP=3,954 RPM` (`IGV=84.9°`) to `LP=3,264 RPM` (`IGV=56.0°`) 14 mins prior |
| **7** | `2026-02-04 03:37:00` | Fired Shutdown (Process Stop) | `5,096->4,258` / `3,812->2,087` | `SRV: 8.1%->3.7%`, `IGV: 33.9°` | `74.2 h` | **`Seal Gas Filters DP` spiked `55x` (`0.69 -> 38.01`)** + `Seal Gas Heater Temp 1 & 3` dropped `-16 °C` |
| **8** | `2026-04-23 05:41:00` | Fired Shutdown (Deload + Stop) | `5,060->5,097` / `3,703->3,264` | `SRV: 24.4%->5.0%`, `IGV: 56.0°->34.0°` | `170.2 h` | **`Seal Gas Amplifier DP` surged (`-2.4 -> 172.5`)** + `Seal Gas Filter DP` rose (`1.33 -> 6.22`) |
| **9** | `2026-08-19 05:25:00` | Fired Shutdown (Deload + Stop) | `5,091->4,305` / `3,989->2,289` | `SRV: 8.5%->3.9%`, `IGV: 34.0°` | `46.3 h` | Gradual 15-min deload + `2nd Stage Comp Outlet Pressure` drop (`73.2 -> 37.3`) |
| **10** | `2026-08-22 09:06:00` | Fired Shutdown (from Part Load) | `4,904` / `3,265` | `SRV: 28.0%->8.0%->3.9%`, `IGV: 34.0°` | `55.6 h` | **`Compressor Shaft Y Radial Vibration 2` rose (`7.96 -> 11.63 mm/s`)** + `Seal Gas Balancing Pressure` doubled |
| **11** | `2026-08-25 07:11:00` | Fired Shutdown (from Part Load) | `5,096` / `3,262` | `SRV: 26.3%->5.6%`, `IGV: 55.9°->33.9°` | `47.7 h` | `Compressor DE & SE Primary Vent Flow` dropped (`16.0 -> 5.1` and `19.6 -> 4.9`) |
| **12** | `2026-08-29 09:11:00` | Fired Shutdown (from Load) | `5,003` / `3,583` | `SRV: 34.4%->25.5%->5.3%`, `IGV: 34.0°` | `50.4 h` | `Seal Gas Filters DP` rose `28x` (`0.04 -> 1.19`) |
| **13** | `2026-09-02 07:07:00` | Fired Shutdown (from Full Load) | `5,102` / `3,855` | `SRV: 39.0%->29.9%->6.4%`, `IGV: 34.0°` | `26.6 h` | `Seal Gas Filters DP` rose `16x` (`0.11 -> 1.73`) + `Buffer Seal Gas Valve` saturated at `100%` |

---

## 4. Recommended Windows for `10s` High-Resolution PI Data Pull (Awaiting VPN)

> **NOTE:** Per instructions, **no PI data pull has been executed yet**. Once you connect to the VPN and confirm which event(s) you want to pull, we will query all 158 sensors at **`--interval 10s`** for the following window(s):

1. **Primary Window (Covers Both Hard Emergency Trip #1 and Hard Emergency Trip #2 on `2026-01-05`):**
   - **Start (UTC):** `2026-01-04 18:00:00` (provides 7.5 hours of clean full-load baseline + pre-trip buildup)
   - **End (UTC):** `2026-01-05 04:30:00` (captures Hard Trip #1 at `01:24 UTC`, cooldown, Restart attempt at `03:06 UTC`, and Hard Trip #2 at `03:21 UTC`)
   - **Resolution:** `10s` (10-second interpolated interval across all 158 tags = `3,780 rows × 158 columns`, pulls in ~2–3 minutes).

2. **Optional Secondary Windows (Process-Induced Shutdowns with Clear Precursors):**
   - **Dry Gas Seal High DP Stop (`2026-02-04`):** `2026-02-03 21:00:00` to `2026-02-04 04:30:00` (`10s`)
   - **Compressor Anti-Surge Stop (`2025-12-07`):** `2025-12-07 04:00:00` to `2025-12-07 08:30:00` (`10s`)
   - **Seal Gas Amplifier DP Stop (`2025-10-31`):** `2025-10-31 02:00:00` to `2025-10-31 08:00:00` (`10s`)
