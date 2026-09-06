@echo off
REM Tiny launcher. Real work is in run.ps1 so paths with (1) or (3) cannot break cmd.exe.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
if errorlevel 1 pause
