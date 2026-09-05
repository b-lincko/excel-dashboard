from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..excel.service import ExcelLocked, ExcelUnavailable, excel_service
from ..security import require_permission

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status")
def sync_status(user=Depends(require_permission("view"))):
    return excel_service.status()


@router.post("/refresh")
def refresh(user=Depends(require_permission("view"))):
    try:
        records = excel_service.load(force=True)
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    status = excel_service.status()
    status["record_count"] = len(records)
    return status
