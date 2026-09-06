#!/usr/bin/env bash
# Install Docker if missing, then build and run Linkco MR in Docker.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${WOMS_PORT:-8000}"

echo "============================================================"
echo "  Linkco MR Dashboard — Docker"
echo "============================================================"
echo "  Folder: $ROOT"
echo

have_cmd() { command -v "$1" >/dev/null 2>&1; }

sudo_if_needed() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif have_cmd sudo; then
    sudo "$@"
  else
    echo "ERROR: need root or sudo to install Docker." >&2
    return 1
  fi
}

docker_ok() {
  docker info >/dev/null 2>&1
}

install_docker() {
  echo "[1/4] Docker not found — installing…"
  if have_cmd apt-get; then
    sudo_if_needed apt-get update -y
    sudo_if_needed apt-get install -y docker.io docker-compose-plugin \
      || sudo_if_needed apt-get install -y docker.io docker-compose
    sudo_if_needed systemctl enable --now docker 2>/dev/null || true
  elif have_cmd dnf; then
    sudo_if_needed dnf install -y docker docker-compose
    sudo_if_needed systemctl enable --now docker 2>/dev/null || true
  elif have_cmd yum; then
    sudo_if_needed yum install -y docker docker-compose
    sudo_if_needed systemctl enable --now docker 2>/dev/null || true
  elif have_cmd pacman; then
    sudo_if_needed pacman -Sy --noconfirm docker docker-compose
    sudo_if_needed systemctl enable --now docker 2>/dev/null || true
  elif have_cmd brew; then
    brew install --cask docker || brew install docker docker-compose
    echo "      If Docker Desktop was installed, open it once, then re-run this script."
  elif have_cmd curl; then
    curl -fsSL https://get.docker.com | sudo_if_needed sh
    sudo_if_needed systemctl enable --now docker 2>/dev/null || true
  else
    echo "ERROR: could not install Docker automatically." >&2
    echo "Install from https://docs.docker.com/get-docker/ and re-run." >&2
    exit 1
  fi
}

wait_for_docker() {
  echo "[2/4] Waiting for Docker engine…"
  local i
  for i in $(seq 1 45); do
    if docker_ok; then
      echo "      Docker is ready."
      return 0
    fi
    if have_cmd docker && [ "$(id -u)" -ne 0 ]; then
      sudo docker info >/dev/null 2>&1 || true
    fi
    sleep 2
  done
  if docker_ok; then
    return 0
  fi
  echo "ERROR: Docker is installed but the engine is not running." >&2
  echo "Start Docker Desktop / 'sudo systemctl start docker', then re-run." >&2
  exit 1
}

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif have_cmd docker-compose; then
    docker-compose "$@"
  else
    echo "ERROR: Docker Compose is not available." >&2
    echo "Install the compose plugin and re-run." >&2
    exit 1
  fi
}

if ! have_cmd docker; then
  install_docker
else
  echo "[1/4] Docker found: $(docker --version 2>/dev/null || echo docker)"
fi

if ! docker_ok; then
  if have_cmd systemctl; then
    sudo_if_needed systemctl start docker 2>/dev/null || true
  fi
fi
wait_for_docker

if ! docker compose version >/dev/null 2>&1 && ! have_cmd docker-compose; then
  echo "      Compose missing — trying to install…"
  if have_cmd apt-get; then
    sudo_if_needed apt-get install -y docker-compose-plugin docker-compose || true
  elif have_cmd dnf; then
    sudo_if_needed dnf install -y docker-compose || true
  elif have_cmd brew; then
    brew install docker-compose || true
  fi
fi

echo
echo "[3/4] Excel workbook"
if [ ! -f "$ROOT/file.xlsx" ]; then
  echo "ERROR: file.xlsx not found in $ROOT" >&2
  echo "Place the Linkco MR workbook here (source of truth)." >&2
  exit 1
fi
echo "      using $ROOT/file.xlsx"
mkdir -p "$ROOT/data" "$ROOT/backups"

echo
echo "[4/4] Building and starting container"
echo "      App → http://127.0.0.1:${PORT}"
echo
echo "      Sign in:  admin / admin123"
echo "                manager / manager123"
echo "                user / user123"
echo
echo "Press Ctrl+C to stop."
echo "============================================================"

export WOMS_PORT="$PORT"
compose -f "$ROOT/docker-compose.yml" up --build
