@echo off
REM Tiny launcher. Real work is in docker-run.ps1 so paths with (1) or (2) cannot break cmd.exe.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker-run.ps1"
if errorlevel 1 pause
