from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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
    return {"settings": data, "sync": excel_service.status()}


@router.put("")
def update_settings(body: SettingsUpdate, user=Depends(require_permission("settings"))):
    cfg = load_config()
    current = cfg.model_dump()
    current.update(body.values)
    try:
        new_cfg = AppConfig.model_validate(current)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    save_config(new_cfg)
    excel_service.invalidate()
    return {"settings": new_cfg.model_dump(), "saved": True}


@router.get("/backups")
def list_backups(user=Depends(require_permission("backup"))):
    return {"items": excel_service.list_backups()}


class RestoreRequest(BaseModel):
    path: str


@router.post("/backups/restore")
def restore_backup(body: RestoreRequest, user=Depends(require_permission("backup"))):
    try:
        excel_service.restore_backup(body.path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"restored": True, "sync": excel_service.status()}


@router.post("/backups")
def create_backup(user=Depends(require_permission("backup"))):
    path = excel_service.create_backup(reason="manual")
    return {"path": str(path) if path else None}
