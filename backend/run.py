from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
os.chdir(BACKEND)
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from .env (repo root or backend/) into os.environ.

    Real environment variables always win. No quotes stripping beyond simple
    pairs, no export prefix - keep it boring. Values are never logged.
    """
    for candidate in (ROOT / ".env", BACKEND / ".env"):
        if not candidate.is_file():
            continue
        try:
            for line in candidate.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text or text.startswith("#") or "=" not in text:
                    continue
                key, _, value = text.partition("=")
                key = key.strip().replace("export ", "")
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            pass
        break


_load_dotenv()

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
