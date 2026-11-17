# Plain-English Guide: How to Read `GT2420A_Trip_Focused_Monitoring.xlsx`
*(Written for Management, Operations & Non-Engineering Readers)*

**Workbook Link:** [`GT2420A_Trip_Focused_Monitoring.xlsx`](file:///C:/Users/Fuad/Documents/dev/PTTEP%20AI/GT2420A_Trip_Focused_Monitoring.xlsx)

---

## 1. The Big Idea in 30 Seconds (Car Analogy)

Think of the Gas Turbine (`GT-2420A`) like a high-performance car driving on a highway:
- It has **158 sensors** measuring temperatures, pressures, speeds, and vibrations. Looking at all 158 sensors at once is overwhelming.
- Instead of looking at everything, we looked back at the **13 times the machine actually stopped or tripped** over the past year (using high-speed **10-second** black-box recordings).
- We asked one simple question: ***"Which sensors acted strangely 15 to 40 minutes BEFORE the machine stopped?"***
- Out of 158 sensors, we found that **only 26 sensors** consistently give early warning before a stop or trip. This workbook tracks **only those 26 early-warning sensors**.

---

## 2. How the "Early Warning Formula" Works (Without the Math Jargon)

Traditional alarms wait until a single sensor hits a dangerous limit (like waiting until your car engine is already smoking at `140°C`). By then, it is too late to prevent a trip.

Our formula works differently—it compares **teamwork between sensors**:
1. **Expected Value ($\hat{Y}$ — "What the sensor *SHOULD* read"):**
   - If the turbine is running at 80% speed, Sensor A *should* match its neighbor sensors (Peers B, C, and D). The formula calculates what Sensor A **should be** at this exact moment.
2. **Residual ($r$ — "The Gap"):**
   - $\text{Residual} = \text{Actual Reading} - \text{Expected Reading}$.
   - If Sensor A should be `500°C` based on its neighbors, but is actually reading `450°C`, the gap is `-50°C`.
3. **Z-Score ($Z$ — "The Universal Alarm Score"):**
   - Because some sensors measure pressure (`bar`), some measure temperature (`°C`), and some measure vibration (`µm`), we convert the gap into a simple **Z-Score** so every sensor uses the exact same traffic-light scale:
     - 🟢 **Score between `-3` and `+3` (`NORMAL`):** Healthy. The sensor agrees with its neighbors.
     - 🟡 **Score above `3` or below `-3` (`EARLY WARNING`):** Something is starting to drift out of sync.
     - 🔴 **Score above `4` or below `-4` (`CRITICAL TRIP PRECURSOR`):** Strong early warning! In historical trips, this score jumped to **`5` to `300+` between 12 and 39 minutes BEFORE the machine stopped**.

---

## 3. Tab-by-Tab Guide: What Each Sheet Tells You

### 📄 Tab 1: `1_Trip_Events_Summary_10s` — *"The Historical Incident Report"*
**What it is:** A 13-row summary of every time the turbine stopped over the last year.
- **Why some rows are highlighted in Red (`Event #4` and `Event #5` on Jan 5, 2026):**
  - **White/Grey rows (11 events) = Planned or Controlled Stops:** Like pulling your car over and turning the key off smoothly (the fuel valve steps down gently over 3 minutes).
  - **Red rows (2 events) = Sudden Emergency Trips:** Like the car's emergency brakes slamming on at full highway speed (`Fuel Valve` slams to `0%` in 10 seconds).
- **The Most Important Columns for Management:**
  - **Column N (`Earliest Precursor Lead Time`):** Shows **how many minutes in advance** the warning sensors spotted trouble before the turbine actually stopped (typically **12 to 39 minutes early**).
  - **Column P (`Top 3 Early-Warning Sensors`):** Names the exact 3 sensors that raised their hand first before that stop.

---

### 📄 Tab 2: `2_Trip_Contributor_Sensors` — *"The Shortlist of 26 Watchdog Sensors"*
**What it is:** The master list of the **26 sensors** that matter for preventing trips, grouped into **4 plain-English categories (Column B)**:
1. **Group A (`Speed, Fuel & Combustion`):** Are the fuel valves steady and are all burners firing evenly?
2. **Group B (`Dry Gas Seal System`):** Are the protective gas seals clean, or are filters getting clogged? *(Clogged seal filters caused several process stops).*
3. **Group C (`Process Compressor`):** Is the gas compressor flowing smoothly, or is pressure building up?
4. **Group D (`Bearings & Lube Oil`):** Are the spinning shafts well-oiled, cool, and running smoothly without vibration?

#### Detailed Column-by-Column Guide for Tab 2:
- **Column D (`Role in Trip / Early Warning Signature`):**
  - Plain-English explanation of what goes wrong physically when this sensor acts up.
- **Column E (`Events Triggered (# of Events)`):**
  - **Refers directly to the `Event #` list (`#1` to `#13`) in Tab 1 (`1_Trip_Events_Summary_10s`).**
  - Counts how many of the 13 historical Stop/Trip events in Tab 1 showed a strong early-warning alarm (`|Z| >= 3.5`) on this specific sensor **before** the turbine stopped, and lists the matching Event IDs from Tab 1.
  - *Example 1 — Row 11 (`Exhaust Temperature 7`):* Shows **`5 events (#1, #3, #5, #6, #8)`**, meaning it gave an early warning before **Event #1** (`2025-10-07`), **Event #3** (`2025-12-07`), **Event #5** (`2026-01-05 03:20` Hard Trip #2), **Event #6** (`2026-01-15`), and **Event #8** (`2026-04-23`) in Tab 1.
  - *Example 2 — Row 16 (`Seal Gas Filters Differential Pressure`):* Shows **`3 events (#3, #5, #7)`**, referring to Event #3, Event #5, and Event #7 (`2026-02-04`, where the clogged seal gas filter spiked and forced the stop).
  - *(Note: When a sensor triggered in more than 6 events, Column E displays the total count and the first 6 event IDs to keep the cell compact).*
- **Column F (`Avg Early Lead Time (min)`):**
  - Shows **how many minutes in advance** (on average across those triggered events) this sensor crossed the warning threshold before the turbine stopped.
- **Column G (`Max Observed |Z| Before Stop`):**
  - Shows the **highest "Severity Score" (Peak Z-Score)** that this sensor reached during the pre-trip warning window across those events.
  - **Plain-English Meaning:** While a healthy sensor stays between **`0` and `3`** and an alarm triggers at **`4.0`**, Column G tells you **how loud the alarm was** before the stop:
    - **`8` to `20`:** Moderate-to-Strong early warning deviation.
    - **`50` to `300+`:** Massive, unmistakable fault signature.
  - *Example 1 — Row 11 (`Exhaust Temperature 7`, Column G = `345.5`):* Before Event #3, this burner temperature dropped to `162.5°C` while its neighbors were at `716–821°C`, reaching a severity score of **`345.5`** (**345 times** larger than normal background noise).
  - *Example 2 — Row 12 (`Exhaust Temperature 5`, Column G = `173.4`):* Reached a severity score of **`173.4`** (`11.5 minutes` before Hard Emergency Trip #2).
  - *Example 3 — Row 17 (`Seal Gas Amplifier Differential Pressure`, Column G = `21.8`):* Reached a severity score of **`21.8`** before Event #8.
- **Summary of Columns E, F, and G Together:**
  - **Column E** = ***HOW OFTEN*** (and in ***WHICH EVENTS*** from Tab 1) the sensor warned us.
  - **Column F** = ***HOW EARLY*** (in minutes before the stop) it warned us.
  - **Column G** = ***HOW STRONG*** the warning signal was (compared to the normal threshold of `3.0–4.0`).
- **Columns H & I (`Intercept β₀` & `Residual Std σ_r`):**
  - Fixed baseline calibration numbers from the trained Digital Twin model used inside the Expected Value and Z-Score formulas.
- **Columns J, K & L (`Expected Value Formula`, `Z-Score Formula` & `10s Hunting Rule`):**
  - The exact copy-paste mathematical formulas used to calculate what the sensor *should* read ($\hat{Y}$), its standardized alarm score ($Z$), and when to trigger an alert in the 10-second stream.

---

### 📄 Tab 3: `3_Precursor_Correlations` — *"Which Sensors Move Together"*
**What it is:** Shows which sensors are "partners" that always move together when the machine is healthy.
- **How to read `Pearson r` (Column F) and `Spearman ρ` (Column G):**
  - **`+1.00`:** Perfect partners—when Sensor A goes up, Sensor B always goes up by the same amount.
  - **`-1.00`:** Opposite partners—when Sensor A goes up, Sensor B always goes down.
  - **`0.00`:** Unrelated.
- **How to read `Optimal Lead/Lag` (Column I):**
  - Tells you **which sensor reacts first** (for example, *"Sensor A leads by 30s"* means Sensor A moves 30 seconds before Sensor B feels the effect—making Sensor A a great early warning indicator).

---

### 📄 Tab 4: `4_Live_Trip_Monitor_Calculator` — *"Interactive What-If Calculator"*
**What it is:** Four real-life historical trip examples where the math formulas are **live inside the Excel cells**.
- **How to read it:**
  - **Column G (`Sample A`):** Sensor readings when the turbine was running normally.
  - **Column I (`Pre-Trip Peak`):** Sensor readings **minutes before the turbine tripped**.
  - Look at the bottom 4 rows of each block (`Expected`, `Actual`, `Residual`, `Z-Score`):
    - In **Column H (Normal)**, the `Actual` and `Expected` numbers match closely, so the **Z-Score is near `0`** (`NORMAL`).
    - In **Column J (Pre-Trip)**, the `Actual` reading diverges from the `Expected` reading, causing the **Z-Score (Row Z) to light up in Red** (`CRITICAL TRIP PRECURSOR`) minutes before the trip occurred.
- **Try it yourself:** You can type any new sensor reading into **Column G or I**, and Excel will automatically recalculate the Expected Value, Gap, and Alarm Status in **Column K**!

---

### 📄 Tab 5: `5_10s_HardTrip_Timeline` — *"10-Second Black-Box Replay of the Jan 5 Emergency Trip"*
**What it is:** A second-by-second replay (every 10 seconds) of the biggest unplanned emergency trip (**Jan 5, 2026 at 01:23:20 UTC**).
- **How to read it:**
  - **Column B (`Seconds to Trip`):** Counts down (`-2360s, -2350s ... -20s, -10s, 0s`) to the exact moment the turbine tripped.
  - **White rows above `0s`:** The 39-minute early-warning window where the turbine was still running at full speed (`5,129 RPM`), but warning sensors (Flame Detector, Vibration, Bearing Oil Temp, Seal Gas Pressure) were already fluctuating.
  - **Red highlighted rows (`-10s` to `+10s` at `01:23:20 UTC`):** The exact 10-second moment the emergency trip occurred—you can see the **Fuel Valve (`Column E`) slam from `41.1%` to `-2.8%` (`0%`)** and the **Rotor Speed (`Column C`) crash toward `0 RPM`**.

---

### 📄 Tab 6: `6_Sweet_Spot_Operating_Guide` — *"How to Operate in the Green Sweet Spot (Instead of Just Avoiding Manufacturer Limits)"*
**What it is:** A practical operating guide and live calculator that shows the **exact Optimum Target ($\hat{Y}$)** and tight **Green Sweet-Spot Band ($\hat{Y} \pm 2\sigma_r$)** for the turbine and all 26 watchdog sensors.

- **Section 1 (Rows 4–13) — *"Turbine-Level Golden Operating Regimes"*:**
  - Shows the ideal control setpoints (`HP Speed`, `LP Speed`, `IGV Angle`, `Fuel SRV %`, `Fuel FCV %`, `Exhaust Spread`, `Seal Gas Filter DP`, and `Lube Oil Header Pressure`) for both **Part-Load Cruise (`IGV = 56°–78°`)** and **Full-Load High Output (`IGV = 84.9°–85.0°`)**, side-by-side with the **Pre-Trip Danger / Hunting Zone** to avoid.
- **Section 2 (Rows 16–43) — *"Sensor-by-Sensor Dynamic Sweet Spot Envelope vs. Static Manufacturer Limits"*:**
  - **Columns F & G (`Part-Load Optimum Target & Green Sweet Spot`):** What each sensor should read during steady part-load operation, and its tight Green Zone (`Ŷ ± 2σ_r`).
  - **Columns H & I (`Full-Load Optimum Target & Green Sweet Spot`):** What each sensor should read during full-load operation, and its tight Green Zone (`Ŷ ± 2σ_r`).
  - **Columns M & N (`Static High H & High-High HH Limits`):** Shows the static DCS/Manufacturer limits side-by-side so you can see how keeping the sensor inside the **Green Sweet Spot Band** protects the machine long before approaching the manufacturer limit.
  - **Column O (`Dynamic Sweet Spot Formula`):** The exact formula (`Expected(Sensor) ± 2*σ_r`) that automatically shifts the Sweet Spot whenever load or weather changes.
- **Section 3 (Rows 46–55) — *"Interactive Live Sweet-Spot Calculator"*:**
  - Type in current sensor and peer readings in **Columns B to G**, and Excel automatically calculates:
    - **Column H:** Exact Optimum Sweet Spot Target ($\hat{Y}$)
    - **Columns I & J:** Minimum and Maximum Green Sweet-Spot boundaries ($\hat{Y} - 2\sigma_r$ to $\hat{Y} + 2\sigma_r$)
    - **Columns N & O:** Live status (`IN SWEET SPOT (OPTIMAL)` vs. `SLIGHT DRIFT` vs. `EARLY WARNING`) and exact operator guidance.

