@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "REQ=%ROOT%backend\requirements.txt"
set "XLSX=%ROOT%file.xlsx"

echo ============================================================
echo   Linkco MR Dashboard — install ^& run
echo ============================================================
echo   Folder: %CD%
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
call %PYTHON% --version
if not exist "%VENV_PY%" (
  echo       creating .venv ...
  call %PYTHON% -m venv "%ROOT%.venv"
  if errorlevel 1 (
    echo ERROR: failed to create virtual environment.
    pause
    exit /b 1
  )
)

echo       upgrading pip ...
"%VENV_PY%" -m pip install --upgrade pip wheel
echo       installing backend packages ...
"%VENV_PY%" -m pip install --prefer-binary --only-binary=:all: -r "%REQ%"
if errorlevel 1 (
  echo Binary wheels not available. Retrying ...
  "%VENV_PY%" -m pip install --prefer-binary -r "%REQ%"
)
if errorlevel 1 (
  echo ERROR: pip install failed. Delete the .venv folder and try again.
  pause
  exit /b 1
)

echo.
echo [2/4] Frontend packages
if not exist "%ROOT%frontend\node_modules\" (
  pushd "%ROOT%frontend"
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
if not exist "%XLSX%" (
  echo ERROR: file.xlsx not found in:
  echo   %CD%
  echo Copy the Linkco MR workbook here and name it file.xlsx
  pause
  exit /b 1
)
echo       using %XLSX%

echo.
echo [4/4] Starting API then UI
echo       API window must stay open — that is what reads Excel.
echo       UI   http://127.0.0.1:5173
echo       API  http://127.0.0.1:8000
echo.
echo       Sign in:  admin / admin123
echo ============================================================
echo.

start "Linkco MR API" "%ROOT%scripts\start-api.bat"

echo Waiting for API on port 8000 ...
set /a _tries=0
:waitapi
timeout /t 2 /nobreak >nul
"%VENV_PY%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" >nul 2>&1
if not errorlevel 1 goto apiok
set /a _tries+=1
if !_tries! lss 20 goto waitapi
echo.
echo WARNING: API did not respond yet. Check the "Linkco MR API" window for errors.
echo You can still open the UI; it will connect once the API is up.
:apiok

start "Linkco MR UI" "%ROOT%scripts\start-ui.bat"

echo.
echo Two windows opened:  Linkco MR API  and  Linkco MR UI
echo Open http://127.0.0.1:5173
echo Do NOT close the API window or the dashboard cannot load Excel.
pause
endlocal
