from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
os.chdir(BACKEND)
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import uvicorn

# Production topology: the backend binds loopback only and nginx is the public
# entry (deploy/nginx.conf). Override with WOMS_HOST / WOMS_PORT for dev.
HOST = (os.environ.get("WOMS_HOST", "") or "127.0.0.1").strip()
PORT = int(os.environ.get("WOMS_PORT", "") or 8001)

if __name__ == "__main__":
    excel = ROOT / "file.xlsx"
    print(f"Project: {ROOT}")
    print(f"Excel:   {excel}  exists={excel.exists()}")
    print(f"API:     http://{HOST}:{PORT}  (public entry: nginx :8000 -> here)")
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",  # trust X-Forwarded-* from our nginx only
    )
