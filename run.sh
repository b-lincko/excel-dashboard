#!/usr/bin/env bash
# Look for dependencies, install what is missing, prefer Docker, else local.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"
USE_LOCAL=0
for arg in "$@"; do
  case "$arg" in
    --local|local) USE_LOCAL=1 ;;
  esac
done

echo "============================================================"
echo "  Linkco MR Dashboard — install & run"
echo "============================================================"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

run_docker() {
  if [ ! -x "$ROOT/docker-run.sh" ]; then
    chmod +x "$ROOT/docker-run.sh" 2>/dev/null || true
  fi
  if [ ! -f "$ROOT/docker-compose.yml" ] || [ ! -f "$ROOT/Dockerfile" ]; then
    return 1
  fi
  echo "Using Docker (pass --local to force Python + Node on the host)."
  echo
  exec "$ROOT/docker-run.sh"
}

if [ "$USE_LOCAL" -eq 0 ]; then
  if have_cmd docker || have_cmd apt-get || have_cmd dnf || have_cmd brew || have_cmd curl; then
    run_docker
  fi
fi

echo "Running locally (Docker not used)."
echo

need() {
  if ! have_cmd "$1"; then
    echo "ERROR: '$1' is not installed or not on PATH." >&2
    exit 1
  fi
}

install_python() {
  if have_cmd python3 || have_cmd python; then
    return 0
  fi
  echo "Python not found — installing…"
  if have_cmd apt-get; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip
  elif have_cmd dnf; then
    sudo dnf install -y python3 python3-pip
  elif have_cmd brew; then
    brew install python
  else
    echo "ERROR: Python 3.11+ is required. Install it and re-run." >&2
    exit 1
  fi
}

install_node() {
  if have_cmd npm; then
    return 0
  fi
  echo "Node.js / npm not found — installing…"
  if have_cmd apt-get; then
    sudo apt-get update -y
    sudo apt-get install -y nodejs npm
  elif have_cmd dnf; then
    sudo dnf install -y nodejs npm
  elif have_cmd brew; then
    brew install node
  else
    echo "ERROR: Node.js 18+ / npm is required. Install LTS from https://nodejs.org/" >&2
    exit 1
  fi
}

install_python
install_node

if have_cmd python3; then
  PYTHON=python3
else
  PYTHON=python
fi
need npm

echo
echo "[1/4] Python virtual environment"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "      creating .venv …"
  "$PYTHON" -m venv "$ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
python -m pip install --upgrade pip wheel >/dev/null
echo "      installing backend packages …"
pip install --prefer-binary -r "$ROOT/backend/requirements.txt"

echo
echo "[2/4] Frontend packages"
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  (cd "$ROOT/frontend" && npm install)
else
  echo "      node_modules already present"
fi

echo
echo "[3/4] Excel workbook"
if [ ! -f "$ROOT/file.xlsx" ]; then
  echo "ERROR: file.xlsx not found in $ROOT" >&2
  echo "Place the Linkco MR workbook here (source of truth)." >&2
  exit 1
fi
echo "      using $ROOT/file.xlsx"

echo
echo "[4/4] Starting servers"
echo "      API  → http://127.0.0.1:${API_PORT}"
echo "      UI   → http://127.0.0.1:${UI_PORT}"
echo
echo "      Sign in:  admin / admin123"
echo "                manager / manager123"
echo "                user / user123"
echo
echo "Press Ctrl+C to stop both processes."
echo "============================================================"

cleanup() {
  echo
  echo "Stopping…"
  if [ -n "${API_PID:-}" ]; then kill "$API_PID" 2>/dev/null || true; fi
  if [ -n "${UI_PID:-}" ]; then kill "$UI_PID" 2>/dev/null || true; fi
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

cd "$ROOT/backend"
"$ROOT/.venv/bin/python" run.py &
API_PID=$!

cd "$ROOT/frontend"
npm run dev -- --host 0.0.0.0 --port "$UI_PORT" &
UI_PID=$!

wait
