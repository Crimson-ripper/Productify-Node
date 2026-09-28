@echo off
title Productify Node - Provider Hypervisor
cd /d "%~dp0"
echo ===================================================
echo  PRODUCTIFY NODE - HYPERVISOR & SYSTEM TRAY
echo ===================================================
py main.py
if %ERRORLEVEL% NEQ 0 (
    python main.py
)
pause
