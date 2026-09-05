#!/usr/bin/env bash
# Install dependencies and start the Linkco MR dashboard (Linux / macOS).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"

echo "============================================================"
echo "  Linkco MR Dashboard — install & run"
echo "============================================================"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: '$1' is not installed or not on PATH." >&2
    exit 1
  fi
}

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "ERROR: Python 3.11+ is required." >&2
  exit 1
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
