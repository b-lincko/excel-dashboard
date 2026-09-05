@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
echo ============================================================
echo  Linkco MR API
echo  Folder: %CD%
echo ============================================================
if not exist "file.xlsx" (
  echo.
  echo ERROR: file.xlsx was not found in:
  echo   %CD%
  echo Put the Linkco workbook in this folder as file.xlsx
  echo.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Python venv missing. Close this window and run run.bat first.
  pause
  exit /b 1
)
echo Excel found: %CD%\file.xlsx
echo Starting http://127.0.0.1:8000 ...
echo Keep this window OPEN while using the dashboard.
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
echo.
echo API stopped.
pause
