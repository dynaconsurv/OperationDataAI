@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ======================================================================
echo   PTTEP MODULE 1: PORTABLE EXECUTION LAUNCHER
echo ======================================================================

set "EMBED_PYTHON=%~dp0python_runtime\python.exe"
set "RUNTIME_ZIP=%~dp0python_runtime.zip"

REM Detect unattended / automated execution mode (Task Scheduler / CI)
set "IS_UNATTENDED=0"
if defined UNATTENDED set "IS_UNATTENDED=1"
if defined TASK_SCHEDULER set "IS_UNATTENDED=1"
for %%A in (%*) do (
    if /i "%%~A"=="--unattended" set "IS_UNATTENDED=1"
    if /i "%%~A"=="--no-pause" set "IS_UNATTENDED=1"
)

REM 1. Auto-extract bundled python_runtime.zip if uncompressed runtime is missing
if not exist "%EMBED_PYTHON%" (
    if exist "%RUNTIME_ZIP%" (
        echo [INFO] Extracting bundled portable Python runtime from python_runtime.zip...
        powershell -NoProfile -Command "Expand-Archive -Path '%RUNTIME_ZIP%' -DestinationPath '%~dp0' -Force"
    )
)

REM 2. Execute with embedded Python if available
if exist "%EMBED_PYTHON%" (
    echo [INFO] Using embedded portable Python runtime: %EMBED_PYTHON%
    "%EMBED_PYTHON%" "%~dp0run_module1.py" %*
) else (
    REM 3. Fallback to system Python
    echo [INFO] Embedded Python runtime not found. Checking system Python...
    where python >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        python "%~dp0run_module1.py" %*
    ) else (
        echo [ERROR] Neither portable Python nor system Python was found!
        echo Please run setup_runtime.bat to configure the portable environment.
        if "!IS_UNATTENDED!"=="0" pause
        exit /b 1
    )
)

set "EXIT_CODE=%ERRORLEVEL%"
if %EXIT_CODE% neq 0 (
    echo.
    echo [ERROR] Pipeline finished with error code %EXIT_CODE%.
    if "!IS_UNATTENDED!"=="0" pause
    exit /b %EXIT_CODE%
)

endlocal
