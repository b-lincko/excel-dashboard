@echo off
REM ============================================================================
REM Linkco MR - first-run setup, then the main server.  (Windows)
REM
REM   setup.bat                 .env wizard on :8081 if .env missing, then main server
REM   setup.bat --setup         force the wizard (reconfigure), then main server
REM   setup.bat --wizard-only   wizard and stop (do not start the server)
REM
REM Creates backend\.venv + installs requirements on first run, then hands over
REM to backend\launch.py: the web setup wizard (port 8081) runs when needed and
REM the main server starts from the .env it writes. Close the wizard tab when
REM done; press Ctrl+C here to stop the main server.
REM ============================================================================
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Linkco MR - setup / launch
echo ============================================================

set "PYCMD="
py -3 --version >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (python --version >nul 2>nul && set "PYCMD=python")
if not defined PYCMD (
  echo ERROR: Python 3 not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during installation.
  exit /b 1
)

if exist "backend\.venv\Scripts\python.exe" (
  echo Using existing virtual environment: backend\.venv
) else (
  echo Creating virtual environment + installing requirements ^(first run only^)...
  %PYCMD% -m venv backend\.venv
  if errorlevel 1 (
    echo ERROR: could not create the virtual environment.
    exit /b 1
  )
  "backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
  "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
  if errorlevel 1 (
    echo ERROR: requirements install failed - check the output above.
    exit /b 1
  )
)

echo Wizard ^(when needed^) on http://0.0.0.0:8081 - main server after Save+Finish.
echo Arguments: %*   ^(--setup forces the wizard, --wizard-only stops after it^)
echo.

"backend\.venv\Scripts\python.exe" backend\launch.py %*
