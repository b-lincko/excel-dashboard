#!/usr/bin/env bash
# Print recovery commands and optionally check that data files exist.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo "  Linkco MR — recovery helper"
echo "============================================================"
echo "  Project: $ROOT"
echo
echo "  Live database : $ROOT/data/woms.db"
echo "  Excel replica : $ROOT/file.xlsx"
echo "  Snapshots     : $ROOT/backups/"
echo "  Mapping       : $ROOT/data/app_config.json"
echo

if [ -f data/woms.db ]; then
  echo "  data/woms.db exists ($(du -h data/woms.db | awk '{print $1}'))"
else
  echo "  WARNING: data/woms.db is missing"
fi
if [ -f file.xlsx ]; then
  echo "  file.xlsx exists ($(du -h file.xlsx | awk '{print $1}'))"
else
  echo "  WARNING: file.xlsx is missing"
fi
echo
echo "  Latest snapshots:"
# shellcheck disable=SC2012
ls -lt backups/*/*.{xlsx,db} 2>/dev/null | head -8 || echo "  (none yet — use Settings → Backup now)"
echo
echo "  Docker:  ./docker-run.sh"
echo "  Local:   ./run.sh --local"
echo "  Admin:   python3 scripts/reset_admin.py"
echo "  Docs:    docs/RECOVERY.md"
echo "============================================================"
