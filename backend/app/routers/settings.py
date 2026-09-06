from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..backup import ensure_folder, list_folders, run_due_backup, schedule_status
from ..config import AppConfig, load_config, save_config
from ..excel.service import excel_service
from ..security import require_permission

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


@router.get("")
def get_settings(user=Depends(require_permission("settings"))):
    cfg = load_config()
    data = cfg.model_dump()
    if user["role"] != "admin":
        data.pop("jwt_secret", None)
    return {"settings": data, "sync": excel_service.status(), "backup": schedule_status(cfg)}


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
    return {"settings": new_cfg.model_dump(), "saved": True, "backup": schedule_status(new_cfg)}


@router.get("/backups")
def list_backups(user=Depends(require_permission("backup"))):
    return {"items": excel_service.list_backups(), "schedule": schedule_status()}


class RestoreRequest(BaseModel):
    path: str
    record_id: Optional[str] = None
    work_order_id: Optional[str] = None
    site: Optional[str] = None


@router.post("/backups/restore")
def restore_backup(body: RestoreRequest, user=Depends(require_permission("backup"))):
    try:
        excel_service.restore_backup(body.path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"restored": True, "sync": excel_service.status()}


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
    path = excel_service.create_backup(reason="manual")
    cfg = load_config()
    pruned = excel_service.prune_backups(int(getattr(cfg, "backup_ratio", 14) or 0), reasons=("auto", "manual"))
    return {
        "path": str(path) if path else None,
        "pruned": pruned,
        "items": excel_service.list_backups(),
        "schedule": schedule_status(cfg),
    }


@router.post("/backups/run-auto")
def run_auto_now(user=Depends(require_permission("backup"))):
    path = run_due_backup(force=True)
    if path is None and not excel_service.available():
        raise HTTPException(status_code=503, detail="Excel file is currently unavailable.")
    return {
        "path": str(path) if path else None,
        "items": excel_service.list_backups(),
        "schedule": schedule_status(),
    }


@router.get("/folders")
def folders(path: Optional[str] = Query(None), user=Depends(require_permission("settings"))):
    try:
        return list_folders(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class FolderCreate(BaseModel):
    path: str


@router.post("/folders")
def create_folder(body: FolderCreate, user=Depends(require_permission("settings"))):
    try:
        path = ensure_folder(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"path": str(path), "listing": list_folders(str(path))}
