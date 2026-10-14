@echo off
REM ==============================================================================
REM PTTEP GT-2420A: FastAPI Predictive Service Daemon Runner
REM Runs continuously to serve Early Warning Advisories to PI Vision
REM ==============================================================================

set WORKDIR=C:\Users\Fuad\Documents\dev\PTTEP AI
set PYTHON_EXE=C:\Users\Fuad\AppData\Local\Python\pythoncore-3.14-64\python.exe

cd /d "%WORKDIR%"

if not exist "logs" mkdir "logs"

echo [%DATE% %TIME%] Starting PTTEP GT-2420A Predictive API on port 8000... >> "logs\api_service.log"

"%PYTHON_EXE%" main.py serve-api --host 0.0.0.0 --port 8000 >> "logs\api_service.log" 2>&1
