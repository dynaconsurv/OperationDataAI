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
│   ├── config.json              # Main configuration (PI Web API, Database, Limits, Time Range)
│   ├── sensors.json             # Taglist grouped by equipment number (GT-2420A)
│   └── last_run_meta.json       # Pipeline execution metadata & statistics
├── data/                        # Generated Parquet caches, CSV limits, and SQLite databases
├── logs/                        # Execution logs (module1.log)
├── python_runtime/              # Bundled embedded Python 3.11 environment
├── python_runtime.zip           # Compressed portable Python archive
├── src/
│   ├── __init__.py
│   ├── config_manager.py        # Portable configuration & sensor catalog manager
│   ├── module1_pi_ingestion/
│   │   ├── __init__.py
│   │   ├── pi_client.py         # PI Web API client with batching & ledger
│   │   ├── limits_calculator.py # Operating Limits statistical calculator
│   │   ├── sql_storage.py       # SQL storage engine with deduplication
│   │   └── pipeline.py          # Orchestration pipeline
│   └── utils/
│       ├── __init__.py
│       ├── logger.py            # Formatted console & file logger
│       └── mock_generator.py    # Synthetic telemetry generator for offline testing
├── tests/
│   └── test_portable_module1.py # Portable verification test suite
├── create_scheduled_task.bat    # Automated Windows Task Scheduler installer
├── remove_scheduled_task.bat    # Automated Windows Task Scheduler uninstaller
├── run.bat                      # One-click portable launcher (supports --unattended)
├── run_module1.bat              # Batch launcher alias
├── run_module1.py               # Standalone CLI entry point
├── setup_runtime.bat            # Runtime extraction & verification script
├── requirements.txt             # Python dependencies
├── CHANGELOG_ADJUSTMENTS.md      # Detailed summary of adjustments from main repository
└── README.md                    # This documentation
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
If deploying without bundled `python_runtime/`:
```bash
pip install -r requirements.txt
python run_module1.py
```

---

## 📅 Windows Task Scheduler Deployment

Deploying Module 1 via **Windows Task Scheduler** enables automated, unattended execution (e.g., daily recalculation of 6-month statistical operating limits and telemetry sync).

### Operational Architecture & Safety

- **Headless Execution**: The launcher supports `--unattended` (or environment variable `UNATTENDED=1`), which disables interactive `pause` prompts so automated runs never hang on errors.
- **PI System Protection**: The built-in batch throttling (5-second sleep after every 5 batch requests) remains active, protecting PI Web API and other active PI Vision users.
- **Outage-Aware Checkpointing**: If a network disconnect or scheduled reboot occurs mid-run, the pipeline records completed slices in `data/completed_slices.json`. The next scheduled task run will automatically resume from the last completed slice.
- **Database Deduplication**: Matching `(af_path, type)` ensures unchanged threshold values are not duplicated in the SQL database.

---

### Option 1: Turnkey Automated Setup via Script (Recommended)

The portable release includes an automated configuration script:

1. Right-click **[`create_scheduled_task.bat`](create_scheduled_task.bat)** and select **Run as Administrator**.
2. Follow the interactive prompts:
   - **Frequency**:
     - `[1]` Daily at 01:00 AM (Recommended for standard daily limits)
     - `[2]` Hourly (Every 1 hour)
     - `[3]` Every 4 Hours
     - `[4]` Custom Time (Daily at `HH:MM`)
   - **Security Account**:
     - `[1]` Local `SYSTEM` (`NT AUTHORITY\SYSTEM`) — Runs 24/7 in background without user logon, no password required.
     - `[2]` Current User Account (`%USERNAME%`).
3. The script automatically generates an XML task definition with the correct working directory, 4-hour execution timeout, and `IgnoreNew` concurrency policy, then registers it in Windows Task Scheduler.

To remove the scheduled task at any time, run **[`remove_scheduled_task.bat`](remove_scheduled_task.bat)**.

---

### Option 2: Step-by-Step GUI Setup (`taskschd.msc`)

To manually configure the task through the Windows Task Scheduler GUI:

#### Step 1: Open Task Scheduler
Press `Win + R`, type `taskschd.msc`, and press **Enter**.

#### Step 2: Create Task
In the right-hand **Actions** panel, click **Create Task...** *(Do NOT use "Create Basic Task", as it lacks critical working directory and concurrency settings)*.

#### Step 3: General Tab
- **Name**: `PTTEP_Module1_Ingestion`
- **Description**: `PTTEP Module 1 - Telemetry Ingestion and Operating Limits Calculation`
- **Security options**:
  - Select **Run whether user is logged on or not**
  - Check **Run with highest privileges**
- **Configure for**: Select `Windows 10` or `Windows Server 2016 / 2019 / 2022`

#### Step 4: Triggers Tab
1. Click **New...**
2. **Begin the task**: `On a schedule`
3. **Settings**:
   - For Daily: Select **Daily**, recur every `1` days, Start: `01:00:00`
   - For Hourly: Select **Daily**, check **Repeat task every**: `1 hour` for a duration of `1 day`
4. Ensure **Enabled** is checked.
5. Click **OK**.

#### Step 5: Actions Tab (Critical Configuration)
1. Click **New...**
2. **Action**: `Start a program`
3. **Program/script**:
   ```
   cmd.exe
   ```
4. **Add arguments**:
   ```
   /c ""C:\path\to\release\run.bat" --unattended"
   ```
   *(Replace `C:\path\to\release\` with your actual absolute deployment folder path)*
5. **Start in (crucial)**:
   ```
   C:\path\to\release
   ```

> [!IMPORTANT]
> **Always set the "Start in" directory** to the absolute path of the `release` folder (e.g. `C:\PTTEP_AI\release`). If left blank, Windows defaults the working directory to `C:\Windows\System32`, causing relative paths to `config/`, `data/`, and `python_runtime/` to fail.

#### Step 6: Conditions Tab
- **Power**: **Uncheck** *"Start the task only if the computer is on AC power"* (ensures execution on VMs or laptops).
- **Power**: **Uncheck** *"Stop if the computer switches to battery power"*.
- **Network**: Check *"Start only if the following network connection is available"* and select `Any connection`.

#### Step 7: Settings Tab
- Check **Allow task to be run on demand**.
- Check **Run task as soon as possible after a scheduled start is missed**.
- Check **If the task fails, restart every**: `10 minutes` (Attempt to restart up to: `3` times).
- Check **Stop the task if it runs longer than**: `4 hours`.
- If the running task does not end when requested: check **Force the task to stop**.
- **If the task is already running, then the following rule applies**: Select **Do not start a new instance** *(avoids duplicate overlapping queries to PI Web API)*.

Click **OK** to save the task. If prompted, enter the account credentials.

---

### Option 3: Command-Line Setup via `schtasks`

You can also create and manage the task directly from an elevated Command Prompt or PowerShell terminal.

#### 1. Register Daily Task (at 01:00 AM as SYSTEM):
```cmd
schtasks /Create /TN "PTTEP_Module1_Ingestion" /TR "\"C:\path\to\release\run.bat\" --unattended" /SC DAILY /ST 01:00 /RU "NT AUTHORITY\SYSTEM" /RL HIGHEST /F
```

#### 2. Register Hourly Task (Every 1 hour as SYSTEM):
```cmd
schtasks /Create /TN "PTTEP_Module1_Ingestion" /TR "\"C:\path\to\release\run.bat\" --unattended" /SC HOURLY /MO 1 /RU "NT AUTHORITY\SYSTEM" /RL HIGHEST /F
```

#### 3. Register with a Dedicated Service Account:
```cmd
schtasks /Create /TN "PTTEP_Module1_Ingestion" /TR "\"C:\path\to\release\run.bat\" --unattended" /SC DAILY /ST 01:00 /RU "DOMAIN\service_account" /RP "AccountPassword" /RL HIGHEST /F
```

#### 4. Trigger an Immediate Test Run:
```cmd
schtasks /Run /TN "PTTEP_Module1_Ingestion"
```

#### 5. Check Task Status & Last Run Result:
```cmd
schtasks /Query /TN "PTTEP_Module1_Ingestion" /FO LIST /V
```

#### 6. Delete / Uninstall the Task:
```cmd
schtasks /Delete /TN "PTTEP_Module1_Ingestion" /F
```

---

### 🔍 Verification & Monitoring

After the scheduled task executes, verify health and telemetry outputs using the following checkpoints:

1. **Execution Logs**: Inspect **[`logs/module1.log`](logs/module1.log)** for timestamps, PI batch requests, limits calculated, and SQL insertion statistics.
2. **Metadata Snapshot**: Check **[`config/last_run_meta.json`](config/last_run_meta.json)** for execution status, data points collected, and time range.
3. **Task Scheduler Return Codes**:
   - `0x0` (`0`): **Success** — Pipeline executed and exited cleanly.
   - `0x1` (`1`): **Application Error** — Check `logs/module1.log` for PI Web API connectivity or SQL authentication issues.
   - `0x41301`: **Task is Currently Running** — Pipeline is actively ingesting slices.
   - `0x80070005`: **Access Denied** — Ensure the task runs with elevated privileges or valid service account credentials.
   - `0xC000013A`: **Terminated** — Task was interrupted or cancelled.
4. **SQL Database Verification**:
   Query the target SQL table to confirm updated records:
   ```sql
   SELECT TOP 20 af_path, type, value, updated_at
   FROM operating_limits
   ORDER BY updated_at DESC;
   ```
5. **Windows Event Log**: Detailed task lifecycle events are available in:
   `Event Viewer -> Applications and Services Logs -> Microsoft -> Windows -> TaskScheduler -> Operational`

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
