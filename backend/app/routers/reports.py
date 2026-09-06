from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..reports import render
from ..security import require_permission
from ..stats import parse_query_filters

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{kind}")
def download_report(
    kind: str,
    fmt: str = "xlsx",
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    year: Optional[str] = None,
    month: Optional[str] = None,
    week: Optional[str] = None,
    status: Optional[str] = None,
    department: Optional[str] = None,
    assigned_to: Optional[str] = None,
    flag: Optional[str] = None,
    user=Depends(require_permission("reports")),
):
    kind = kind.lower()
    allowed = {"daily", "weekly", "monthly", "yearly", "open", "overdue", "closed", "delay", "department", "technician"}
    if kind not in allowed:
        raise HTTPException(status_code=404, detail="Unknown report")
    fmt = fmt.lower()
    if fmt not in {"xlsx", "csv", "pdf"}:
        raise HTTPException(status_code=400, detail="Format must be xlsx, csv or pdf")
    filters = parse_query_filters(locals())
    try:
        data, filename, mime = render(kind, fmt, filters)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {exc}") from exc
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
