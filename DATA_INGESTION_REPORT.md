# Gas Turbine GT-2420A Telemetry Ingestion & Data Quality Report

**Target Asset:** `MALAYSIA\BORF\GTG\GT-2420A`  
**Data Source:** OSIsoft PI Web API (`https://kul-pivision.pttep.com/piwebapi`)  
**Sampling Interval:** 1-minute interpolated resolution (`1m`)  
**Storage Target:** Apache Parquet (`data/historical_data.parquet`, Snappy compression)  
**Report Generated:** 2026-10-08 19:40 MYT  

---

## 1. Executive Summary

The 12-month historical telemetry ingestion for Gas Turbine Generator `GT-2420A` has successfully completed. The dataset covers **12.1 months** of plant operations, capturing **75,864,016 individual sensor points** across **158 active sensor attributes**.

Operating limits (5 statistical thresholds per sensor: **Normal, HH, H, L, LL**) have been computed across all 158 sensors (790 limits total) and persisted to SQLite storage (`data/operating_limits.db`) and CSV (`data/operating_limits.csv`).

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Ingestion Status** | **Success** | Confirmed in `config/last_run_meta.json` |
| **Total Recorded Rows** | **480,152** | Monotonically ordered 1-minute timestamps |
| **Duplicate Timestamps** | **0** | Clean, de-duplicated time index |
| **Active Sensors Ingested** | **158** | Out of 162 total cataloged attributes |
| **Total Data Points** | **75,864,016** | 480,152 rows × 158 columns |
| **Dataset Completeness** | **90.41%** | 480,152 actual vs. 531,093 calendar minutes |

---

## 2. Telemetry Boundaries (First & Last Data)

| Boundary | UTC Timestamp | Local Time (MYT / UTC+8) | Description |
| :--- | :--- | :--- | :--- |
| **First Data Point** | **`2025-10-04 16:00:00+00:00`** | **`2025-10-05 00:00:00+08:00`** | Midnight 5 October 2025 (Beginning of 12-month training baseline) |
| **Last Data Point** | **`2026-10-08 11:32:00+00:00`** | **`2026-10-08 19:32:00+08:00`** | Latest minute recorded in OSIsoft PI Data Archive |

- **Total Monitored Span:** **368.8 days** (~12.1 months)
- **Total Calendar Minutes in Span:** **531,093 minutes**
- **Actual Telemetry Rows Collected:** **480,152 minutes** (90.41% operational coverage)

---

## 3. Timeline Gaps & Incomplete Periods Analysis

Across the 531,093 calendar minutes between start and end, **50,941 minutes (9.59%)** have no data points. 

Forensic verification against the live PI Web API confirms that these gaps are **not** software or network data loss; they correspond to **physical equipment shutdowns, maintenance turnarounds, and unit trips** where the turbine was offline and produced zero points in the PI System.

### 3.1. Major Gaps (≥ 1 Hour) — Physical Plant Outages

There are only **3 major gap events** across the entire 12-month period. Together, these 3 events account for **50,798 missing minutes (99.72% of all missing timeline intervals)**:

| Event # | Start Time (UTC) | End Time (UTC) | Start Time (MYT) | End Time (MYT) | Duration | Missing Minutes | Root Cause & Operating Context |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **1** | **`2026-06-06 23:51`** | **`2026-07-09 04:47`** | `2026-06-07 07:51` | `2026-07-09 12:47` | **32.21 days** (772.9 hrs) | **46,375** | **Annual Planned Turnaround / Major Maintenance:** Equipment `GT-2420A` was physically de-energized and offline for ~1 month. The PI Web API returned HTTP 200 with 0 points (`Items: []`) across all 158 tags throughout this outage window. |
| **2** | **`2026-07-17 02:36`** | **`2026-07-20 02:19`** | `2026-07-17 10:36` | `2026-07-20 10:19` | **2.99 days** (71.7 hrs) | **4,302** | **Plant Outage / Maintenance:** 3-day outage period. Equipment produced 0 points. |
| **3** | **`2026-08-31 06:28`** | **`2026-08-31 08:30`** | `2026-08-31 14:28` | `2026-08-31 16:30` | **2.03 hours** | **121** | **Turbine Trip & Restart:** Transient unit shutdown followed by startup synchronization. |

### 3.2. Minor Gaps (< 1 Hour)

There are **28 minor gaps** totaling just **143 minutes** across the entire year (**0.03%** of the calendar year):
- **Startup Transient Gaps:** 
  - `2026-07-20 13:53 UTC` to `14:35 UTC` (41 minutes) during unit restart following Outage 2.
  - `2026-08-31 03:58 UTC` to `04:44 UTC` (45 minutes) during pre-trip startup.
- **Telemetry Sync / Buffer Flushes:**
  - 26 isolated 1-to-2 minute telemetry jumps scattered across October 2025, March 2026, and July 2026 caused by PI Data Archive buffer flushes.

---

## 4. Sensor-Level Completeness & Null Value Analysis

Within the 480,152 active recorded timestamps:
- **108 sensors (68.4%)** have **100% complete data** (0 nulls) for all operational timestamps.
- **50 sensors** exhibit null values during specific operational periods due to field instrumentation maintenance or signal quality flags:

### 4.1. Instrumentation Maintenance & Outages

| Sensor | Subsystem | Total Nulls | Null % | Valid Range (UTC) | Description |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **Lube Oil Header Pressure 2** | Lube Oil System | 72,642 | 15.13% | 2025-10-04 to 2026-10-08 | Transmitter outage between **28 Nov 2025 13:34 UTC** and **16 Jan 2026 02:27 UTC** (~48 days). Normal logging resumed thereafter. |
| **G.T. Compart. Vent. Outlet Gas Detector** | Enclosure System | 34,885 | 7.27% | 2025-10-04 to 2026-09-14 | Transmitter signal discontinued / Bad quality in PI AF after **14 Sept 2026 07:25 UTC**. |
| **Turbine Compartment Ventilation Pressure 1–3** | Enclosure System | ~34,870 | 7.26% | 2025-10-04 to 2026-09-14 | Transmitter signal discontinued / Bad quality after **14 Sept 2026 07:32 UTC**. |
| **Exhaust Duct Back Pressure** | Gas Turbine Engine | 34,865 | 7.26% | 2025-10-04 to 2026-09-14 | Transmitter signal discontinued / Bad quality after **14 Sept 2026 07:40 UTC**. |
| **Axial Compressor Inlet Temp 1 & 2** | Gas Turbine Engine | ~32,336 | 6.74% | 2025-10-04 to 2026-09-16 | Thermocouple signal discontinued after **16 Sept 2026 01:22 UTC**. |
| **Exhaust Temperature 1–13** | Gas Turbine Engine | ~29,140 | 6.07% | 2025-10-04 to 2026-09-25 | Thermocouple rack signals discontinued / Bad quality after **24–25 Sept 2026**. |
| **Bearing Drain Oil Temperatures (1–3)** | Gas Turbine Engine | ~27,600 | 5.75% | 2025-10-04 to 2026-09-20 | Drain oil temp signals discontinued after **19–20 Sept 2026**. |

---

## 5. System Architecture & Resumption Hardening

During this ingestion cycle, the client engine was upgraded to handle real-world plant outages and VPN disconnections:

1. **Persistent Slice Completion Ledger (`data/completed_slices.json`):**
   - Each hourly slice queried from PI Web API is permanently registered in an atomic JSON ledger.
   - Plant outage slices returning 0 points are tracked as verified, preventing the engine from re-querying known outage periods on restart.
2. **Batch Throttling & PI Vision Accommodated:**
   - 5-second back-off delay after every 5 batch requests to avoid saturating PTTEP PI Web API server resources.
3. **Automated Limits Synchronization:**
   - Statistical limits engine automatically computed 790 thresholds upon completion and synchronized them with SQLite (`data/operating_limits.db`) using change-detection deduplication.
