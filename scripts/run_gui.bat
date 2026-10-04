@echo off
title Productify Node — Hypervisor & Cloud Gaming Studio
cd /d "%~dp0\.."
echo ========================================================
echo   ⚡ PRODUCTIFY NODE — HYPERVISOR & CLOUD GAMING STUDIO
echo ========================================================
echo.

:: Check for administrative permissions to allow seamless driver setup
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Requesting Administrator privileges for driver and firewall support...
    powershell -Command "Start-Process cmd -ArgumentList '/k cd /d \"%~dp0\..\" && py main.py' -Verb RunAs"
    exit /b
)

py main.py
if %ERRORLEVEL% NEQ 0 (
    echo 'py' not found, trying 'python'...
    python main.py
)
pause
