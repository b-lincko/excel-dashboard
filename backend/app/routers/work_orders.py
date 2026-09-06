from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import database
from ..config import load_config
from ..dates import to_date
from ..domain import aging_days, annotate, is_overdue, matches_filters, reason_for_open, today
from ..excel.service import DELAY_FIELDS, DUE_OFFSETS, ExcelLocked, ExcelUnavailable, SyncConflict, excel_service
from ..security import require_permission
from ..stats import parse_query_filters
from ..validation import validate_work_order

EXTRA_FIELDS = set(DELAY_FIELDS)


def _overlay_fields(rec: dict[str, Any], extra: dict[str, Any] | None) -> dict[str, Any]:
    extra = extra or {}
    ready = excel_service.delay_columns_ready()
    out: dict[str, Any] = {}
    for field in DELAY_FIELDS:
        excel_val = str(rec.get(field) or "").strip()
        db_val = str(extra.get(field) or "").strip()
        out[field] = excel_val if (ready or excel_val) else db_val
    return out


def _with_extras(rec: dict[str, Any]) -> dict[str, Any]:
    extra = database.get_record_extra(str(rec.get("record_id") or ""))
    out = dict(rec)
    out.update(_overlay_fields(rec, extra))
    return out


def _with_extras_many(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    extras = database.get_record_extras([str(r.get("record_id") or "") for r in recs])
    out = []
    for rec in recs:
        item = dict(rec)
        item.update(_overlay_fields(rec, extras.get(str(rec.get("record_id") or ""))))
        out.append(item)
    return out


def _split_changes(changes: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    excel_changes: dict[str, Any] = {}
    extra_changes: dict[str, Any] = {}
    for key, value in (changes or {}).items():
        if key in EXTRA_FIELDS:
            extra_changes[key] = value if value is not None else ""
            excel_changes[key] = extra_changes[key]
        else:
            excel_changes[key] = value
    return excel_changes, extra_changes


def _save_extras(rec: dict[str, Any], extra_changes: dict[str, Any], username: str) -> None:
    if not extra_changes:
        return
    rid = str(rec.get("record_id") or "")
    if not rid:
        return
    database.upsert_record_extra(
        rid,
        username,
        work_order_id=str(rec.get("work_order_id") or ""),
        delay_kind=extra_changes.get("delay_kind"),
        delay_source=extra_changes.get("delay_source"),
        delay_justification=extra_changes.get("delay_justification"),
    )


def _maybe_add_supplier(name: Any, username: str) -> None:
    cleaned = " ".join(str(name or "").split())
    if cleaned:
        database.add_supplier(cleaned, created_by=username)

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
    matched = [r for r in records if matches_filters(r, filters, cfg)]
    if reason:
        matched = [r for r in matched if reason_for_open(r) == reason]
    reverse = order.lower() != "asc"
    t = today()

    def sort_key(r):
        if sort == "aging_days":
            return aging_days(r) or 0
        if sort == "days_overdue":
            if not is_overdue(r, cfg):
                return -1
            due = to_date(r.get("due_date"))
            return (t - due).days if due else -1
        v = r.get(sort)
        if v is None:
            return -10**12 if reverse else 10**12
        return str(v).lower()

    matched.sort(key=sort_key, reverse=reverse)
    total = len(matched)
    start = (page - 1) * page_size
    page_rows = [annotate(r, cfg) for r in _with_extras_many(matched[start : start + page_size])]
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
    buckets: dict[str, set] = {f: set() for f in fields}
    for rec in records:
        for f in fields:
            v = rec.get(f)
            if v not in (None, ""):
                buckets[f].add(str(v))
    opts = {f: sorted(buckets[f], key=str.lower) for f in fields}
    lists = excel_service.lists()
    cfg = load_config()
    catalog_names = [s["name"] for s in database.list_suppliers() if s.get("name")]
    suppliers = sorted({*opts.get("supplier", []), *catalog_names}, key=str.lower)
    opts["supplier"] = suppliers
    offsets = dict(DUE_OFFSETS)
    offsets.update({str(k).lower(): int(v) for k, v in (cfg.due_offsets or {}).items()})
    return {
        "options": opts,
        "lists": lists,
        "mapping": cfg.mapping.model_dump(),
        "headers": excel_service.headers(),
        "sync_token": excel_service.sync_token(),
        "due_offsets": offsets,
        "due_offset_default_days": cfg.due_offset_default_days,
        "delay_kinds": ["placement", "delivery"],
        "delay_sources": ["site", "procurement", "supplier"],
    }


@router.get("/{wo_id}")
def get_work_order(wo_id: str, user=Depends(require_permission("view"))):
    try:
        rec = excel_service.get_by_id(wo_id)
    except (ExcelUnavailable, ExcelLocked) as exc:
        _raise_excel(exc)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    return {"item": annotate(_with_extras(rec)), "sync_token": excel_service.sync_token()}


@router.put("/{wo_id}")
def update_work_order(wo_id: str, body: WorkOrderUpdate, user=Depends(require_permission("edit"))):
    rec = excel_service.get_by_id(wo_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    excel_changes, extra_changes = _split_changes(body.changes)
    merged = {**{k: rec.get(k) for k in load_config().mapping.model_dump().keys()}, **excel_changes}
    errors = validate_work_order(merged, partial=False)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    updated = rec
    if excel_changes:
        try:
            updated = excel_service.update_record(
                wo_id, excel_changes, username=user["username"], sync_token=body.sync_token, force=body.force
            )
        except (ExcelUnavailable, ExcelLocked, SyncConflict, KeyError, ValueError) as exc:
            _raise_excel(exc)
    if extra_changes:
        _save_extras(updated, extra_changes, user["username"])
    if excel_changes.get("supplier"):
        _maybe_add_supplier(excel_changes.get("supplier"), user["username"])
    return {"item": annotate(_with_extras(updated)), "sync_token": excel_service.sync_token(), "saved": True}


@router.post("")
def create_work_order(body: WorkOrderCreate, user=Depends(require_permission("create"))):
    excel_data, extra_changes = _split_changes(body.data)
    errors = validate_work_order(excel_data, partial=False)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    try:
        created = excel_service.create_record(excel_data, username=user["username"])
    except (ExcelUnavailable, ExcelLocked, ValueError) as exc:
        _raise_excel(exc)
    if extra_changes:
        _save_extras(created, extra_changes, user["username"])
    if excel_data.get("supplier"):
        _maybe_add_supplier(excel_data.get("supplier"), user["username"])
    return {"item": annotate(_with_extras(created)), "sync_token": excel_service.sync_token(), "saved": True}


@router.delete("/{wo_id}")
def delete_work_order(wo_id: str, user=Depends(require_permission("delete"))):
    try:
        excel_service.delete_record(wo_id, username=user["username"])
    except (ExcelUnavailable, ExcelLocked, KeyError) as exc:
        _raise_excel(exc)
    return {"deleted": True, "id": wo_id, "sync_token": excel_service.sync_token()}
