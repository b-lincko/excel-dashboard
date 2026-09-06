from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import database
from .backup import start_scheduler, stop_scheduler
from .config import DATA_DIR
from .excel.service import excel_service
from .routers import audit, auth, catalog, dashboard, ops, reports, settings, sync, users, work_orders


def _boot() -> None:
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _boot()
    try:
        start_scheduler()
    except Exception as exc:
        print(f"[WOMS] autobackup scheduler skipped: {exc}")
    try:
        yield
    finally:
        try:
            stop_scheduler()
        except Exception:
            pass


app = FastAPI(
    title="Linkco MR — Work Order Management",
    description="Operations dashboard with Excel as the source of truth.",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=400)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    return response

app.include_router(auth.router)
app.include_router(work_orders.router)
app.include_router(catalog.router)
app.include_router(dashboard.router)
app.include_router(ops.router)
app.include_router(reports.router)
app.include_router(audit.router)
app.include_router(users.router)
app.include_router(settings.router)
app.include_router(sync.router)


@app.get("/api/health")
def health():
    live = excel_service.ping()
    return {
        "ok": True,
        "excel": live.get("synchronized"),
        "records": live.get("record_count"),
        "error": live.get("error"),
        "stale": live.get("stale"),
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
