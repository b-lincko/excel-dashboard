#!/usr/bin/env bash
# Linkco MR container entrypoint: start uvicorn on loopback, then hand the
# container's main process to nginx (public :8000). Mirrors the host
# production topology (deploy/start_production.sh) inside one container.
set -euo pipefail

mkdir -p /app/data/logs

WOMS_HOST="${WOMS_HOST:-127.0.0.1}"
WOMS_PORT="${WOMS_PORT:-8001}"
export WOMS_HOST WOMS_PORT

echo "[linkco-mr] starting API on ${WOMS_HOST}:${WOMS_PORT} (loopback, behind nginx :8000)"
cd /app/backend
python run.py >>/app/data/logs/backend.log 2>&1 &

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${WOMS_PORT}/api/health" >/dev/null 2>&1; then
    echo "[linkco-mr] API is healthy"
    break
  fi
  sleep 1
done

echo "[linkco-mr] nginx taking over as the main process (public :8000)"
exec /usr/sbin/nginx -c /app/deploy/nginx-docker.conf -g 'daemon off;'
