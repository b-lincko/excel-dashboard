from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ..dates import week_bounds
from ..domain import today
from ..excel.service import ExcelLocked, ExcelUnavailable, excel_service
from ..security import require_permission
from ..stats import (
    dashboard_payload,
    filtered,
    group_by,
    kpis,
    monthly,
    parse_query_filters,
    reasons,
    status_distribution,
    weekly,
    yearly,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _filters(params: dict) -> dict:
    return parse_query_filters(params)


def _records():
    try:
        return excel_service.get_all()
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))


@router.get("")
def dashboard(
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
    flag: Optional[str] = None,
    user=Depends(require_permission("view")),
):
    filters = _filters(locals())
    try:
        payload = dashboard_payload(filters)
    except ExcelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExcelLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))
    payload["sync"] = excel_service.status()
    return payload


@router.get("/kpis")
def get_kpis(
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    year: Optional[str] = None,
    user=Depends(require_permission("view")),
):
    recs = filtered(_records(), _filters(locals()))
    return kpis(recs)


@router.get("/weekly")
def get_weekly(year: Optional[int] = None, week: Optional[int] = None, user=Depends(require_permission("view"))):
    t = today()
    iso = t.isocalendar()
    y = year or int(iso[0])
    w = week or int(iso[1])
    return weekly(_records(), y, w)


@router.get("/monthly")
def get_monthly(year: Optional[int] = None, user=Depends(require_permission("view"))):
    return monthly(_records(), year or today().year)


@router.get("/yearly")
def get_yearly(user=Depends(require_permission("view"))):
    return yearly(_records())


@router.get("/status")
def get_status(user=Depends(require_permission("view"))):
    return status_distribution(_records())


@router.get("/reasons")
def get_reasons(user=Depends(require_permission("view"))):
    return reasons(_records())


@router.get("/departments")
def get_departments(user=Depends(require_permission("view"))):
    return group_by(_records(), "department")


@router.get("/employees")
def get_employees(user=Depends(require_permission("view"))):
    return group_by(_records(), "assigned_to")
