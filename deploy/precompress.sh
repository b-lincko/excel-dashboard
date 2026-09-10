#!/usr/bin/env bash
# Pre-gzip built frontend assets for nginx gzip_static: browsers that accept
# gzip download the .gz directly — no runtime compression cost. Run after
# every `npm run build` (start_production.sh does this automatically).
set -euo pipefail
DIST="$(cd "$(dirname "${BASH_SOURCE[0]}")/../frontend/dist" && pwd)"
[ -f "$DIST/index.html" ] || { echo "frontend/dist/index.html missing — run `npm run build` in frontend/ first" >&2; exit 1; }
count=0
while IFS= read -r -d '' f; do
  gzip -9 -c "$f" > "$f.gz" && touch -r "$f" "$f.gz"
  count=$((count + 1))
done < <(find "$DIST" -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.svg' \) ! -name '*.gz' -print0)
echo "precompressed $count assets in $DIST"
