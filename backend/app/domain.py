from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from .config import AppConfig, load_config
from .dates import days_between, parse_date, quarter_of, to_date, week_bounds

TODAY_OVERRIDE: Optional[date] = None  # used in tests


def today() -> date:
    return TODAY_OVERRIDE or date.today()


def now() -> datetime:
    if TODAY_OVERRIDE:
        return datetime(TODAY_OVERRIDE.year, TODAY_OVERRIDE.month, TODAY_OVERRIDE.day, 12, 0)
    return datetime.now()


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def status_set(values: list[str]) -> set[str]:
    return {_norm(v) for v in values}


def is_closed(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    cfg = cfg or load_config()
    return _norm(rec.get("status")) in status_set(cfg.closed_statuses)


def is_cancelled(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    cfg = cfg or load_config()
    return _norm(rec.get("status")) in status_set(cfg.cancelled_statuses)


def is_pending(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    cfg = cfg or load_config()
    return _norm(rec.get("status")) in status_set(cfg.pending_statuses)


def is_in_progress(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    cfg = cfg or load_config()
    return _norm(rec.get("status")) in status_set(cfg.in_progress_statuses)


def is_open(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    """Still outstanding: anything that is not CLOSED (includes PLACED, NTP, hold)."""
    return not is_closed(rec, cfg)


def is_status_open(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    """Excel STATUS is OPEN — used for the Open KPI and /open page."""
    cfg = cfg or load_config()
    values = getattr(cfg, "status_open_values", None) or ["OPEN"]
    return _norm(rec.get("status")) in status_set(values)


def is_placed(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    cfg = cfg or load_config()
    values = getattr(cfg, "placed_statuses", None) or ["PLACED"]
    return _norm(rec.get("status")) in status_set(values)


def is_overdue(rec: dict[str, Any], cfg: Optional[AppConfig] = None, on: Optional[date] = None) -> bool:
    if is_closed(rec, cfg):
        return False
    due = to_date(rec.get("due_date"))
    if not due:
        return False
    return due < (on or today())


def is_ntp(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    return "ntp" in _norm(rec.get("status"))


def is_on_hold(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    return "hold" in _norm(rec.get("status"))


def is_delivered(rec: dict[str, Any]) -> bool:
    return _norm(rec.get("issue") or rec.get("delay_reason")) == "delivered"


def has_po(rec: dict[str, Any]) -> bool:
    return bool(str(rec.get("po_number") or "").strip())


def is_pending_po(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    return is_open(rec, cfg) and has_po(rec) and not is_delivered(rec)


def is_awaiting_po(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    return is_open(rec, cfg) and not has_po(rec) and not is_delivered(rec)


def has_rfq_date(rec: dict[str, Any]) -> bool:
    return bool(to_date(rec.get("scheduled_date")) or str(rec.get("scheduled_date") or "").strip())


def is_need_rfq(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    return is_awaiting_po(rec, cfg) and not has_rfq_date(rec)


def is_rfq_sent(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    return is_awaiting_po(rec, cfg) and has_rfq_date(rec)


def is_po_issued(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    return is_pending_po(rec, cfg) and not is_eta_late(rec, cfg)


def delivery_done_date(rec: dict[str, Any]) -> Optional[date]:
    return to_date(rec.get("completion_date")) or to_date(rec.get("scheduled_date"))


def is_on_time_delivery(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> Optional[bool]:
    """Scorable delivered/closed rows vs due date. None = not enough dates to score."""
    if not is_delivered(rec) and not is_closed(rec, cfg):
        return None
    due = to_date(rec.get("due_date"))
    done = to_date(rec.get("completion_date"))
    if done and due:
        return done <= due
    if is_delivered(rec) and due:
        return due >= today() or not is_overdue(rec, cfg)
    return None


def po_stage(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> str:
    """Exclusive pipeline stage for the PO board (derived, not stored)."""
    if is_delivered(rec):
        return "delivered"
    if is_closed(rec, cfg):
        return "closed"
    if is_eta_late(rec, cfg):
        return "eta_late"
    if is_pending_po(rec, cfg):
        return "po_issued"
    if is_rfq_sent(rec, cfg):
        return "rfq_sent"
    if is_need_rfq(rec, cfg):
        return "need_rfq"
    return "other"


def eta_date(rec: dict[str, Any]) -> Optional[date]:
    return to_date(rec.get("closed_date"))


def is_eta_late(rec: dict[str, Any], cfg: Optional[AppConfig] = None, on: Optional[date] = None) -> bool:
    if is_closed(rec, cfg) or is_delivered(rec):
        return False
    eta = eta_date(rec)
    if not eta:
        return False
    return eta < (on or today())


def is_due_this_week(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    if is_closed(rec, cfg):
        return False
    due = to_date(rec.get("due_date"))
    if not due:
        return False
    t = today()
    iso = t.isocalendar()
    start, end = week_bounds(int(iso[0]), int(iso[1]))
    return t <= due <= end.date()


def days_until_due(rec: dict[str, Any], on: Optional[date] = None) -> Optional[int]:
    due = to_date(rec.get("due_date"))
    if not due:
        return None
    return (due - (on or today())).days


def is_due_soon(rec: dict[str, Any], cfg: Optional[AppConfig] = None, on: Optional[date] = None) -> bool:
    """Open MRs whose due date is today through due_soon_days (default 3)."""
    if is_closed(rec, cfg):
        return False
    days = days_until_due(rec, on=on)
    if days is None:
        return False
    cfg = cfg or load_config()
    try:
        window = int(getattr(cfg, "due_soon_days", 3) or 3)
    except (TypeError, ValueError):
        window = 3
    return 0 <= days <= max(0, window)


def is_created_today(rec: dict[str, Any]) -> bool:
    return to_date(rec.get("created_date")) == today()


def aging_days(rec: dict[str, Any], on: Optional[date] = None) -> Optional[int]:
    created = to_date(rec.get("created_date"))
    if not created:
        return None
    return ((on or today()) - created).days


def closing_days(rec: dict[str, Any]) -> Optional[float]:
    closed = rec.get("closed_date") or rec.get("completion_date")
    return days_between(rec.get("created_date"), closed)


def delay_days(rec: dict[str, Any]) -> Optional[float]:
    """Positive means closed after due date."""
    closed = rec.get("closed_date") or rec.get("completion_date")
    return days_between(rec.get("due_date"), closed)


def reason_for_open(rec: dict[str, Any]) -> str:
    st = str(rec.get("status") or "").strip()
    if st and _norm(st) not in status_set(load_config().closed_statuses):
        delivery = str(rec.get("delay_reason") or rec.get("issue") or "").strip()
        if delivery and _norm(delivery) not in {"delivered", ""}:
            return f"{st} — {delivery}"
        return st
    for key in ("delay_reason", "issue"):
        v = str(rec.get(key) or "").strip()
        if v:
            return v
    return "No reason specified"


def matches_filters(rec: dict[str, Any], filters: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    cfg = cfg or load_config()

    def in_list(field: str, values: Optional[list[str]]) -> bool:
        if not values:
            return True
        current = str(rec.get(field) or "")
        return current in values or _norm(current) in {_norm(v) for v in values}

    if not in_list("status", filters.get("status")):
        return False
    if not in_list("priority", filters.get("priority")):
        return False
    if not in_list("department", filters.get("department")):
        return False
    if not in_list("location", filters.get("location")):
        return False
    if not in_list("assigned_to", filters.get("assigned_to")):
        return False
    if not in_list("work_type", filters.get("work_type")):
        return False
    if not in_list("delay_reason", filters.get("delay_reason")):
        return False
    if not in_list("supplier", filters.get("supplier")):
        return False
    if not in_list("issue", filters.get("issue")):
        return False

    bucket = filters.get("aging")
    if bucket:
        days = aging_days(rec)
        if days is None or not _in_bucket(days, bucket, cfg):
            return False

    aging_min = filters.get("aging_min")
    if aging_min not in (None, ""):
        try:
            min_days = int(aging_min)
        except (TypeError, ValueError):
            min_days = None
        if min_days is not None:
            days = aging_days(rec)
            if days is None or days < min_days:
                return False

    flag = filters.get("flag")
    if flag == "open" and not is_status_open(rec, cfg):
        return False
    if flag == "placed" and not is_placed(rec, cfg):
        return False
    if flag == "outstanding" and not is_open(rec, cfg):
        return False
    if flag == "closed" and not is_closed(rec, cfg):
        return False
    if flag == "overdue" and not is_overdue(rec, cfg):
        return False
    if flag == "pending" and not is_pending(rec, cfg):
        return False
    if flag == "in_progress" and not is_in_progress(rec, cfg):
        return False
    if flag == "cancelled" and not is_cancelled(rec, cfg):
        return False
    if flag == "ntp" and not is_ntp(rec, cfg):
        return False
    if flag == "on_hold" and not is_on_hold(rec, cfg):
        return False
    if flag == "due_week" and not is_due_this_week(rec, cfg):
        return False
    if flag == "due_soon" and not is_due_soon(rec, cfg):
        return False
    if flag == "eta_late" and not is_eta_late(rec, cfg):
        return False
    if flag == "pending_po" and not is_pending_po(rec, cfg):
        return False
    if flag == "awaiting_po" and not is_awaiting_po(rec, cfg):
        return False
    if flag == "need_rfq" and not is_need_rfq(rec, cfg):
        return False
    if flag == "rfq_sent" and not is_rfq_sent(rec, cfg):
        return False
    if flag == "po_issued" and not is_po_issued(rec, cfg):
        return False
    if flag == "delivered" and not is_delivered(rec):
        return False
    if flag == "created_today" and not is_created_today(rec):
        return False

    q = (filters.get("q") or "").strip().lower()
    if q:
        hay = " ".join(
            str(rec.get(k) or "")
            for k in (
                "work_order_id",
                "record_id",
                "description",
                "assigned_to",
                "department",
                "location",
                "status",
                "issue",
                "delay_reason",
                "remarks",
                "priority",
                "work_type",
                "supplier",
                "po_number",
                "delay_kind",
                "delay_source",
                "delay_justification",
            )
        ).lower()
        if q not in hay:
            return False

    start, end = date_window(filters)
    if start or end:
        created = to_date(rec.get("created_date"))
        if not created:
            return False
        if start and created < start:
            return False
        if end and created > end:
            return False
    return True


def _in_bucket(days: int, bucket_id: str, cfg: AppConfig) -> bool:
    for b in cfg.aging_buckets:
        if b["id"] == bucket_id:
            if days < b["min"]:
                return False
            if b["max"] is None:
                return True
            return days <= b["max"]
    return False


def date_window(filters: dict[str, Any]) -> tuple[Optional[date], Optional[date]]:
    preset = (filters.get("period") or "").lower()
    t = today()
    if filters.get("date_from") or filters.get("date_to"):
        start = to_date(filters.get("date_from"))
        end = to_date(filters.get("date_to"))
        return start, end
    if preset in {"today"}:
        return t, t
    if preset in {"yesterday"}:
        y = t - timedelta(days=1)
        return y, y
    if preset in {"this_week", "week"}:
        start = t - timedelta(days=t.weekday())
        return start, t
    if preset in {"last_week"}:
        start = t - timedelta(days=t.weekday() + 7)
        end = start + timedelta(days=6)
        return start, end
    if preset in {"this_month", "month"}:
        return t.replace(day=1), t
    if preset in {"last_month"}:
        first = t.replace(day=1)
        end = first - timedelta(days=1)
        start = end.replace(day=1)
        return start, end
    if preset in {"this_quarter", "quarter"}:
        q = (t.month - 1) // 3
        start = date(t.year, q * 3 + 1, 1)
        return start, t
    if preset in {"this_year", "year"}:
        return date(t.year, 1, 1), t
    if preset in {"last_year"}:
        return date(t.year - 1, 1, 1), date(t.year - 1, 12, 31)
    if filters.get("year"):
        y = int(filters["year"])
        month = filters.get("month")
        week = filters.get("week")
        if week:
            start_dt, end_dt = week_bounds(y, int(week))
            return start_dt.date(), end_dt.date()
        if month:
            m = int(month)
            start = date(y, m, 1)
            if m == 12:
                end = date(y, 12, 31)
            else:
                end = date(y, m + 1, 1) - timedelta(days=1)
            return start, end
        return date(y, 1, 1), date(y, 12, 31)
    return None, None


def annotate(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    out = dict(rec)
    out.pop("_raw", None)
    out["is_closed"] = is_closed(rec, cfg)
    out["is_open"] = is_open(rec, cfg)
    out["is_status_open"] = is_status_open(rec, cfg)
    out["is_placed"] = is_placed(rec, cfg)
    out["is_overdue"] = is_overdue(rec, cfg)
    out["is_pending"] = is_pending(rec, cfg)
    out["is_in_progress"] = is_in_progress(rec, cfg)
    out["aging_days"] = aging_days(rec)
    out["closing_days"] = closing_days(rec)
    out["days_overdue"] = None
    if out["is_overdue"]:
        due = to_date(rec.get("due_date"))
        if due:
            out["days_overdue"] = (today() - due).days
    out["open_reason"] = reason_for_open(rec) if out["is_open"] else ""
    out["is_ntp"] = is_ntp(rec, cfg)
    out["is_on_hold"] = is_on_hold(rec, cfg)
    out["is_delivered"] = is_delivered(rec)
    out["is_pending_po"] = is_pending_po(rec, cfg)
    out["is_awaiting_po"] = is_awaiting_po(rec, cfg)
    out["is_need_rfq"] = is_need_rfq(rec, cfg)
    out["is_rfq_sent"] = is_rfq_sent(rec, cfg)
    out["is_po_issued"] = is_po_issued(rec, cfg)
    out["is_eta_late"] = is_eta_late(rec, cfg)
    out["is_due_this_week"] = is_due_this_week(rec, cfg)
    out["is_due_soon"] = is_due_soon(rec, cfg)
    out["days_until_due"] = days_until_due(rec)
    out["on_time"] = is_on_time_delivery(rec, cfg)
    out["po_stage"] = po_stage(rec, cfg)
    eta = eta_date(rec)
    out["days_to_eta"] = (eta - today()).days if eta else None
    return out
