@echo off
REM ==============================================================================
REM PTTEP GT-2420A: 5-Minute Ingestion & Operating Limits Sync Runner
REM Invoked every 5 minutes via Windows Task Scheduler
REM ==============================================================================

set WORKDIR=C:\Users\Fuad\Documents\dev\PTTEP AI
set PYTHON_EXE=C:\Users\Fuad\AppData\Local\Python\pythoncore-3.14-64\python.exe

cd /d "%WORKDIR%"

REM Ensure logs directory exists
if not exist "logs" mkdir "logs"

echo [%DATE% %TIME%] Starting 5-minute incremental PI ingestion... >> "logs\scheduled_ingest.log"

REM 1. Pull latest 5-minute interpolated slice, append to Parquet, and sync limits to SQL
"%PYTHON_EXE%" main.py run-module1 --interval 5m --live >> "logs\scheduled_ingest.log" 2>&1

if %ERRORLEVEL% equ 0 (
    echo [%DATE% %TIME%] Ingestion completed successfully. >> "logs\scheduled_ingest.log"
    echo [%DATE% %TIME%] Running CorrelationDigitalTwin proactive anomaly diagnosis... >> "logs\scheduled_ingest.log"
    
    REM 2. Run CorrelationDigitalTwin on the newly arrived telemetry and save advisory
    "%PYTHON_EXE%" main.py run-module3 --load-model models\gt2420a_digital_twin.pkl --save-alert data\latest_advisory.json >> "logs\scheduled_ingest.log" 2>&1
    
    if %ERRORLEVEL% equ 0 (
        echo [%DATE% %TIME%] Digital Twin diagnosis completed and saved to data\latest_advisory.json. >> "logs\scheduled_ingest.log"
    ) else (
        echo [%DATE% %TIME%] Digital Twin diagnosis encountered error code %ERRORLEVEL%. >> "logs\scheduled_ingest.log"
    )
) else (
    echo [%DATE% %TIME%] Ingestion encountered error code %ERRORLEVEL%. >> "logs\scheduled_ingest.log"
)

