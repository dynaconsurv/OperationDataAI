# PTTEP Module 1: Portable Release

A self-contained, portable edition of **Module 1 (PI Telemetry Ingestion & Operating Limits Engine)** designed for deployment on standalone application servers, scheduled tasks, and headless production environments.

---

## 🚀 Key Capabilities

- **Equipment-Grouped Taglist**: Extracts telemetry for preconfigured sensor attributes grouped by equipment number (defaults to **`GT-2420A`**, 162 sensor attributes).
- **6-Month Hourly Ingestion**: Extracts hourly interpolated data (`1h`) covering the past 6 months (duration and interval fully configurable via JSON).
- **Batching & Throttling**: Batch streaming (25 tags per request) with a 5-second back-off delay after every 5 batch calls to safeguard PI Web API and PI Vision users.
- **Outage-Aware Checkpointing**: Automatically tracks completed time slices in `completed_slices.json`, preventing redundant re-querying during unit shutdowns.
- **Statistical Operating Limits**: Computes **Normal**, **HH** (High-High), **H** (High), **L** (Low), and **LL** (Low-Low) thresholds using non-parametric Percentiles (or parametric Sigma).
- **SQL Deduplication & Change Detection**: Matches `(af_path, type)` against existing database rows. If a threshold already exists and has not changed, insertion is skipped. If a threshold is new or changed, it is inserted with the current execution timestamp. Supports **MS SQL Server** with automatic **SQLite** fallback.

---

## 📂 Directory Structure

```
release/
├── config/
│   ├── config.json          # Main configuration (PI Web API, Database, Limits, Time Range)
│   ├── sensors.json         # Taglist grouped by equipment number (GT-2420A)
│   └── last_run_meta.json   # Pipeline execution metadata & statistics
├── data/                    # Generated Parquet caches, CSV limits, and SQLite databases
├── logs/                    # Execution logs (module1.log)
├── src/
│   ├── __init__.py
│   ├── config_manager.py     # Portable configuration & sensor catalog manager
│   ├── module1_pi_ingestion/
│   │   ├── __init__.py
│   │   ├── pi_client.py      # PI Web API client with batching & ledger
│   │   ├── limits_calculator.py # Operating Limits statistical calculator
│   │   ├── sql_storage.py    # SQL storage engine with deduplication
│   │   └── pipeline.py       # Orchestration pipeline
│   └── utils/
│       ├── __init__.py
│       ├── logger.py         # Formatted console & file logger
│       └── mock_generator.py # Synthetic telemetry generator for offline testing
├── tests/
│   └── test_portable_module1.py # Portable verification test suite
├── run_module1.py            # Standalone CLI entry point
├── requirements.txt          # Python dependencies
├── CHANGELOG_ADJUSTMENTS.md  # Detailed summary of adjustments from main repository
└── README.md                 # This documentation
```

---

## ⚙️ Configuration Reference

### 1. `config/config.json`

```json
{
  "target_equipment": "GT-2420A",
  "pi_web_api": {
    "base_url": "https://kul-pivision.pttep.com/piwebapi",
    "auth_type": "basic",
    "user": "pi-ai",
    "password": "your_password_here",
    "verify_ssl": false,
    "timeout_seconds": 30,
    "mock_mode": false,
    "query_mode": "interpolated",
    "sample_interval": "1h",
    "duration_months": 6,
    "slice_days": 30,
    "batch_size": 25,
    "batch_throttle_calls": 5,
    "batch_throttle_delay_seconds": 5.0
  },
  "database": {
    "engine": "mssql",
    "host": "localhost",
    "port": 1433,
    "database": "PTTEP_AI",
    "user": "pi-ai",
    "password": "your_password_here",
    "driver": "SQL Server",
    "table_name": "operating_limits",
    "use_sqlite_fallback": true,
    "sqlite_path": "data/operating_limits.db",
    "deduplication_tolerance": 0.0001
  },
  "operating_limits": {
    "method": "percentile",
    "normal_stat": "median",
    "percentiles": {
      "ll": 1.0,
      "l": 5.0,
      "h": 95.0,
      "hh": 99.0
    },
    "sigma_multipliers": {
      "ll": 3.0,
      "l": 2.0,
      "h": 2.0,
      "hh": 3.0
    }
  },
  "storage": {
    "parquet_file": "data/historical_data_hourly.parquet",
    "limits_csv_file": "data/operating_limits.csv",
    "completed_slices_file": "data/completed_slices.json"
  }
}
```

### 2. `config/sensors.json` (Grouped by Equipment)

Sensors are grouped under equipment keys (`GT-2420A`). Additional equipment can be added as adjacent keys:

```json
{
  "GT-2420A": [
    {
      "id": 1,
      "equipment_id": "GT-2420A",
      "parent": "MALAYSIA\\BORF\\GTG\\GT-2420A\\Air Filter System\\Ambient Inlet Pressure",
      "attribute_name": "Parameter",
      "full_af_path": "MALAYSIA\\BORF\\GTG\\GT-2420A\\Air Filter System\\Ambient Inlet Pressure",
      "subsystem": "Air Filter System",
      "tag_name": "Ambient Inlet Pressure",
      "category": "Pressure",
      "unit": "barg",
      "web_id": "F1AbE5cqYAPyzXUGOIYCd8upOcQU3uXDiS-8RGf-_Q72Pfl3wVcg2479IeF0OI3c4SvwFYQS1VMLVBJQUZcR0VHIFJQTVxNQUxBWVNJQVxCT1JGXEdUR1xHVC0yNDIwQVxBSVIgRklMVEVSIFNZU1RFTVxBTUJJRU5UIElOTEVUIFBSRVNTVVJFfFBBUkFNRVRFUg"
    }
  ]
}
```

---

## 🏃 How to Run

### Zero Installation Required (Bundled Embedded Python)
The release folder includes an embedded **Python 3.11 runtime (`python_runtime/`)** with all required packages pre-installed (`pandas`, `numpy`, `pyarrow`, `SQLAlchemy`, `pyodbc`, `requests`, `requests-ntlm`, etc.). **You do not need to install Python on the destination host.**

#### Option A: One-Click Windows Batch Launcher (Recommended)
Simply double-click or execute `run.bat`:
```cmd
run.bat
```
Pass arguments directly to `run.bat`:
```cmd
run.bat --mock
run.bat --equipment GT-2420A --months 6 --interval 1h
```

#### Option B: Direct Embedded Python Execution
```cmd
python_runtime\python.exe run_module1.py
python_runtime\python.exe run_module1.py --mock
```

#### Option C: Using System Python (Fallback)
If deploying without `python_runtime/`:
```bash
pip install -r requirements.txt
python run_module1.py
```

---

## 🗄️ SQL Persistence & Deduplication Logic

Operating limits are stored in the `operating_limits` table:

```sql
CREATE TABLE operating_limits (
    id INT IDENTITY(1,1) PRIMARY KEY,
    af_path VARCHAR(500) NOT NULL,
    value FLOAT NOT NULL,
    type VARCHAR(50) NOT NULL,        -- 'Normal', 'HH', 'H', 'L', 'LL'
    updated_at DATETIME NOT NULL      -- Current execution timestamp
);
CREATE INDEX idx_path_type ON operating_limits(af_path, type);
```

### Deduplication Rules:
1. For every calculated threshold, the storage manager checks if `(af_path, type)` exists in the database.
2. If the record exists and `|new_value - existing_value| <= deduplication_tolerance` (default `0.0001`):
   - **Skip insert**: `sql_skipped += 1`.
3. If the record does not exist or the value has changed:
   - **Insert new row**: `sql_inserted += 1` with `updated_at = current_timestamp`.

---

## 🧪 Testing

Run the automated test suite to verify all portable functionality:
```bash
python -m pytest tests/ -v
```
All 3 portable integration tests verify grouped sensor catalog resolution, SQL deduplication, and end-to-end pipeline execution.
