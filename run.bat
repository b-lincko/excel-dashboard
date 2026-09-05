@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "API_PORT=8000"
set "UI_PORT=5173"

echo ============================================================
echo   Linkco MR Dashboard — install ^& run
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python 3.11+ is required and was not found on PATH.
    echo Install from https://www.python.org/downloads/ and tick "Add Python to PATH".
    pause
    exit /b 1
  )
  set "PYTHON=py -3"
) else (
  set "PYTHON=python"
)

where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: Node.js / npm is required and was not found on PATH.
  echo Install LTS from https://nodejs.org/
  pause
  exit /b 1
)

echo [1/4] Python virtual environment
if not exist ".venv\Scripts\python.exe" (
  echo       creating .venv ...
  %PYTHON% -m venv .venv
  if errorlevel 1 (
    echo ERROR: failed to create virtual environment.
    pause
    exit /b 1
  )
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
echo       installing backend packages ...
pip install -r "backend\requirements.txt"
if errorlevel 1 (
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

echo.
echo [2/4] Frontend packages
if not exist "frontend\node_modules" (
  pushd frontend
  call npm install
  if errorlevel 1 (
    popd
    echo ERROR: npm install failed.
    pause
    exit /b 1
  )
  popd
) else (
  echo       node_modules already present
)

echo.
echo [3/4] Excel workbook
if not exist "file.xlsx" (
  echo ERROR: file.xlsx not found in %CD%
  echo Place the Linkco MR workbook here ^(source of truth^).
  pause
  exit /b 1
)
echo       using %CD%\file.xlsx

echo.
echo [4/4] Starting servers
echo       API  - http://127.0.0.1:%API_PORT%
echo       UI   - http://127.0.0.1:%UI_PORT%
echo.
echo       Sign in:  admin / admin123
echo                 manager / manager123
echo                 user / user123
echo.
echo Two windows will open. Close them ^(or press Ctrl+C in each^) to stop.
echo ============================================================
echo.

start "Linkco MR API" cmd /k "cd /d "%~dp0backend" && "%~dp0.venv\Scripts\python.exe" run.py"
timeout /t 2 /nobreak >nul
start "Linkco MR UI" cmd /k "cd /d "%~dp0frontend" && npm run dev -- --host 0.0.0.0 --port %UI_PORT%"

echo Servers launched.
echo Open http://127.0.0.1:%UI_PORT% in your browser.
pause
