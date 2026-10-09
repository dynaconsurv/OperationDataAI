@echo off
setlocal
cd /d "%~dp0"

echo ======================================================================
echo   PTTEP MODULE 1: PORTABLE EXECUTION LAUNCHER
echo ======================================================================

set "EMBED_PYTHON=%~dp0python_runtime\python.exe"
set "RUNTIME_ZIP=%~dp0python_runtime.zip"

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
    if %ERRORLEVEL% equ 0 (
        python "%~dp0run_module1.py" %*
    ) else (
        echo [ERROR] Neither portable Python nor system Python was found!
        echo Please run setup_runtime.bat to configure the portable environment.
        pause
        exit /b 1
    )
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Pipeline finished with error code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

endlocal
