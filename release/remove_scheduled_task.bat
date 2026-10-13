@echo off
setlocal

echo ======================================================================
echo   PTTEP MODULE 1: TASK SCHEDULER UNINSTALLER
echo ======================================================================
echo.

set "TASK_NAME=PTTEP_Module1_Ingestion"

echo This script will delete the scheduled task "%TASK_NAME%".
set /p CONFIRM="Are you sure you want to proceed? [y/N]: "
if /i "%CONFIRM%" neq "y" (
    echo Operation cancelled by user.
    pause
    exit /b 0
)

schtasks /Delete /TN "%TASK_NAME%" /F
if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] Task "%TASK_NAME%" was successfully removed from Task Scheduler.
) else (
    echo.
    echo [ERROR] Failed to delete task "%TASK_NAME%". It may not exist, or you need to run as Administrator.
)

pause
endlocal
