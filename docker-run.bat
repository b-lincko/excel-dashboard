@echo off
REM Install Docker if missing, then build and run Linkco MR in Docker.
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"
if "%WOMS_PORT%"=="" set "WOMS_PORT=8000"

echo ============================================================
echo   Linkco MR Dashboard - Docker
echo ============================================================
echo   Folder: %ROOT%
echo.

where docker >nul 2>&1
if errorlevel 1 goto INSTALL_DOCKER
echo [1/4] Docker found
docker --version
goto WAIT_DOCKER

:INSTALL_DOCKER
echo [1/4] Docker not found - installing Docker Desktop...
where winget >nul 2>&1
if errorlevel 1 goto NO_WINGET
winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo ERROR: winget could not install Docker Desktop.
  echo Install from https://docs.docker.com/desktop/setup/install/windows-install/
  pause
  exit /b 1
)
echo Start Docker Desktop if it did not open, then this script will wait.
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
)
goto WAIT_DOCKER

:NO_WINGET
echo ERROR: Docker is not installed and winget was not found.
echo Install Docker Desktop from:
echo   https://docs.docker.com/desktop/setup/install/windows-install/
pause
exit /b 1

:WAIT_DOCKER
echo [2/4] Waiting for Docker engine...
set /a TRIES=0
:WAIT_LOOP
docker info >nul 2>&1
if not errorlevel 1 goto DOCKER_READY
set /a TRIES+=1
if %TRIES% GEQ 60 (
  echo ERROR: Docker is installed but the engine is not running.
  echo Open Docker Desktop, wait until it says running, then re-run docker-run.bat
  pause
  exit /b 1
)
timeout /t 2 /nobreak >nul
goto WAIT_LOOP

:DOCKER_READY
echo       Docker is ready.

if not exist "%ROOT%\file.xlsx" (
  echo ERROR: file.xlsx not found in:
  echo   %ROOT%
  echo Copy the Linkco MR workbook here and name it file.xlsx
  pause
  exit /b 1
)
echo [3/4] Excel workbook
echo       using %ROOT%\file.xlsx
if not exist "%ROOT%\data" mkdir "%ROOT%\data"
if not exist "%ROOT%\backups" mkdir "%ROOT%\backups"

echo.
echo [4/4] Building and starting container
echo       App  http://127.0.0.1:%WOMS_PORT%
echo.
echo       Sign in:  admin / admin123
echo                 manager / manager123
echo                 user / user123
echo.
echo Press Ctrl+C to stop.
echo ============================================================
echo.

docker compose version >nul 2>&1
if errorlevel 1 goto COMPOSE_LEGACY
docker compose -f "%ROOT%\docker-compose.yml" up --build
if errorlevel 1 (
  echo.
  echo Docker compose failed.
  pause
  exit /b 1
)
goto END

:COMPOSE_LEGACY
where docker-compose >nul 2>&1
if errorlevel 1 (
  echo ERROR: Docker Compose is not available.
  echo Update Docker Desktop and re-run.
  pause
  exit /b 1
)
docker-compose -f "%ROOT%\docker-compose.yml" up --build
if errorlevel 1 (
  echo.
  echo docker-compose failed.
  pause
  exit /b 1
)

:END
endlocal
