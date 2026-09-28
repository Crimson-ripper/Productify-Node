@echo off
title Productify Node - Physical GPU & Compute Provider
cd /d "%~dp0\.."
echo ===================================================
echo  PRODUCTIFY NODE DESKTOP HYPERVISOR
echo ===================================================
echo Starting Productify Node Desktop Application...
py main.py
if %ERRORLEVEL% NEQ 0 (
    echo 'py' not found, trying 'python'...
    python main.py
)
pause
