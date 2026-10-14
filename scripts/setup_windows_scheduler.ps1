# ==============================================================================
# PTTEP GT-2420A: Automated Windows Task Scheduler Setup (Option B)
# Configures:
#   1. PTTEP_GT2420A_5Min_Ingest   - Runs every 5 minutes (Ingest + Limits + Parquet)
#   2. PTTEP_GT2420A_API_Service   - Runs at System Startup (FastAPI daemon)
# ==============================================================================

$WorkDir = "C:\Users\Fuad\Documents\dev\PTTEP AI"
$IngestBatch = "$WorkDir\scripts\run_5min_ingest.bat"
$ApiBatch = "$WorkDir\scripts\run_api_service.bat"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " PTTEP GT-2420A: Windows Task Scheduler Automation Setup " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# Task 1: 5-Minute Ingestion Task
# ------------------------------------------------------------------------------
$TaskName1 = "PTTEP_GT2420A_5Min_Ingest"
Write-Host "`n[1/2] Configuring $TaskName1..." -ForegroundColor Yellow

# Unregister existing task if present
Unregister-ScheduledTask -TaskName $TaskName1 -Confirm:$false -ErrorAction SilentlyContinue

$Action1 = New-ScheduledTaskAction -Execute $IngestBatch -WorkingDirectory $WorkDir
# Trigger: Start now, repeat every 5 minutes indefinitely
$Trigger1 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5)
$Settings1 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName1 -Action $Action1 -Trigger $Trigger1 -Settings $Settings1 -Description "PTTEP GT-2420A: Ingests 5-minute PI telemetry and persists to Parquet & SQL" | Out-Null
Write-Host "  -> Task '$TaskName1' registered successfully (Interval: 5 minutes)." -ForegroundColor Green

# ------------------------------------------------------------------------------
# Task 2: FastAPI Service Daemon (Runs at Startup)
# ------------------------------------------------------------------------------
$TaskName2 = "PTTEP_GT2420A_API_Service"
Write-Host "`n[2/2] Configuring $TaskName2..." -ForegroundColor Yellow

Unregister-ScheduledTask -TaskName $TaskName2 -Confirm:$false -ErrorAction SilentlyContinue

$Action2 = New-ScheduledTaskAction -Execute $ApiBatch -WorkingDirectory $WorkDir
$Trigger2 = New-ScheduledTaskTrigger -AtStartup
$Settings2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName2 -Action $Action2 -Trigger $Trigger2 -Settings $Settings2 -Description "PTTEP GT-2420A: FastAPI service hosting Digital Twin Early Warning Advisories for PI Vision" | Out-Null
Write-Host "  -> Task '$TaskName2' registered successfully (Trigger: At Startup)." -ForegroundColor Green

Write-Host "`nSetup complete! You can view these tasks in Windows Task Scheduler (taskschd.msc)." -ForegroundColor Cyan
