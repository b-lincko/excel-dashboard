from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import database, notify, reports
from ..config import load_config
from ..dates import to_date
from ..domain import aging_days, annotate, is_overdue, matches_filters, reason_for_open, today
from ..excel.service import DELAY_FIELDS, DUE_OFFSETS, ExcelLocked, ExcelUnavailable, SyncConflict, excel_service
from ..security import editable_fields, forbidden_fields, require_permission
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


class BulkUpdate(BaseModel):
    ids: list[str] = Field(default_factory=list)
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    remarks: Optional[str] = None
    append_remarks: bool = True
    sync_token: Optional[str] = None
    force: bool = False


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
    aging_min: Optional[str] = None,
    watched: Optional[int] = None,
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
    if watched or flag == "watched":
        watched_ids = set(database.list_watched_ids(user["username"]))
        matched = [r for r in matched if str(r.get("record_id") or "") in watched_ids]
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
        "editable_fields": editable_fields(user, cfg),
        "status_required_fields": getattr(cfg, "status_required_fields", None) or {},
        "field_edit_roles": getattr(cfg, "field_edit_roles", None) or {},
    }


@router.post("/bulk")
def bulk_update(body: BulkUpdate, user=Depends(require_permission("edit"))):
    changes: dict[str, Any] = {}
    if body.assigned_to is not None:
        changes["assigned_to"] = body.assigned_to
    if body.status is not None:
        changes["status"] = body.status
    remark = (body.remarks or "").strip()
    append = bool(remark) and bool(body.append_remarks)
    if remark:
        changes["remarks"] = remark
    if not changes:
        raise HTTPException(status_code=400, detail="Choose an assignee, a status, or a remark.")
    blocked = forbidden_fields(user, changes)
    if blocked:
        raise HTTPException(
            status_code=403,
            detail=f"Your role cannot edit: {', '.join(blocked)}.",
        )
    try:
        result = excel_service.update_records(
            body.ids,
            changes,
            username=user["username"],
            append_remarks=append,
            sync_token=body.sync_token,
            force=body.force,
        )
    except (ExcelUnavailable, ExcelLocked, SyncConflict, KeyError, ValueError) as exc:
        _raise_excel(exc)
    actor = user["username"]
    parts = []
    if body.assigned_to is not None:
        parts.append(f"assigned to {body.assigned_to or '—'}")
    if body.status is not None:
        parts.append(f"status {body.status or '—'}")
    if remark:
        parts.append("remark added" if append else "remarks replaced")
    summary_tail = ", ".join(parts) or "updated"
    items = []
    for rec in result["items"]:
        pinged = notify.fanout_mentions(
            actor,
            remark,
            record_id=str(rec.get("record_id") or ""),
            work_order_id=str(rec.get("work_order_id") or ""),
        ) if remark else []
        notify.notify_watchers(
            actor,
            rec,
            f"{actor} bulk-updated {rec.get('work_order_id') or rec.get('record_id')}: {summary_tail}",
            skip=set(pinged),
        )
        items.append(annotate(_with_extras(rec)))
    return {
        "items": items,
        "updated": len(items),
        "missing": result.get("missing") or [],
        "sync_token": excel_service.sync_token(),
        "saved": True,
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
    blocked = forbidden_fields(user, {**excel_changes, **extra_changes})
    if blocked:
        raise HTTPException(
            status_code=403,
            detail=f"Your role cannot edit: {', '.join(blocked)}.",
        )
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
    actor = user["username"]
    remark = str(excel_changes.get("remarks") or "")
    pinged = (
        notify.fanout_mentions(
            actor,
            remark,
            record_id=str(updated.get("record_id") or ""),
            work_order_id=str(updated.get("work_order_id") or ""),
        )
        if remark
        else []
    )
    if excel_changes or extra_changes:
        bits = [k for k in {**excel_changes, **extra_changes} if k != "remarks"]
        if remark:
            bits.append("remarks")
        notify.notify_watchers(
            actor,
            updated,
            f"{actor} updated {updated.get('work_order_id') or wo_id}" + (f" ({', '.join(bits)})" if bits else ""),
            skip=set(pinged),
        )
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


@router.get("/{wo_id}/watch")
def watch_state(wo_id: str, user=Depends(require_permission("view"))):
    rec = excel_service.get_by_id(wo_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    rid = str(rec.get("record_id") or "")
    return {
        "watching": database.is_watching(user["username"], rid),
        "watchers": database.list_watchers(rid),
        "record_id": rid,
        "work_order_id": rec.get("work_order_id"),
    }


@router.post("/{wo_id}/watch")
def follow_work_order(wo_id: str, user=Depends(require_permission("view"))):
    rec = excel_service.get_by_id(wo_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    rid = str(rec.get("record_id") or "")
    database.add_watch(user["username"], rid, str(rec.get("work_order_id") or ""))
    return {
        "watching": True,
        "watchers": database.list_watchers(rid),
        "record_id": rid,
        "work_order_id": rec.get("work_order_id"),
    }


@router.delete("/{wo_id}/watch")
def unfollow_work_order(wo_id: str, user=Depends(require_permission("view"))):
    rec = excel_service.get_by_id(wo_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    rid = str(rec.get("record_id") or "")
    database.remove_watch(user["username"], rid)
    return {
        "watching": False,
        "watchers": database.list_watchers(rid),
        "record_id": rid,
        "work_order_id": rec.get("work_order_id"),
    }


@router.get("/{wo_id}/sheet")
def work_order_sheet(wo_id: str, user=Depends(require_permission("view"))):
    try:
        rec = excel_service.get_by_id(wo_id)
    except (ExcelUnavailable, ExcelLocked) as exc:
        _raise_excel(exc)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    item = annotate(_with_extras(rec))
    files = database.list_attachments(str(item.get("record_id") or ""))
    pdf = reports.wo_sheet_pdf(item, files)
    name = str(item.get("work_order_id") or wo_id).replace("/", "-")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="WO_{name}.pdf"'},
    )


class ChatBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.get("/{wo_id}/chat")
def work_order_chat(wo_id: str, after: int = 0, limit: int = 200, user=Depends(require_permission("view"))):
    rec = excel_service.get_by_id(wo_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    thread = database.get_or_create_wo_thread(
        str(rec.get("record_id") or ""),
        str(rec.get("work_order_id") or ""),
        user["username"],
    )
    items = database.list_chat_messages(int(thread["id"]), after_id=after, limit=limit)
    return {"thread": thread, "items": items}


@router.post("/{wo_id}/chat")
def post_work_order_chat(wo_id: str, body: ChatBody, user=Depends(require_permission("view"))):
    rec = excel_service.get_by_id(wo_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    thread = database.get_or_create_wo_thread(
        str(rec.get("record_id") or ""),
        str(rec.get("work_order_id") or ""),
        user["username"],
    )
    item = database.add_chat_message(int(thread["id"]), user["username"], text)
    pinged = notify.fanout_mentions(
        user["username"],
        text,
        record_id=str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
        thread_id=int(thread["id"]),
    )
    notify.notify_watchers(
        user["username"],
        rec,
        f"{user['username']} commented on {rec.get('work_order_id') or wo_id}",
        skip=set(pinged),
    )
    return {"thread": thread, "item": item}


@router.post("/{wo_id}/seen")
def mark_seen(wo_id: str, user=Depends(require_permission("view"))):
    rec = excel_service.get_by_id(wo_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
    item = database.mark_queue_seen(str(rec.get("record_id") or wo_id), user["username"])
    return {"item": item, "seen_by": database.list_queue_seen([item["record_id"]]).get(item["record_id"], [])}


@router.delete("/{wo_id}")
def delete_work_order(wo_id: str, user=Depends(require_permission("delete"))):
    try:
        excel_service.delete_record(wo_id, username=user["username"])
    except (ExcelUnavailable, ExcelLocked, KeyError) as exc:
        _raise_excel(exc)
    return {"deleted": True, "id": wo_id, "sync_token": excel_service.sync_token()}
