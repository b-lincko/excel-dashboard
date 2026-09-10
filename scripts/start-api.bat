@echo off
REM Use PowerShell so folder names like "download (3)" do not break cmd.exe.
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$Root = (Get-Location).Path; $py = Join-Path $Root '.venv\Scripts\python.exe'; $xlsx = Join-Path $Root 'file.xlsx'; if (-not (Test-Path -LiteralPath $xlsx)) { Write-Host \"ERROR: file.xlsx not found in $Root\"; pause; exit 1 }; if (-not (Test-Path -LiteralPath $py)) { Write-Host 'ERROR: .venv missing. Run run.bat first.'; pause; exit 1 }; Write-Host \"Excel: $xlsx\"; Write-Host 'API on http://127.0.0.1:8001 (loopback — the dev UI proxies to it) — keep this window OPEN.'; & $py -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --app-dir backend; pause"
