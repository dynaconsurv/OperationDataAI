# Module 1 Portable Release: Architectural Adjustments & Reused Features

This document provides a technical audit of the portable release of **Module 1 (PI Telemetry Ingestion & Operating Limits Engine)**, detailing the components reused directly from the main project and the specific adjustments made to satisfy portable deployment requirements.

---

## 1. Summary of Reused Features & Functions

In accordance with the instruction to *prioritize reusing whatever features/functions are already developed*, the portable release preserves the core logic and battle-tested algorithms from the parent codebase:

| Component | Source File | Status | Description of Reused Functionality |
| :--- | :--- | :---: | :--- |
| **Statistical Limits Engine** | `src/module1_pi_ingestion/limits_calculator.py` | **100% Reused** | Full parametric (Sigma multipliers: $\mu \pm 2\sigma, \mu \pm 3\sigma$) and non-parametric (Percentiles: 1st, 5th, 95th, 99th, and Median) limit calculators for `Normal`, `HH`, `H`, `L`, and `LL`. |
| **SQL Storage & Deduplication** | `src/module1_pi_ingestion/sql_storage.py` | **100% Reused** | Exact deduplication mechanism: compares `(af_path, type)` against the SQL table. If the value is unchanged within tolerance, skip insert; else insert with current execution timestamp `updated_at`. Supports MS SQL Server with automatic SQLite fallback. |
| **Batch API Extraction** | `src/module1_pi_ingestion/pi_client.py` | **Reused & Enhanced** | Sub-batch streaming (25 tags per call) against `/piwebapi/batch`, Basic & NTLM authentication, WebID resolution, and SSL bypass toggles. |
| **PI Vision Throttling** | `src/module1_pi_ingestion/pi_client.py` | **100% Reused** | 5-second back-off delay after every 5 batch requests to protect PI Web API and other concurrent enterprise users. |
| **Outage-Aware Ledger** | `src/module1_pi_ingestion/pi_client.py` | **100% Reused** | Atomic slice completion ledger (`completed_slices.json`) ensuring that zero-point plant outages are permanently marked as complete and never re-queried on restart. |
| **Synthetic Generator** | `src/utils/mock_generator.py` | **100% Reused** | Realistic thermodynamic and physical operational sensor data simulation for offline testing. |

---

## 2. Key Adjustments Made for Portable Release

### Adjustment 1: Taglist Grouped by Equipment Number
- **Original:** `config/sensors.json` was a flat JSON array containing 162 sensors without explicit top-level equipment grouping.
- **Portable Adjustment:** 
  - Restructured `release/config/sensors.json` into an equipment-keyed dictionary:
    ```json
    {
      "GT-2420A": [
        {
          "id": 1,
          "equipment_id": "GT-2420A",
          "parent": "MALAYSIA\\BORF\\GTG\\GT-2420A\\...",
          ...
        }
      ]
    }
    ```
  - Added `equipment_id` parameter to `ConfigManager.load_sensors(equipment_id="GT-2420A")`.
  - Added `target_equipment` setting to `config/config.json`.
  - The loader supports both the new grouped dictionary and legacy flat lists for backwards compatibility.

---

### Adjustment 2: Configurable 6-Month Hourly Data Ingestion
- **Original:** Configured for 1-minute sampling (`1m`) across a 12-month window (`full_duration_months: 12`), with hardcoded 1-hour slicing designed specifically for high-frequency minute data.
- **Portable Adjustment:**
  - Default sampling interval set to **hourly** (`sample_interval: "1h"`).
  - Default duration set to **6 months** (`duration_months: 6`).
  - Added `slice_days: 30` parameter in `config.json`. Multi-month hourly queries are segmented into 30-day slices (6 monthly slices for a 6-month period), providing incremental progress tracking, periodic Parquet checkpoints, and resume capability.

---

### Adjustment 3: Standalone CLI Runner (`run_module1.py`)
- **Original:** Ingestion was triggered either via the multi-page Streamlit web interface (`app.py`) or via the top-level `main.py` CLI which loaded all 3 modules.
- **Portable Adjustment:**
  - Created dedicated, zero-dependency standalone runner `release/run_module1.py`.
  - Can be invoked without arguments for default production execution:
    ```bash
    python run_module1.py
    ```
  - Supports CLI flag overrides:
    - `--equipment GT-2420A`: Target a specific equipment group.
    - `--months 6`: Override historical duration in months.
    - `--interval 1h`: Override sampling resolution.
    - `--mock`: Force offline synthetic data generation.
    - `--live`: Force live PI Web API connection.
    - `--no-resume`: Start fresh pull without checkpoint resume.
    - `--start` / `--end`: Custom time range.

---

### Adjustment 4: Self-Contained Path Resolution
- **Original:** Path resolution in `ConfigManager` and `SQLStorageManager` relied on relative paths referencing the root project directory `PTTEP AI/`.
- **Portable Adjustment:**
  - Decoupled `ConfigManager` to anchor all relative paths strictly inside the `release/` base directory.
  - Portable directories `release/data/`, `release/logs/`, and `release/config/` are automatically initialized on launch.

---

### Adjustment 5: Focused Dependencies (`requirements.txt`)
- **Original:** `requirements.txt` included dependencies for Streamlit, Plotly, SciPy, Scikit-learn, and NetworkX required by Modules 2 and 3.
- **Portable Adjustment:**
  - Streamlined `release/requirements.txt` to include only the minimal footprint required for Module 1:
    - `pandas`, `numpy`, `pyarrow` (Data processing & Parquet serialization)
    - `SQLAlchemy`, `pyodbc` (Database connectivity & ORM)
    - `requests`, `requests-ntlm`, `urllib3` (PI Web API network layer)
    - `pytest` (Automated verification)

---

## 3. Comparison Matrix

| Aspect | Main Repository (Module 1) | Portable Release (`release/`) |
| :--- | :--- | :--- |
| **Taglist Structure** | Flat array (`sensors.json`) | **Grouped by equipment number** (`{"GT-2420A": [...]}`) |
| **Target Equipment** | Implicit | **Configurable via JSON (`target_equipment`) and CLI (`--equipment`)** |
| **Default Time Window** | 12 months (or 1 day test) | **Past 6 months** (`duration_months: 6`) |
| **Default Frequency** | 1 minute (`1m`) | **Hourly (`1h`)** |
| **Execution Entry Point** | Streamlit UI (`app.py`) / `main.py` | **Dedicated Standalone CLI (`run_module1.py`)** |
| **Module Scope** | Modules 1, 2, and 3 | **Module 1 only (Ingestion, Limits, SQL)** |
| **Portability** | Requires entire repository | **Fully standalone (can be copied to any directory/server)** |
| **Deduplication Method** | Matching `(af_path, type)` | **Identical: Matching `(af_path, type)` + Current execution timestamp** |
