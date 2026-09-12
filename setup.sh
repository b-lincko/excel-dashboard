#!/usr/bin/env bash
# ============================================================================
# Linkco MR - first-run setup, then the main server.
#
#   ./setup.sh                 # .env wizard on :8081 if .env missing, then main server
#   ./setup.sh --setup         # force the wizard (reconfigure), then main server
#   ./setup.sh --wizard-only   # wizard and stop (do not start the server)
#
# Creates backend/.venv + installs requirements on first run, then hands over
# to backend/launch.py, which starts the web setup wizard (port 8081) when
# needed and the main server (port 8000 via nginx) from the .env it writes.
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "============================================================"
echo "  Linkco MR - setup / launch"
echo "============================================================"

PYEXE=""
if [ -x "$ROOT/backend/.venv/bin/python" ]; then
  PYEXE="$ROOT/backend/.venv/bin/python"
  echo "Using existing virtual environment: backend/.venv"
elif [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then
  # venv was created from Windows; reuse it from WSL / git-bash
  PYEXE="$ROOT/backend/.venv/Scripts/python.exe"
  echo "Using existing Windows virtual environment: backend/.venv"
else
  PY=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
      PY="$candidate"
      break
    fi
  done
  if [ -z "$PY" ]; then
    echo "ERROR: Python 3 not found."
    echo "  Debian/Ubuntu:  sudo apt install python3 python3-venv python3-pip"
    exit 1
  fi
  echo "Creating virtual environment + installing requirements (first run only)..."
  if ! "$PY" -m venv "$ROOT/backend/.venv" 2>/dev/null; then
    echo "ERROR: could not create the virtual environment."
    echo "  Debian/Ubuntu:  sudo apt install python3-venv   (then re-run ./setup.sh)"
    exit 1
  fi
  "$ROOT/backend/.venv/bin/python" -m pip install --upgrade pip
  "$ROOT/backend/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt" ||
    { echo "ERROR: requirements install failed - check the output above."; exit 1; }
  PYEXE="$ROOT/backend/.venv/bin/python"
fi

echo "Wizard (when needed) on http://0.0.0.0:8081 - main server after Save+Finish."
echo "Arguments: ${*:-none}   (--setup forces the wizard, --wizard-only stops after it)"
echo

exec "$PYEXE" "$ROOT/backend/launch.py" "$@"
