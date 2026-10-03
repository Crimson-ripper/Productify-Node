@echo off
:: Productify Node — 1-Click Cloud Gaming Stack Installer
title Productify Node - Cloud Gaming Stack Setup
echo ========================================================
echo   ⚡ PRODUCTIFY NODE — HOST CLOUD GAMING SETUP WIZARD
echo ========================================================
echo.

:: Check for administrative permissions
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Running with Administrative privileges.
) else (
    echo [!] Requesting Administrative privileges to install ViGEmBus and Sunshine...
    powershell -Command "Start-Process cmd -ArgumentList '/k cd /d \"%~dp0\" && py install_gaming_stack.py' -Verb RunAs"
    exit /b
)

:: Run Python Installer
py install_gaming_stack.py
echo.
echo ========================================================
echo   Setup process completed. Press any key to exit.
echo ========================================================
pause >nul
