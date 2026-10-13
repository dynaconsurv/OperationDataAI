@echo off
setlocal enabledelayedexpansion

echo ======================================================================
echo   PTTEP MODULE 1: AUTOMATED TASK SCHEDULER INSTALLER
echo ======================================================================
echo.

REM Verify Administrator Privileges
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARNING] This script is NOT running with elevated Administrator privileges.
    echo Creating scheduled tasks (especially for SYSTEM accounts) usually requires Admin rights.
    echo If this fails, right-click create_scheduled_task.bat and select 'Run as Administrator'.
    echo.
)

set "TASK_NAME=PTTEP_Module1_Ingestion"
set "RELEASE_DIR=%~dp0"
REM Remove trailing backslash if present
if "%RELEASE_DIR:~-1%"=="\" set "RELEASE_DIR=%RELEASE_DIR:~0,-1%"
set "RUN_BAT=%RELEASE_DIR%\run.bat"

echo Configuration Details:
echo   - Task Name:         %TASK_NAME%
echo   - Target Script:     %RUN_BAT%
echo   - Working Directory: %RELEASE_DIR%
echo.

echo Choose Execution Frequency:
echo   [1] Daily at 01:00 AM (Recommended for standard daily limits)
echo   [2] Hourly (Every 1 hour)
echo   [3] Every 4 Hours
echo   [4] Custom Time (Daily at HH:MM)
echo.
set /p FREQ_CHOICE="Select schedule [1-4, Default=1]: "
if "%FREQ_CHOICE%"=="" set "FREQ_CHOICE=1"

set "SCHED_TYPE=DAILY"
set "START_TIME=01:00"
set "REPEAT_INTERVAL="

if "%FREQ_CHOICE%"=="1" (
    set "SCHED_TYPE=DAILY"
    set "START_TIME=01:00"
) else if "%FREQ_CHOICE%"=="2" (
    set "SCHED_TYPE=HOURLY"
    set "REPEAT_INTERVAL=1"
) else if "%FREQ_CHOICE%"=="3" (
    set "SCHED_TYPE=HOURLY"
    set "REPEAT_INTERVAL=4"
) else if "%FREQ_CHOICE%"=="4" (
    set "SCHED_TYPE=DAILY"
    set /p START_TIME="Enter start time (24-hour HH:MM, e.g. 02:30): "
    if "!START_TIME!"=="" set "START_TIME=01:00"
) else (
    set "SCHED_TYPE=DAILY"
    set "START_TIME=01:00"
)

echo.
echo Choose Execution Security Principal:
echo   [1] Local SYSTEM Account (Headless background service, runs without user logged on, no password needed)
echo   [2] Current User Account (%USERNAME%)
echo.
set /p USER_CHOICE="Select user account [1-2, Default=1]: "
if "%USER_CHOICE%"=="" set "USER_CHOICE=1"

set "PRINCIPAL_USER=NT AUTHORITY\SYSTEM"
if "%USER_CHOICE%"=="2" (
    set "PRINCIPAL_USER=%USERNAME%"
)

echo.
echo [INFO] Generating Task Scheduler definition...
set "TASK_XML=%TEMP%\pttep_module1_task.xml"

REM Build XML definition for maximum fidelity (WorkingDirectory, Concurrency, Restart)
(
echo ^<?xml version="1.0" encoding="UTF-16"?^>
echo ^<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"^>
echo   ^<RegistrationInfo^>
echo     ^<Description^>PTTEP Module 1 - Telemetry Ingestion and Operating Limits Calculation^</Description^>
echo     ^<URI^>\%TASK_NAME%^</URI^>
echo   ^</RegistrationInfo^>
echo   ^<Triggers^>
if "%SCHED_TYPE%"=="DAILY" (
    echo     ^<CalendarTrigger^>
    echo       ^<StartBoundary^>2026-01-01T%START_TIME%:00^</StartBoundary^>
    echo       ^<Enabled^>true^</Enabled^>
    echo       ^<ScheduleByDay^>
    echo         ^<DaysInterval^>1^</DaysInterval^>
    echo       ^</ScheduleByDay^>
    echo     ^</CalendarTrigger^>
) else (
    echo     ^<TimeTrigger^>
    echo       ^<StartBoundary^>2026-01-01T00:00:00^</StartBoundary^>
    echo       ^<Enabled^>true^</Enabled^>
    echo       ^<Repetition^>
    echo         ^<Interval^>PT%REPEAT_INTERVAL%H^</Interval^>
    echo         ^<StopAtDurationEnd^>false^</StopAtDurationEnd^>
    echo       ^</Repetition^>
    echo     ^</TimeTrigger^>
)
echo   ^</Triggers^>
echo   ^<Principals^>
echo     ^<Principal id="Author"^>
if "%PRINCIPAL_USER%"=="NT AUTHORITY\SYSTEM" (
    echo       ^<UserId^>S-1-5-18^</UserId^>
    echo       ^<RunLevel^>HighestAvailable^</RunLevel^>
) else (
    echo       ^<LogonType^>InteractiveToken^</LogonType^>
    echo       ^<RunLevel^>HighestAvailable^</RunLevel^>
)
echo     ^</Principal^>
echo   ^</Principals^>
echo   ^<Settings^>
echo     ^<MultipleInstancesPolicy^>IgnoreNew^</MultipleInstancesPolicy^>
echo     ^<DisallowStartIfOnBatteries^>false^</DisallowStartIfOnBatteries^>
echo     ^<StopIfGoingOnBatteries^>false^</StopIfGoingOnBatteries^>
echo     ^<AllowHardTerminate^>true^</AllowHardTerminate^>
echo     ^<StartWhenAvailable^>true^</StartWhenAvailable^>
echo     ^<RunOnlyIfNetworkAvailable^>true^</RunOnlyIfNetworkAvailable^>
echo     ^<IdleSettings^>
echo       ^<StopOnIdleEnd^>false^</StopOnIdleEnd^>
echo       ^<RestartOnIdle^>false^</RestartOnIdle^>
echo     ^</IdleSettings^>
echo     ^<AllowStartOnDemand^>true^</AllowStartOnDemand^>
echo     ^<Enabled^>true^</Enabled^>
echo     ^<Hidden^>false^</Hidden^>
echo     ^<RunOnlyIfIdle^>false^</RunOnlyIfIdle^>
echo     ^<WakeToRun^>false^</WakeToRun^>
echo     ^<ExecutionTimeLimit^>PT4H^</ExecutionTimeLimit^>
echo     ^<Priority^>7^</Priority^>
echo   ^</Settings^>
echo   ^<Actions Context="Author"^>
echo     ^<Exec^>
echo       ^<Command^>%RUN_BAT%^</Command^>
echo       ^<Arguments^>--unattended^</Arguments^>
echo       ^<WorkingDirectory^>%RELEASE_DIR%^</WorkingDirectory^>
echo     ^</Exec^>
echo   ^</Actions^>
echo ^</Task^>
) > "%TASK_XML%"

echo [INFO] Registering task "%TASK_NAME%" via Task Scheduler...
schtasks /Create /TN "%TASK_NAME%" /XML "%TASK_XML%" /F >nul 2>&1
set "REG_STATUS=%ERRORLEVEL%"

REM Fallback to standard CLI command if XML registration fails
if %REG_STATUS% neq 0 (
    echo [INFO] Advanced XML registration returned %REG_STATUS%. Attempting direct schtasks command...
    if "%SCHED_TYPE%"=="DAILY" (
        schtasks /Create /TN "%TASK_NAME%" /TR "\"%RUN_BAT%\" --unattended" /SC DAILY /ST %START_TIME% /RU "%PRINCIPAL_USER%" /RL HIGHEST /F
    ) else (
        schtasks /Create /TN "%TASK_NAME%" /TR "\"%RUN_BAT%\" --unattended" /SC HOURLY /MO %REPEAT_INTERVAL% /RU "%PRINCIPAL_USER%" /RL HIGHEST /F
    )
    set "REG_STATUS=%ERRORLEVEL%"
)

if exist "%TASK_XML%" del /f /q "%TASK_XML%" >nul 2>&1

if %REG_STATUS% equ 0 (
    echo.
    echo ======================================================================
    echo   SUCCESS: Task "%TASK_NAME%" registered successfully!
    echo ======================================================================
    echo.
    echo To verify or manage the task:
    echo   - View status:      schtasks /Query /TN "%TASK_NAME%" /FO LIST /V
    echo   - Run immediately:  schtasks /Run /TN "%TASK_NAME%"
    echo   - GUI Manager:      taskschd.msc
    echo   - Remove task:      remove_scheduled_task.bat
    echo.
) else (
    echo.
    echo ======================================================================
    echo   ERROR: Failed to register task (Error code: %REG_STATUS%).
    echo   Please run this script as Administrator.
    echo ======================================================================
    echo.
)

pause
endlocal
