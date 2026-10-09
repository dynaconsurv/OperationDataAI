@echo off
setlocal
cd /d "%~dp0"

echo ======================================================================
echo   PTTEP MODULE 1: PORTABLE PYTHON RUNTIME BOOTSTRAPPER
echo ======================================================================

echo [1/3] Downloading official Python 3.11 embeddable runtime...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip', 'python-embed.zip')"

if not exist "python-embed.zip" (
    echo [ERROR] Failed to download python-embed.zip. Check internet connection.
    pause
    exit /b 1
)

echo [2/3] Extracting Python embeddable into python_runtime\...
powershell -Command "Expand-Archive -Path 'python-embed.zip' -DestinationPath 'python_runtime' -Force"
del /f /q "python-embed.zip"

echo Configuring python311._pth...
powershell -Command "$p = 'python_runtime\python311._pth'; $c = 'python311.zip`r`n.`r`n..`r`nLib\site-packages`r`nimport site'; Set-Content $p $c"
mkdir "python_runtime\Lib\site-packages" 2>nul

echo [3/3] Installing pip and dependencies from requirements.txt...
powershell -Command "(New-Object Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', 'python_runtime\get-pip.py')"
.\python_runtime\python.exe python_runtime\get-pip.py --no-warn-script-location
del /f /q "python_runtime\get-pip.py"

.\python_runtime\python.exe -m pip install -r requirements.txt --no-warn-script-location

echo ======================================================================
echo   PORTABLE PYTHON RUNTIME SETUP COMPLETE!
echo   You can now execute run.bat directly.
echo ======================================================================
pause
endlocal
