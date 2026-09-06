from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import load_config
from ..domain import annotate, matches_filters
from ..excel.service import ExcelLocked, ExcelUnavailable, SyncConflict, excel_service
from ..security import get_current_user, require_permission
from ..stats import parse_query_filters
from ..validation import validate_work_order

router = APIRouter(prefix="/api/work-orders", tags=["work-orders"])


class WorkOrderUpdate(BaseModel):
    changes: dict[str, Any] = Field(default_factory=dict)
    sync_token: Optional[str] = None
    force: bool = False


class WorkOrderCreate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


def _raise_excel(exc: Exception):
    if isinstance(exc, ExcelUnavailable):
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ExcelLocked):
        raise HTTPException(status_code=423, detail=str(exc))
    if isinstance(exc, SyncConflict):
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "conflict": True, "current": exc.current},
        )
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("")
def list_work_orders(
    q: Optional[str] = None,
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    year: Optional[str] = None,
    month: Optional[str] = None,
    week: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    department: Optional[str] = None,
    location: Optional[str] = None,
    assigned_to: Optional[str] = None,
    work_type: Optional[str] = None,
    delay_reason: Optional[str] = None,
    supplier: Optional[str] = None,
    issue: Optional[str] = None,
    flag: Optional[str] = None,
    aging: Optional[str] = None,
    reason: Optional[str] = None,
    sort: str = "created_date",
    order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    user=Depends(require_permission("view")),
):
    try:
        records = excel_service.get_all()
    except (ExcelUnavailable, ExcelLocked) as exc:
        _raise_excel(exc)
    filters = parse_query_filters(locals())
    cfg = load_config()
    matched = [annotate(r, cfg) for r in records if matches_filters(r, filters, cfg)]
    if reason:
        matched = [r for r in matched if (r.get("open_reason") or "") == reason]
    reverse = order.lower() != "asc"
    numeric_sorts = {"aging_days", "days_overdue", "closing_days"}
    def sort_key(r):
        v = r.get(sort)
        if v is None:
            return -10**12 if reverse else 10**12
        if sort in numeric_sorts:
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0
        return str(v).lower()

    matched.sort(key=sort_key, reverse=reverse)
    total = len(matched)
    start = (page - 1) * page_size
    page_rows = matched[start : start + page_size]
    return {
        "items": page_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 1,
        "sync_token": excel_service.sync_token(),
        "headers": excel_service.headers(),
    }


@router.get("/options")
def options(user=Depends(require_permission("view"))):
    try:
        records = excel_service.get_all()
    except (ExcelUnavailable, ExcelLocked) as exc:
        _raise_excel(exc)
    fields = [
        "status",
        "priority",
        "department",
        "location",
        "assigned_to",
        "work_type",
        "delay_reason",
        "supplier",
        "issue",
    ]
    opts = {f: excel_service.unique_values(f) for f in fields}
    lists = excel_service.lists()
    return {
        "options": opts,
        "lists": lists,
        "mapping": load_config().mapping.model_dump(),
        "headers": excel_service.headers(),
        "sync_token": excel_service.sync_token(),
    }


@router.get("/{wo_id}")
def get_work_order(wo_id: str, user=Depends(require_permission("view"))):
    try:
        rec = excel_service.get_by_id(wo_id)
    except (ExcelUnavailable, ExcelLocked) as exc:
        _raise_excel(exc)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    return {"item": annotate(rec), "sync_token": excel_service.sync_token()}


@router.put("/{wo_id}")
def update_work_order(wo_id: str, body: WorkOrderUpdate, user=Depends(require_permission("edit"))):
    rec = excel_service.get_by_id(wo_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    merged = {**{k: rec.get(k) for k in load_config().mapping.model_dump().keys()}, **body.changes}
    errors = validate_work_order(merged, partial=False)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    try:
        updated = excel_service.update_record(
            wo_id, body.changes, username=user["username"], sync_token=body.sync_token, force=body.force
        )
    except (ExcelUnavailable, ExcelLocked, SyncConflict, KeyError, ValueError) as exc:
        _raise_excel(exc)
    return {"item": annotate(updated), "sync_token": excel_service.sync_token(), "saved": True}


@router.post("")
def create_work_order(body: WorkOrderCreate, user=Depends(require_permission("create"))):
    errors = validate_work_order(body.data, partial=False)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    try:
        created = excel_service.create_record(body.data, username=user["username"])
    except (ExcelUnavailable, ExcelLocked, ValueError) as exc:
        _raise_excel(exc)
    return {"item": annotate(created), "sync_token": excel_service.sync_token(), "saved": True}


@router.delete("/{wo_id}")
def delete_work_order(wo_id: str, user=Depends(require_permission("delete"))):
    try:
        excel_service.delete_record(wo_id, username=user["username"])
    except (ExcelUnavailable, ExcelLocked, KeyError) as exc:
        _raise_excel(exc)
    return {"deleted": True, "id": wo_id, "sync_token": excel_service.sync_token()}
