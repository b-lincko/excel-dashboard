from __future__ import annotations

import io
import zipfile
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import database
from ..backup import ensure_folder, list_folders, require_app_folder, run_due_backup, schedule_status
from ..config import AppConfig, load_config, save_config
from ..excel.service import ExcelLocked, ExcelUnavailable, excel_service
from ..jobs import create_job, get_job, public_job, run_job
from ..security import get_current_user, require_permission
from ..stats import invalidate_dash_cache

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


def _public_settings(cfg: AppConfig) -> dict[str, Any]:
    data = cfg.model_dump()
    data.pop("jwt_secret", None)
    data["jwt_secret_set"] = bool(cfg.jwt_secret)
    return data


@router.get("")
def get_settings(user=Depends(require_permission("settings"))):
    cfg = load_config()
    return {"settings": _public_settings(cfg), "sync": excel_service.status(), "backup": schedule_status(cfg)}


@router.put("")
def update_settings(body: SettingsUpdate, user=Depends(require_permission("settings"))):
    cfg = load_config()
    current = cfg.model_dump()
    current.update(body.values)
    try:
        new_cfg = AppConfig.model_validate(current)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    folder = str(new_cfg.backup_dir or "").strip()
    if folder:
        try:
            path = ensure_folder(folder)
            new_cfg.backup_dir = str(path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    save_config(new_cfg)
    excel_service.invalidate()
    return {"settings": _public_settings(new_cfg), "saved": True, "backup": schedule_status(new_cfg)}


@router.get("/mapping-scan")
def mapping_scan(user=Depends(require_permission("settings"))):
    try:
        return excel_service.mapping_scan()
    except ExcelUnavailable as cop:
        raise HTTPException(status_code=503, detail=str(cop))
    except ExcelLocked as cop:
        raise HTTPException(status_code=423, detail=str(cop))
    except Exception as cop:
        raise HTTPException(status_code=500, detail=str(cop))


@router.get("/jobs/{job_id}")
def job_status(job_id: str, user=Depends(get_current_user)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("username") != user.get("username") and user.get("role") != "admin":
        raise HTTPException(status_code=404, detail="Job not found")
    return public_job(job)


@router.post("/jobs/excel-upload")
async def job_excel_upload(file: UploadFile = File(...), user=Depends(require_permission("settings"))):
    _require_admin(user)
    name = (file.filename or "upload.xlsx").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx or .xlsm).")
    content = await file.read()
    filename = file.filename or name
    jid = create_job("excel-upload", user["username"])

    def work(report):
        report(20, "Saving Excel…", "apply")
        status = excel_service.replace_from_bytes(content, username=user["username"], filename=filename)
        report(90, "Refreshing lists…", "apply")
        invalidate_dash_cache()
        count = status.get("record_count") if isinstance(status, dict) else None
        return {"ok": True, "sync": status, "seed": {"ok": True, "count": count, "error": None}}

    run_job(jid, work)
    return {"job_id": jid}


@router.post("/jobs/backup-apply")
async def job_backup_apply(file: UploadFile = File(...), user=Depends(require_permission("backup"))):
    name = (file.filename or "backup.xlsx").lower()
    if not name.endswith((".xlsx", ".xlsm", ".db", ".zip")):
        raise HTTPException(
            status_code=400,
            detail="Upload an Excel workbook (.xlsx/.xlsm), a SQLite snapshot (.db), or a zip of both.",
        )
    content = await file.read()
    filename = file.filename or name
    jid = create_job("backup-apply", user["username"])

    def work(report):
        report(25, "Storing backup…", "apply")
        stored = excel_service.store_uploaded_backup(content, filename=filename)
        report(55, "Applying backup…", "apply")
        restored = excel_service.restore_backup(stored["path"])
        report(88, "Refreshing lists…", "apply")
        excel_service.invalidate()
        invalidate_dash_cache()
        database.add_audit(
            user["username"],
            "backup_upload",
            details=f"Uploaded and applied backup {stored.get('name')}",
        )
        return {"ok": True, **stored, **restored, "sync": excel_service.status()}

    run_job(jid, work)
    return {"job_id": jid}


@router.get("/backups")
def list_backups(user=Depends(require_permission("backup"))):
    return {"items": excel_service.list_backups(), "schedule": schedule_status()}


class BackupCheck(BaseModel):
    path: str


@router.post("/backups/check")
def check_backup(body: BackupCheck, user=Depends(require_permission("backup"))):
    try:
        return excel_service.check_backup(body.path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    except Exception as cop:
        raise HTTPException(status_code=500, detail=str(cop))


class RestoreRequest(BaseModel):
    path: str
    record_id: Optional[str] = None
    work_order_id: Optional[str] = None
    site: Optional[str] = None


@router.post("/backups/restore")
async def restore_backup(body: RestoreRequest, user=Depends(require_permission("backup"))):
    def _run():
        result = excel_service.restore_backup(body.path)
        invalidate_dash_cache()
        return {"restored": True, **result, "sync": excel_service.status()}

    try:
        return await run_in_threadpool(_run)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/backups/preview-row")
def preview_restore_row(body: RestoreRequest, user=Depends(require_permission("backup"))):
    try:
        return excel_service.preview_restore_row(
            body.path,
            record_id=body.record_id or "",
            work_order_id=body.work_order_id or "",
            site=body.site or "",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/backups/restore-row")
def restore_backup_row(body: RestoreRequest, user=Depends(require_permission("backup"))):
    if not (body.record_id or body.work_order_id):
        raise HTTPException(status_code=400, detail="Provide a record id or work order number.")
    try:
        result = excel_service.restore_row_from_backup(
            body.path,
            username=user["username"],
            record_id=body.record_id or "",
            work_order_id=body.work_order_id or "",
            site=body.site or "",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {**result, "sync": excel_service.status()}


@router.post("/backups")
def create_backup(user=Depends(require_permission("backup"))):
    export_err = None
    try:
        excel_service.export_database_to_excel(username=user["username"])
    except Exception as exc:
        export_err = str(exc)
    try:
        path = excel_service.create_backup(reason="manual")
    except Exception as exc:
        path = None
        if not export_err:
            export_err = str(exc)
    cfg = load_config()
    try:
        archived = excel_service.archive_old_backups(int(getattr(cfg, "backup_archive_days", 30) or 30))
    except Exception:
        archived = {"moved": 0}
    try:
        pruned_arch = excel_service.prune_archives(int(getattr(cfg, "backup_archive_keep_days", 180) or 180))
    except Exception:
        pruned_arch = {"removed": 0}
    try:
        pruned = excel_service.prune_backups(int(getattr(cfg, "backup_ratio", 14) or 0), reasons=("auto", "manual"))
    except Exception:
        pruned = 0
    health = None
    if path:
        try:
            health = excel_service.check_backup(str(path))
        except Exception as cop:
            health = {"ok": False, "error": str(cop), "path": str(path)}
    if export_err:
        health = dict(health or {"path": str(path) if path else None})
        health["ok"] = False
        health["excel_export_ok"] = False
        health["error"] = export_err
    try:
        items = excel_service.list_backups()
    except Exception:
        items = []
    return {
        "path": str(path) if path else None,
        "pruned": pruned,
        "archived": archived,
        "pruned_archives": pruned_arch,
        "health": health,
        "items": items,
        "schedule": schedule_status(cfg),
    }


@router.get("/backups/download")
def download_backup(path: str = Query(...), user=Depends(require_permission("backup"))):
    try:
        files = excel_service.backup_files_for_download(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if len(files) == 1:
        return FileResponse(
            path=str(files[0]),
            filename=files[0].name,
            media_type="application/octet-stream",
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in files:
            zf.write(item, arcname=item.name)
    zip_name = f"{files[0].stem}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@router.post("/backups/upload")
async def upload_backup(file: UploadFile = File(...), user=Depends(require_permission("backup"))):
    name = (file.filename or "backup.xlsx").lower()
    if not name.endswith((".xlsx", ".xlsm", ".db", ".zip")):
        raise HTTPException(
            status_code=400,
            detail="Upload an Excel workbook (.xlsx/.xlsm), a SQLite snapshot (.db), or a zip of both.",
        )
    content = await file.read()
    filename = file.filename or name

    def _run():
        stored = excel_service.store_uploaded_backup(content, filename=filename)
        database.add_audit(
            user["username"],
            "backup_upload",
            details=f"Uploaded backup {stored.get('name')} ({stored.get('size') or 0} bytes)",
        )
        return {
            **stored,
            "items": excel_service.list_backups(),
            "schedule": schedule_status(),
        }

    try:
        return await run_in_threadpool(_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc


@router.post("/backups/run-auto")
def run_auto_now(user=Depends(require_permission("backup"))):
    path = run_due_backup(force=True)
    if path is None:
        raise HTTPException(status_code=503, detail="Backup could not be created.")
    sched = schedule_status()
    return {
        "path": str(path) if path else None,
        "health": sched.get("last_auto_backup_health"),
        "items": excel_service.list_backups(),
        "schedule": sched,
    }


@router.get("/folders")
def folders(path: Optional[str] = Query(None), user=Depends(require_permission("settings"))):
    try:
        return list_folders(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class FolderCreate(BaseModel):
    path: str


class ConfirmBody(BaseModel):
    confirm: str = ""


def _require_admin(user) -> None:
    if str(user.get("role") or "") != "admin":
        raise HTTPException(status_code=403, detail="Only an administrator can reset or reseed the database.")


@router.get("/database")
def get_database_status(user=Depends(require_permission("settings"))):
    try:
        status = database.database_status()
        status["excel_available"] = excel_service.available()
        status["excel_path"] = str(excel_service.excel_path())
        return status
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read database status: {exc}") from exc


@router.post("/database/seed")
async def seed_database(user=Depends(require_permission("settings"))):
    _require_admin(user)

    def _run():
        result = excel_service.seed_from_excel(username=user["username"], replace_lines=True)
        excel_service.invalidate()
        invalidate_dash_cache()
        if not result.get("ok"):
            raise ValueError(result.get("error") or "Seed from Excel failed.")
        return {**result, "sync": excel_service.status()}

    try:
        return await run_in_threadpool(_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Seed failed: {exc}") from exc


@router.post("/database/reset")
def reset_app_database(body: ConfirmBody, user=Depends(require_permission("settings"))):
    _require_admin(user)
    if (body.confirm or "").strip() != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to confirm wiping the database.")
    try:
        wiped = database.reset_database()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Reset failed: {exc}") from exc
    excel_service.invalidate()
    if not wiped.get("ok"):
        raise HTTPException(status_code=500, detail="; ".join(wiped.get("errors") or ["Reset failed"]))
    try:
        seed = excel_service.seed_from_excel(username=user["username"], replace_lines=True)
    except Exception as exc:
        seed = {"ok": False, "error": str(exc), "count": 0}
    try:
        database.add_audit(user["username"], "reset", details="Wiped application database and recreated default users")
    except Exception:
        pass
    return {
        "reset": True,
        "users": wiped.get("users"),
        "seed": seed,
        "relogin": True,
        "sync": excel_service.status() if seed.get("ok") else excel_service.ping(),
    }


@router.post("/database/upload")
async def upload_excel_and_seed(file: UploadFile = File(...), user=Depends(require_permission("settings"))):
    _require_admin(user)
    name = (file.filename or "upload.xlsx").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx or .xlsm).")
    content = await file.read()
    filename = file.filename or name

    def _run():
        status = excel_service.replace_from_bytes(content, username=user["username"], filename=filename)
        invalidate_dash_cache()
        count = status.get("record_count") if isinstance(status, dict) else None
        return {"ok": True, "sync": status, "seed": {"ok": True, "count": count, "error": None}}

    try:
        return await run_in_threadpool(_run)
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc


@router.post("/folders")
def create_folder(body: FolderCreate, user=Depends(require_permission("settings"))):
    try:
        require_app_folder(body.path)
        path = ensure_folder(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"path": str(path), "listing": list_folders(str(path))}
