from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import database
from .config import DATA_DIR
from .excel.service import excel_service
from .routers import audit, auth, dashboard, ops, reports, settings, sync, users, work_orders

app = FastAPI(
    title="Work Order Management System",
    description="Professional work-order dashboard with Excel as the source of truth.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(work_orders.router)
app.include_router(dashboard.router)
app.include_router(ops.router)
app.include_router(reports.router)
app.include_router(audit.router)
app.include_router(users.router)
app.include_router(settings.router)
app.include_router(sync.router)


@app.on_event("startup")
def startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    database.init_db()
    try:
        path = excel_service.excel_path()
        print(f"[WOMS] Excel path: {path} exists={path.exists()}")
        if excel_service.available():
            n = len(excel_service.load(force=True))
            print(f"[WOMS] Loaded {n} material requests")
        else:
            print("[WOMS] Excel file is currently unavailable.")
    except Exception as exc:
        print(f"[WOMS] Excel load skipped: {exc}")


@app.get("/api/health")
def health():
    status = excel_service.status()
    return {
        "ok": True,
        "excel": status.get("synchronized"),
        "records": status.get("record_count"),
        "error": status.get("error"),
    }


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    raise exc


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        index = FRONTEND_DIST / "index.html"
        candidate = FRONTEND_DIST / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
