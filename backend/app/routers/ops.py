from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..excel.service import ExcelLocked, ExcelUnavailable
from ..ops import alerts_payload, queue_payload, supplier_payload
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
