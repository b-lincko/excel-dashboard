from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import database
from ..excel.service import ExcelLocked, ExcelUnavailable, excel_service
from ..ops import alerts_payload, handover_snapshot, queue_payload, supplier_payload
from ..security import require_permission
from ..stats import parse_query_filters

router = APIRouter(prefix="/api/ops", tags=["ops"])


def _filters(params: dict) -> dict:
    return parse_query_filters(params)


@router.get("/queue")
def action_queue(
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
    assigned_to: Optional[str] = None,
    work_type: Optional[str] = None,
    supplier: Optional[str] = None,
    user=Depends(require_permission("view")),
):
    try:
        return queue_payload(_filters(locals()))
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))


@router.get("/alerts")
def sla_alerts(
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
    assigned_to: Optional[str] = None,
    work_type: Optional[str] = None,
    supplier: Optional[str] = None,
    user=Depends(require_permission("view")),
):
    try:
        return alerts_payload(_filters(locals()))
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))


@router.get("/suppliers")
def suppliers(
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
    assigned_to: Optional[str] = None,
    work_type: Optional[str] = None,
    supplier: Optional[str] = None,
    user=Depends(require_permission("view")),
):
    try:
        return supplier_payload(_filters(locals()))
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))


class HandoverIn(BaseModel):
    notes: str = ""
    department: str = ""
    shift: str = ""


class SeenIn(BaseModel):
    record_id: str = Field(min_length=1)


@router.get("/handover")
def handover_live(
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
    assigned_to: Optional[str] = None,
    work_type: Optional[str] = None,
    supplier: Optional[str] = None,
    user=Depends(require_permission("view")),
):
    try:
        live = handover_snapshot(_filters(locals()))
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    return {"live": live, "items": database.list_handovers()}


@router.post("/handover")
def publish_handover(body: HandoverIn, user=Depends(require_permission("edit"))):
    try:
        snap = handover_snapshot()
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    item = database.create_handover(
        username=user["username"],
        notes=body.notes or "",
        snapshot=snap,
        department=body.department or "",
        shift=body.shift or "",
    )
    return {"item": item}


@router.get("/health")
def excel_health(user=Depends(require_permission("view"))):
    try:
        return excel_service.health_scan()
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))


@router.post("/seen")
def mark_queue_item_seen(body: SeenIn, user=Depends(require_permission("view"))):
    rec = excel_service.get_by_id(body.record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Work order not found")
    item = database.mark_queue_seen(str(rec.get("record_id") or body.record_id), user["username"])
    seen = database.list_queue_seen([item["record_id"]]).get(item["record_id"], [])
    return {"item": item, "seen_by": seen}
