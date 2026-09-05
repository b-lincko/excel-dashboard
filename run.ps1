# Linkco MR Dashboard — install dependencies and start API + UI
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

function Write-Banner {
    Write-Host "============================================================"
    Write-Host "  Linkco MR Dashboard — install & run"
    Write-Host "============================================================"
    Write-Host "  Folder: $Root"
    Write-Host ""
}

Write-Banner

$python = $null
foreach ($cmd in @("python", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) { $python = $found.Source; break }
}
if (-not $python) {
    Write-Host "ERROR: Python 3.11+ was not found on PATH." -ForegroundColor Red
    Write-Host "Install from https://www.python.org/downloads/ and tick Add Python to PATH."
    Read-Host "Press Enter to close"
    exit 1
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Node.js / npm was not found on PATH." -ForegroundColor Red
    Write-Host "Install LTS from https://nodejs.org/"
    Read-Host "Press Enter to close"
    exit 1
}

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
$xlsx = Join-Path $Root "file.xlsx"
$req = Join-Path $Root "backend\requirements.txt"

Write-Host "[1/4] Python virtual environment"
& $python --version
if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "      creating .venv ..."
    & $python -m venv (Join-Path $Root ".venv")
    if ($LASTEXITCODE) { Read-Host "venv failed. Press Enter"; exit 1 }
}

Write-Host "      upgrading pip ..."
& $venvPy -m pip install --upgrade pip wheel
Write-Host "      installing backend packages ..."
& $venvPy -m pip install --prefer-binary --only-binary=:all: -r $req
if ($LASTEXITCODE) {
    Write-Host "      retrying without --only-binary ..."
    & $venvPy -m pip install --prefer-binary -r $req
}
if ($LASTEXITCODE) {
    Write-Host "ERROR: pip install failed. Delete the .venv folder and try again." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "[2/4] Frontend packages"
$nm = Join-Path $Root "frontend\node_modules"
if (-not (Test-Path -LiteralPath $nm)) {
    Push-Location (Join-Path $Root "frontend")
    npm install
    if ($LASTEXITCODE) { Pop-Location; Read-Host "npm install failed. Press Enter"; exit 1 }
    Pop-Location
} else {
    Write-Host "      node_modules already present"
}

Write-Host ""
Write-Host "[3/4] Excel workbook"
if (-not (Test-Path -LiteralPath $xlsx)) {
    Write-Host "ERROR: file.xlsx not found in:" -ForegroundColor Red
    Write-Host "  $Root"
    Write-Host "Copy the Linkco MR workbook here and name it file.xlsx"
    Read-Host "Press Enter to close"
    exit 1
}
Write-Host "      using $xlsx"

Write-Host ""
Write-Host "[4/4] Starting API then UI"
Write-Host "      API window must stay open — that is what reads Excel."
Write-Host "      UI   http://127.0.0.1:5173"
Write-Host "      API  http://127.0.0.1:8000"
Write-Host ""
Write-Host "      Sign in:  admin / admin123"
Write-Host "============================================================"
Write-Host ""

$apiCmd = @"
title Linkco MR API
cd /d "$Root"
echo Excel: $xlsx
echo Starting http://127.0.0.1:8000
echo Keep this window OPEN.
echo.
"$venvPy" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
echo.
echo API stopped.
pause
"@
Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $apiCmd) -WorkingDirectory $Root

Write-Host "Waiting for API on port 8000 ..."
$up = $false
for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep -Seconds 2
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2
        $up = $true
        break
    } catch { }
}
if (-not $up) {
    Write-Host "WARNING: API did not respond yet. Check the Linkco MR API window." -ForegroundColor Yellow
}

$uiCmd = @"
title Linkco MR UI
cd /d "$Root\frontend"
echo Starting http://127.0.0.1:5173
echo Keep this window OPEN.
echo.
npm run dev -- --host 0.0.0.0 --port 5173
echo.
echo UI stopped.
pause
"@
Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $uiCmd) -WorkingDirectory (Join-Path $Root "frontend")

Write-Host ""
Write-Host "Two windows opened:  Linkco MR API  and  Linkco MR UI"
Write-Host "Open http://127.0.0.1:5173"
Write-Host "Do NOT close the API window."
Read-Host "Press Enter to close this installer window"
