from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from .config import AppConfig, default_camp_sites, load_config
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


def site_choices(cfg: Optional[AppConfig] = None) -> list[str]:
    """Known worksheet site labels for filters. All sites is a UI-only option, not a department value."""
    cfg = cfg or load_config()
    names: list[str] = []
    seen: set[str] = set()
    for raw in list((cfg.worksheet_labels or {}).values()) + list(getattr(cfg, "extra_sites", None) or []):
        name = str(raw or "").strip()
        key = name.lower()
        if not name or key in {"all sites", "all"} or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _compact_code(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def camp_site_catalog(cfg: Optional[AppConfig] = None) -> list[dict[str, Any]]:
    """SH5 / SH1 camp sites. They live on the SH5-SH1 worksheet — not extra Excel tabs."""
    cfg = cfg or load_config()
    raw = list(getattr(cfg, "camp_sites", None) or []) or default_camp_sites()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        label = str(item.get("label") or sid).strip()
        if not sid or sid.lower() in seen:
            continue
        seen.add(sid.lower())
        prefixes = [str(p).strip() for p in (item.get("prefixes") or []) if str(p).strip()]
        out.append(
            {
                "id": sid,
                "label": label or sid,
                "group": str(item.get("group") or "").strip(),
                "sheet": str(item.get("sheet") or "SH5-SH1").strip() or "SH5-SH1",
                "prefixes": prefixes or [label or sid],
            }
        )
    return out


def find_camp_site(value: Any, cfg: Optional[AppConfig] = None) -> Optional[dict[str, Any]]:
    text = str(value or "").strip()
    if not text:
        return None
    key = _norm(text)
    compact = _compact_code(text)
    for camp in camp_site_catalog(cfg):
        aliases = [camp["id"], camp["label"], *(camp.get("prefixes") or [])]
        if camp.get("group"):
            aliases.append(f"{camp['group']} {camp['label']}")
        if key in {_norm(a) for a in aliases if a}:
            return camp
        if compact and compact in {_compact_code(a) for a in aliases if a}:
            return camp
    return None


def excel_sheet_alias(site: str, cfg: Optional[AppConfig] = None) -> str:
    """Map a camp / group / label to the Excel worksheet site label. Unknown values pass through."""
    raw = str(site or "").strip()
    if not raw:
        return ""
    camp = find_camp_site(raw, cfg)
    if camp:
        return str(camp.get("sheet") or "SH5-SH1")
    if _norm(raw) in {"sh5", "sh1"}:
        return "SH5-SH1"
    return raw


def apply_site_on_record(data: dict[str, Any], cfg: Optional[AppConfig] = None) -> dict[str, Any]:
    """Keep department as the Excel sheet label; stash camp_site separately."""
    out = dict(data or {})
    camp = find_camp_site(out.get("camp_site"), cfg) or find_camp_site(out.get("department"), cfg)
    if camp:
        out["camp_site"] = camp["id"]
        out["department"] = camp["sheet"]
        out["_site"] = camp["sheet"]
    elif _norm(out.get("department")) in {"sh5", "sh1"}:
        out["department"] = "SH5-SH1"
        out["_site"] = "SH5-SH1"
    return out


def infer_camp_site(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> Optional[dict[str, Any]]:
    cfg = cfg or load_config()
    stored = find_camp_site(rec.get("camp_site"), cfg)
    if stored:
        return stored
    sheet = _norm(rec.get("department") or rec.get("_site") or "")
    if sheet and sheet not in {"sh5-sh1", "sh5", "sh1", ""}:
        return None
    compact = _compact_code(rec.get("location"))
    if not compact:
        return None
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for camp in camp_site_catalog(cfg):
        for prefix in camp.get("prefixes") or []:
            code = _compact_code(prefix)
            if code:
                ranked.append((len(code), code, camp))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    for _n, code, camp in ranked:
        if not compact.startswith(code):
            continue
        rest = compact[len(code) :]
        if rest and rest[0].isdigit():
            continue
        return camp
    return None


def camp_site_of(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> Optional[dict[str, Any]]:
    return infer_camp_site(rec, cfg)


def site_filter_match(rec: dict[str, Any], values: Optional[list[str]], cfg: Optional[AppConfig] = None) -> bool:
    if not values:
        return True
    cfg = cfg or load_config()
    wanted = {_norm(v) for v in values if str(v or "").strip()}
    if not wanted:
        return True
    dept = str(rec.get("department") or rec.get("_site") or "").strip()
    hay = {_norm(dept)} if dept else set()
    camp = camp_site_of(rec, cfg)
    if camp:
        hay.update(
            {
                _norm(camp.get("id")),
                _norm(camp.get("label")),
                _norm(camp.get("group")),
                _norm(f"{camp.get('group')} {camp.get('label')}"),
            }
        )
        hay.update(_norm(p) for p in (camp.get("prefixes") or []) if p)
    for needle in wanted:
        if needle in hay:
            return True
        camp_hit = find_camp_site(needle, cfg)
        if camp_hit and camp and camp_hit.get("id") == camp.get("id"):
            return True
        if needle in {"sh5", "sh1"}:
            if camp and _norm(camp.get("group")) == needle:
                return True
            continue
        if needle == _norm(dept):
            return True
    return False


def filter_site_items(cfg: Optional[AppConfig] = None) -> list[dict[str, Any]]:
    """SiteSwitcher chips: worksheet sites plus SH5 / SH1 camp sites."""
    cfg = cfg or load_config()
    items: list[dict[str, Any]] = [{"id": "", "label": "All sites", "kind": "all", "group": ""}]
    sheets = site_choices(cfg)
    camps = camp_site_catalog(cfg)
    if "SH5-SH1" in sheets:
        items.append({"id": "SH5-SH1", "label": "SH5-SH1", "kind": "sheet", "group": ""})
    groups: list[str] = []
    for camp in camps:
        g = str(camp.get("group") or "").strip()
        if g and g not in groups:
            groups.append(g)
    for group in groups:
        items.append({"id": group, "label": group, "kind": "group", "group": group})
        for camp in camps:
            if camp.get("group") != group:
                continue
            items.append(
                {
                    "id": camp["id"],
                    "label": camp["label"],
                    "kind": "camp",
                    "group": group,
                }
            )
    for name in sheets:
        if name == "SH5-SH1":
            continue
        items.append({"id": name, "label": name, "kind": "sheet", "group": ""})
    return items


def _delay_excluded(rec: dict[str, Any], cfg: AppConfig) -> bool:
    st = _norm(rec.get("status"))
    excluded = status_set(
        list(cfg.closed_statuses or [])
        + list(getattr(cfg, "placed_statuses", None) or ["PLACED"])
        + list(getattr(cfg, "cancelled_statuses", None) or [])
        + list(getattr(cfg, "delay_excluded_statuses", None) or [])
    )
    excluded.update({"close", "closed", "placed", "estimation price", "delivered material inspection"})
    return st in excluded


def is_delayed(rec: dict[str, Any], cfg: Optional[AppConfig] = None, on: Optional[date] = None) -> bool:
    """Delay = OPEN past due date, or PENDING. Closed / placed / estimation / inspection are never delay."""
    cfg = cfg or load_config()
    if _delay_excluded(rec, cfg):
        return False
    st = _norm(rec.get("status"))
    pending = status_set(getattr(cfg, "delay_pending_statuses", None) or ["PENDING"])
    open_vals = status_set(getattr(cfg, "delay_open_statuses", None) or getattr(cfg, "status_open_values", None) or ["OPEN"])
    due = to_date(rec.get("due_date"))
    if st in pending:
        return True
    if st in open_vals:
        if not due:
            return False
        return due < (on or today())
    return False


def is_overdue(rec: dict[str, Any], cfg: Optional[AppConfig] = None, on: Optional[date] = None) -> bool:
    return is_delayed(rec, cfg, on=on)


def is_ntp(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    return "ntp" in _norm(rec.get("status"))


def is_on_hold(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    return "hold" in _norm(rec.get("status"))


def is_delivered(rec: dict[str, Any]) -> bool:
    return _norm(rec.get("issue") or rec.get("delay_reason")) == "delivered"


def is_waiting_supplier(rec: dict[str, Any], cfg: Optional[AppConfig] = None) -> bool:
    """Open MR still with a supplier (or delay source = supplier), not delivered."""
    if is_closed(rec, cfg) or is_delivered(rec):
        return False
    if _norm(rec.get("delay_source")) == "supplier":
        return True
    return bool(str(rec.get("supplier") or "").strip()) and is_open(rec, cfg)


def _tokens(text: Any) -> set[str]:
    import re

    return {t for t in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(t) > 2}


def similar_open_pairs(records: list[dict[str, Any]], cfg: Optional[AppConfig] = None, limit: int = 40) -> list[dict[str, Any]]:
    """Open MRs on the same asset with similar material text. No invented scores beyond overlap."""
    from collections import defaultdict
    from difflib import SequenceMatcher

    cfg = cfg or load_config()
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        if not is_open(rec, cfg):
            continue
        asset = str(rec.get("location") or "").strip()
        if not asset:
            continue
        desc = str(rec.get("description") or "").strip()
        if not desc:
            continue
        groups[asset.lower()].append(rec)
    pairs: list[dict[str, Any]] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        for i, a in enumerate(group):
            ta = _tokens(a.get("description"))
            da = str(a.get("description") or "").lower()
            if not ta:
                continue
            for b in group[i + 1 :]:
                if str(a.get("record_id")) == str(b.get("record_id")):
                    continue
                tb = _tokens(b.get("description"))
                db = str(b.get("description") or "").lower()
                if not tb:
                    continue
                inter = len(ta & tb)
                union = len(ta | tb) or 1
                overlap = inter / union
                seq = SequenceMatcher(None, da, db).ratio()
                score = max(overlap, seq)
                if not ((inter >= 2 and overlap >= 0.35) or seq >= 0.55):
                    continue
                pairs.append(
                    {
                        "asset": a.get("location") or b.get("location"),
                        "score": round(score, 2),
                        "a": {
                            "record_id": a.get("record_id"),
                            "work_order_id": a.get("work_order_id"),
                            "description": a.get("description"),
                            "assigned_to": a.get("assigned_to"),
                            "status": a.get("status"),
                            "department": a.get("department"),
                        },
                        "b": {
                            "record_id": b.get("record_id"),
                            "work_order_id": b.get("work_order_id"),
                            "description": b.get("description"),
                            "assigned_to": b.get("assigned_to"),
                            "status": b.get("status"),
                            "department": b.get("department"),
                        },
                    }
                )
    pairs.sort(key=lambda x: (-float(x.get("score") or 0), str(x.get("asset") or "")))
    return pairs[: max(1, min(int(limit or 40), 80))]


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
    if not site_filter_match(rec, filters.get("department"), cfg):
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
    if flag == "delayed" and not is_delayed(rec, cfg):
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
                "camp_site",
            )
        ).lower()
        camp = camp_site_of(rec, cfg)
        if camp:
            hay += " " + " ".join(
                str(x or "")
                for x in (
                    camp.get("id"),
                    camp.get("label"),
                    camp.get("group"),
                    f"{camp.get('group')} {camp.get('label')}",
                    *(camp.get("prefixes") or []),
                )
            ).lower()
        if q not in hay and not site_filter_match(rec, [q], cfg):
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
    out["is_delayed"] = out["is_overdue"]
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
    camp = camp_site_of(rec, cfg)
    out["camp_site"] = camp["id"] if camp else str(rec.get("camp_site") or "")
    out["camp_site_label"] = camp["label"] if camp else ""
    out["site_group"] = camp["group"] if camp else ""
    out["site_display"] = camp["label"] if camp else str(rec.get("department") or "")
    return out
