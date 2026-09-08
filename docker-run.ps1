# Install Docker if missing, then build and run Linkco MR in Docker.
# Uses PowerShell so folder names like "excel-dashboard (2)" do not break cmd.exe.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

$Port = if ($env:WOMS_PORT) { $env:WOMS_PORT } else { "8000" }
$env:WOMS_PORT = $Port
$env:COMPOSE_PROJECT_NAME = "linkco-mr"

Write-Host "============================================================"
Write-Host "  Linkco MR Dashboard - Docker"
Write-Host "============================================================"
Write-Host "  Folder: $Root"
Write-Host ""

function Test-DockerEngine {
    try {
        docker info 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[1/4] Docker not found - installing Docker Desktop..."
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: Docker is not installed and winget was not found."
        Write-Host "Install Docker Desktop from:"
        Write-Host "  https://docs.docker.com/desktop/setup/install/windows-install/"
        Read-Host "Press Enter to close"
        exit 1
    }
    winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE) {
        Write-Host "ERROR: winget could not install Docker Desktop."
        Write-Host "Install from https://docs.docker.com/desktop/setup/install/windows-install/"
        Read-Host "Press Enter to close"
        exit 1
    }
    $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path -LiteralPath $desktop) {
        Start-Process -FilePath $desktop
    }
    Write-Host "      Start Docker Desktop if it did not open, then this script will wait."
} else {
    Write-Host "[1/4] Docker found"
    docker --version
}

Write-Host "[2/4] Waiting for Docker engine..."
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    if (Test-DockerEngine) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Write-Host "ERROR: Docker is installed but the engine is not running."
    Write-Host "Open Docker Desktop, wait until it says running, then re-run docker-run.bat"
    Read-Host "Press Enter to close"
    exit 1
}
Write-Host "      Docker is ready."

$xlsx = Join-Path $Root "file.xlsx"
if (-not (Test-Path -LiteralPath $xlsx)) {
    Write-Host "ERROR: file.xlsx not found in:"
    Write-Host "  $Root"
    Write-Host "Copy the Linkco MR workbook here and name it file.xlsx"
    Read-Host "Press Enter to close"
    exit 1
}
Write-Host "[3/4] Excel workbook"
Write-Host "      using $xlsx"
New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "backups") | Out-Null

$composeFile = Join-Path $Root "docker-compose.yml"
$usePlugin = $false
try {
    docker compose version 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $usePlugin = $true }
} catch {}
if (-not $usePlugin -and -not (Get-Command docker-compose -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Docker Compose is not available."
    Write-Host "Update Docker Desktop and re-run."
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "[4/4] Building and starting container"
Write-Host "      App  http://127.0.0.1:$Port"
Write-Host ""
Write-Host "Press Ctrl+C to stop."
Write-Host "============================================================"
Write-Host ""

if ($usePlugin) {
    docker compose -f $composeFile up --build
} else {
    docker-compose -f $composeFile up --build
}
