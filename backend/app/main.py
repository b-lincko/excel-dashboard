from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import database
from .backup import start_scheduler, stop_scheduler
from .escalation import start_escalator, stop_escalator
from .config import DATA_DIR
from .excel.service import excel_service
from .routers import admin_backups, audit, auth, catalog, collab, dashboard, files, netdrive, ops, po_approvals, reports, settings, sync, users, work_orders


def _boot() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    database.init_db()
    try:
        path = excel_service.excel_path()
        print(f"[WOMS] Excel path: {path} exists={path.exists()}")
        n = database.wo_cache_count()
        if n == 0 and excel_service.available():
            result = excel_service.seed_from_excel(username="boot", replace_lines=True)
            if result.get("ok"):
                print(f"[WOMS] Seeded {result.get('count')} material requests from Excel into the database")
            else:
                print(f"[WOMS] Database seed skipped: {result.get('error')}")
        else:
            recs = excel_service.load()
            print(f"[WOMS] Database holds {len(recs)} material requests")
    except Exception as exc:
        print(f"[WOMS] Database/Excel boot skipped: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _boot()
    try:
        start_scheduler()
    except Exception as exc:
        print(f"[WOMS] autobackup scheduler skipped: {exc}")
    try:
        start_escalator()
    except Exception as exc:
        print(f"[WOMS] escalation scheduler skipped: {exc}")
    try:
        yield
    finally:
        try:
            stop_escalator()
        except Exception:
            pass
        try:
            stop_scheduler()
        except Exception:
            pass


app = FastAPI(
    title="Linkco MR — Work Order Management",
    description="Operations dashboard. The database is the work-order history; Excel is a backup replica.",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS: same-origin only by default — nginx serves the app and proxies /api
# from the same origin the browser uses, so no cross-origin is needed. Set
# WOMS_CORS_ORIGINS to a comma-separated list (or "*") only when the UI is
# hosted on a different origin than the API.
_cors_env = os.environ.get("WOMS_CORS_ORIGINS", "").strip()
if _cors_env == "*":
    _cors_origins: list[str] = ["*"]
elif _cors_env:
    _cors_origins = [item.strip() for item in _cors_env.split(",") if item.strip()]
else:
    _cors_origins = []

app.add_middleware(GZipMiddleware, minimum_size=400)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    return response

app.include_router(auth.router)
app.include_router(admin_backups.router)
app.include_router(netdrive.router)
app.include_router(work_orders.router)
app.include_router(po_approvals.router)
app.include_router(catalog.router)
app.include_router(dashboard.router)
app.include_router(ops.router)
app.include_router(reports.router)
app.include_router(audit.router)
app.include_router(users.router)
app.include_router(settings.router)
app.include_router(sync.router)
app.include_router(collab.router)
app.include_router(files.router)


@app.get("/api/health")
def health():
    db_ok = True
    cache = 0
    db_error = None
    try:
        cache = database.wo_cache_count()
    except Exception as exc:
        db_ok = False
        db_error = str(exc)
    live = {}
    try:
        live = excel_service.ping() or {}
    except Exception as exc:
        live = {"error": str(exc)}
    return {
        "ok": db_ok,
        "database": db_ok,
        "excel": live.get("synchronized"),
        "records": live.get("record_count"),
        "cache": cache,
        "error": db_error or live.get("error"),
        "stale": live.get("stale"),
    }


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    if request.url.path.startswith("/api/"):
        debug = os.environ.get("WOMS_DEBUG", "").strip().lower() in {"1", "true", "yes"}
        detail = str(exc) if debug else "Internal server error"
        return JSONResponse(status_code=500, content={"detail": detail})
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
