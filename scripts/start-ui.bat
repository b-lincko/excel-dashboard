@echo off
cd /d "%~dp0..\frontend"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Set-Location -LiteralPath (Get-Location).Path; if (-not (Test-Path -LiteralPath 'node_modules')) { npm install }; Write-Host 'Starting http://127.0.0.1:5173 — keep this window OPEN.'; npm run dev -- --host 0.0.0.0 --port 5173; pause"
