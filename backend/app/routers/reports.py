from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from ..reports import period_payload, render
from ..security import require_permission
from ..stats import parse_query_filters

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{kind}")
def download_report(
    kind: str,
    fmt: str = "pdf",
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
    as_of: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    user=Depends(require_permission("reports")),
):
    kind = kind.lower()
    allowed = {"daily", "weekly", "monthly", "yearly", "open", "overdue", "closed", "delay", "department", "technician"}
    if kind not in allowed:
        raise HTTPException(status_code=404, detail="Unknown report")
    fmt = fmt.lower()
    if fmt not in {"xlsx", "csv", "pdf", "json"}:
        raise HTTPException(status_code=400, detail="Format must be pdf, xlsx, csv or json")
    filters = parse_query_filters(locals())
    filters["as_of"] = as_of or date or date_from or ""
    if fmt == "json" and kind in {"daily", "weekly"}:
        try:
            return period_payload(kind, filters)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to generate report: {exc}") from exc
    try:
        data, filename, mime = render(kind, fmt, filters)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {exc}") from exc
    if fmt == "json":
        return JSONResponse(content=__import__("json").loads(data.decode("utf-8")))
    inline = fmt == "pdf"
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
