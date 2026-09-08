#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
fi
if [ ! -f "$ROOT/data/work_orders.xlsx" ]; then
  "$ROOT/.venv/bin/python" "$ROOT/scripts/generate_excel.py"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  (cd "$ROOT/frontend" && npm install)
fi

"$ROOT/.venv/bin/python" "$ROOT/backend/run.py" &
API_PID=$!
(cd "$ROOT/frontend" && npm run dev) &
UI_PID=$!
trap 'kill $API_PID $UI_PID 2>/dev/null || true' INT TERM
wait
