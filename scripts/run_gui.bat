@echo off
title Productify Node - Physical GPU & Compute Provider
echo ===================================================
echo  ⚡ PRODUCTIFY NODE DESKTOP CLIENT
echo ===================================================
echo Starting Productify Node Desktop Application...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo Python not found as 'python', trying 'py'...
    py main.py
)
pause
