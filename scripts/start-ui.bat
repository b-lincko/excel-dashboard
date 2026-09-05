@echo off
setlocal EnableExtensions
cd /d "%~dp0..\frontend"
echo ============================================================
echo  Linkco MR UI
echo  Folder: %CD%
echo ============================================================
if not exist "node_modules\" (
  echo Installing frontend packages...
  call npm install
)
echo Starting http://127.0.0.1:5173 ...
echo Keep this window OPEN while using the dashboard.
echo.
call npm run dev -- --host 0.0.0.0 --port 5173
echo.
echo UI stopped.
pause
