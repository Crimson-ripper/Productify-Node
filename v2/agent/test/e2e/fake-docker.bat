@echo off
rem Stand-in for docker.exe in integration tests. Logs every call.
echo %* >> "%~dp0docker-calls.log"
if "%1"=="version" (echo 27.0& exit /b 0)
if "%1"=="exec" (echo hello from container& exit /b 0)
echo ok
exit /b 0
