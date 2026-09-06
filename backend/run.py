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

if __name__ == "__main__":
    excel = ROOT / "file.xlsx"
    print(f"Project: {ROOT}")
    print(f"Excel:   {excel}  exists={excel.exists()}")
    print("API:     http://127.0.0.1:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
