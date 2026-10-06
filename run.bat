@echo off
title Productify Node - Hypervisor and Cloud Gaming Studio
setlocal

:: Resolve directory reliably without trailing backslash escaping issues
set "NODE_DIR=%~dp0"
if "%NODE_DIR:~-1%"=="\" set "NODE_DIR=%NODE_DIR:~0,-1%"
cd /d "%NODE_DIR%"

echo ========================================================
echo   PRODUCTIFY NODE - HYPERVISOR AND CLOUD GAMING STUDIO
echo ========================================================
echo.
echo [*] Launching Productify Node Desktop Application...

:: Check for py launcher
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py main.py %*
    goto check_exit
)

:: Check for python
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python main.py %*
    goto check_exit
)

:: Check for compiled executable
if exist "dist\ProductifyNode.exe" (
    echo [*] Python not detected in PATH. Starting compiled ProductifyNode.exe...
    start "" "dist\ProductifyNode.exe" %*
    goto done
)
if exist "ProductifyNode.exe" (
    echo [*] Starting compiled ProductifyNode.exe...
    start "" "ProductifyNode.exe" %*
    goto done
)

echo [!] Error: Neither Python nor ProductifyNode.exe could be found.
echo     Please install Python 3.10+ from python.org or download ProductifyNode.exe.
pause
exit /b 1

:check_exit
if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] Productify Node closed with exit code %ERRORLEVEL%.
    pause
)

:done
