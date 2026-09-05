from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..excel.service import ExcelLocked, ExcelUnavailable, excel_service
from ..security import require_permission
from ..stats import dashboard_payload

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status")
def sync_status(user=Depends(require_permission("view"))):
    return excel_service.status()


@router.get("/ping")
def sync_ping(user=Depends(require_permission("view"))):
    return excel_service.ping()


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


@router.post("/upload")
async def upload_excel(
    file: UploadFile = File(...),
    user=Depends(require_permission("edit")),
):
    name = (file.filename or "upload.xlsx").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx).")
    content = await file.read()
    try:
        status = excel_service.replace_from_bytes(content, username=user["username"], filename=file.filename or name)
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc
    dash = dashboard_payload({})
    return {"ok": True, "sync": status, "kpis": dash.get("kpis"), "mindmap": dash.get("mindmap")}
