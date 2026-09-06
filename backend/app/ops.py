from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from typing import Any, Optional

from .config import load_config
from .dates import to_date
from .domain import (
    aging_days,
    annotate,
    closing_days,
    is_awaiting_po,
    is_closed,
    is_created_today,
    is_delivered,
    is_due_this_week,
    is_eta_late,
    is_ntp,
    is_on_hold,
    is_open,
    is_overdue,
    is_pending_po,
    matches_filters,
    today,
)
from .excel.service import excel_service

SLIM_KEYS = (
    "record_id",
    "work_order_id",
    "description",
    "department",
    "assigned_to",
    "status",
    "priority",
    "issue",
    "supplier",
    "po_number",
    "due_date",
    "created_date",
    "closed_date",
    "scheduled_date",
    "location",
    "work_type",
    "remarks",
    "aging_days",
    "days_overdue",
    "days_to_eta",
    "is_overdue",
    "is_ntp",
    "is_on_hold",
    "is_eta_late",
    "is_pending_po",
    "is_delivered",
)


def _slim(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: rec.get(k) for k in SLIM_KEYS}


def _take(rows: list[dict[str, Any]], cfg, n: int = 40) -> list[dict[str, Any]]:
    return [_slim(annotate(r, cfg)) for r in rows[:n]]


def _sort_num(rows: list[dict[str, Any]], key: str, reverse: bool = True) -> list[dict[str, Any]]:
    def val(r):
        v = r.get(key)
        if v is None:
            return -10**9 if reverse else 10**9
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0

    return sorted(rows, key=val, reverse=reverse)


def _sort_date(rows: list[dict[str, Any]], key: str, reverse: bool = False) -> list[dict[str, Any]]:
    def val(r):
        d = to_date(r.get(key))
        return d.toordinal() if d else (0 if reverse else 10**9)

    return sorted(rows, key=val, reverse=reverse)


def _filtered(records: list[dict[str, Any]], filters: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    cfg = load_config()
    if not filters:
        return records
    return [r for r in records if matches_filters(r, filters, cfg)]


def queue_payload(filters: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = load_config()
    all_records = excel_service.get_all()
    records = _filtered(all_records, filters or {})
    t = today()
    iso = t.isocalendar()

    overdue = _sort_date([r for r in records if is_overdue(r, cfg)], "due_date", False)
    ntp = _sort_date([r for r in records if is_ntp(r) and is_open(r, cfg)], "created_date", False)
    on_hold = _sort_date([r for r in records if is_on_hold(r) and is_open(r, cfg)], "created_date", False)
    due_week = _sort_date([r for r in records if is_due_this_week(r, cfg)], "due_date", False)
    created_today = _sort_date([r for r in records if is_created_today(r)], "created_date", True)
    done_today = [
        r
        for r in records
        if is_closed(r, cfg)
        and (
            to_date(r.get("closed_date")) == t
            or to_date(r.get("completion_date")) == t
            or to_date(r.get("scheduled_date")) == t
        )
    ]
    eta_late = _sort_date([r for r in records if is_eta_late(r, cfg)], "closed_date", False)
    pending_po = _sort_date([r for r in records if is_pending_po(r, cfg)], "created_date", False)

    return {
        "as_of": t.isoformat(),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "week": int(iso[1]),
        "year": int(iso[0]),
        "sync_token": excel_service.sync_token(),
        "count": len(records),
        "counts": {
            "overdue": len(overdue),
            "ntp": len(ntp),
            "on_hold": len(on_hold),
            "due_this_week": len(due_week),
            "created_today": len(created_today),
            "done_today": len(done_today),
            "eta_late": len(eta_late),
            "pending_po": len(pending_po),
        },
        "queues": {
            "overdue": _take(overdue, cfg),
            "ntp": _take(ntp, cfg),
            "on_hold": _take(on_hold, cfg),
            "due_this_week": _take(due_week, cfg),
            "created_today": _take(created_today, cfg),
            "done_today": _take(done_today, cfg),
            "eta_late": _take(eta_late, cfg),
            "pending_po": _take(pending_po, cfg),
        },
    }


def supplier_payload(filters: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = load_config()
    records = _filtered(excel_service.get_all(), filters or {})
    t = today()
    groups: dict[str, list] = defaultdict(list)
    for r in records:
        name = str(r.get("supplier") or "").strip() or "Unassigned"
        groups[name].append(r)

    rows = []
    for name, recs in groups.items():
        open_ = [r for r in recs if is_open(r, cfg)]
        closed = [r for r in recs if is_closed(r, cfg)]
        overdue = [r for r in recs if is_overdue(r, cfg)]
        delivered = [r for r in recs if is_delivered(r)]
        pending_delivery = [r for r in open_ if not is_delivered(r)]
        pending_po = [r for r in recs if is_pending_po(r, cfg)]
        awaiting_po = [r for r in recs if is_awaiting_po(r, cfg)]
        late = [r for r in recs if is_eta_late(r, cfg)]
        aging = [d for d in (aging_days(r) for r in open_) if d is not None]
        closing = [d for d in (closing_days(r) for r in closed) if d is not None]
        rows.append(
            {
                "name": name,
                "total": len(recs),
                "open": len(open_),
                "closed": len(closed),
                "overdue": len(overdue),
                "delivered": len(delivered),
                "pending_delivery": len(pending_delivery),
                "pending_po": len(pending_po),
                "awaiting_po": len(awaiting_po),
                "eta_late": len(late),
                "avg_aging_days": round(mean(aging), 1) if aging else None,
                "avg_close_days": round(mean(closing), 1) if closing else None,
                "completion_rate": round((len(closed) / len(recs) * 100) if recs else 0, 1),
            }
        )
    rows.sort(key=lambda x: (x["open"], x["eta_late"], x["total"]), reverse=True)

    pending_pos = _sort_date([r for r in records if is_pending_po(r, cfg)], "created_date", False)
    awaiting_po = _sort_date([r for r in records if is_awaiting_po(r, cfg)], "created_date", False)
    eta_late = _sort_date([r for r in records if is_eta_late(r, cfg)], "closed_date", False)
    delivery = Counter(str(r.get("issue") or "Unknown") for r in records)

    return {
        "as_of": t.isoformat(),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sync_token": excel_service.sync_token(),
        "count": len(records),
        "kpis": {
            "suppliers": sum(1 for r in rows if r["name"] != "Unassigned"),
            "unassigned": next((r["total"] for r in rows if r["name"] == "Unassigned"), 0),
            "pending_po": len(pending_pos),
            "awaiting_po": len(awaiting_po),
            "eta_late": len(eta_late),
            "delivered": sum(1 for r in records if is_delivered(r)),
            "open": sum(1 for r in records if is_open(r, cfg)),
        },
        "suppliers": rows,
        "delivery": [
            {"name": name, "value": value, "pct": round(value / max(len(records), 1) * 100, 1)}
            for name, value in delivery.most_common()
        ],
        "pending_pos": _take(pending_pos, cfg, 50),
        "awaiting_po": _take(awaiting_po, cfg, 50),
        "eta_late": _take(eta_late, cfg, 50),
    }


def ops_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    cfg = load_config()
    return {
        "overdue": sum(1 for r in records if is_overdue(r, cfg)),
        "ntp": sum(1 for r in records if is_ntp(r) and is_open(r, cfg)),
        "on_hold": sum(1 for r in records if is_on_hold(r) and is_open(r, cfg)),
        "due_this_week": sum(1 for r in records if is_due_this_week(r, cfg)),
        "created_today": sum(1 for r in records if is_created_today(r)),
        "eta_late": sum(1 for r in records if is_eta_late(r, cfg)),
        "pending_po": sum(1 for r in records if is_pending_po(r, cfg)),
        "awaiting_po": sum(1 for r in records if is_awaiting_po(r, cfg)),
        "suppliers": len({str(r.get("supplier") or "").strip() for r in records if str(r.get("supplier") or "").strip()}),
    }
