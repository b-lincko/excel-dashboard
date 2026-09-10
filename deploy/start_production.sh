#!/usr/bin/env bash
# Linkco MR production launcher.
#
#   deploy/start_production.sh        start backend (loopback) + nginx (public)
#   deploy/start_production.sh stop   stop both
#
# Topology:  browser -> nginx :8000 (frontend dist + /api proxy) -> uvicorn
#            127.0.0.1:8001 (never exposed). Requires `npm run build` in
#            frontend/ to have produced frontend/dist.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="$ROOT/data/logs"
mkdir -p "$LOGDIR"

NGINX="$ROOT/deploy/nginx/sbin/nginx"          # source build installed in-repo
[ -x "$NGINX" ] || NGINX="$(command -v nginx || true)"  # or a distro package
[ -n "$NGINX" ] && [ -x "$NGINX" ] || { echo "nginx binary not found" >&2; exit 1; }

if [ "${1:-}" = "stop" ]; then
  if [ -f "$LOGDIR/nginx.pid" ]; then kill "$(cat "$LOGDIR/nginx.pid")" 2>/dev/null || true; fi
  pkill -f "app.main:app" 2>/dev/null || true
  echo "Linkco MR stopped."
  exit 0
fi

[ -f "$ROOT/frontend/dist/index.html" ] || { echo "frontend/dist missing — run: (cd frontend && npm run build)" >&2; exit 1; }

bash "$ROOT/deploy/precompress.sh"

# Backend on loopback only
pkill -f "app.main:app" 2>/dev/null || true
sleep 0.5
cd "$ROOT/backend"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
WOMS_HOST=127.0.0.1 WOMS_PORT=8001 nohup "$PY" run.py >>"$LOGDIR/backend.log" 2>&1 &
echo $! > "$LOGDIR/backend.pid"
for _ in $(seq 1 30); do
  curl -sf http://127.0.0.1:8001/api/health >/dev/null && break
  sleep 1
done

# nginx (reload if already running, start otherwise)
if [ -f "$LOGDIR/nginx.pid" ] && kill -0 "$(cat "$LOGDIR/nginx.pid")" 2>/dev/null; then
  "$NGINX" -c "$ROOT/deploy/nginx.conf" -s reload
else
  "$NGINX" -c "$ROOT/deploy/nginx.conf"
fi
echo "Linkco MR is live: nginx :8000 -> backend 127.0.0.1:8001"
