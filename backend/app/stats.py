from __future__ import annotations

import json
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any, Optional

from .config import load_config
from .dates import parse_date, quarter_of, to_date, week_bounds
from .domain import (
    aging_days,
    annotate,
    canonical_priority,
    closing_days,
    filter_site_items,
    is_blockade,
    is_closed,
    is_in_progress,
    is_open,
    is_overdue,
    is_pending,
    is_placed,
    is_status_open,
    matches_filters,
    reason_for_open,
    site_choices,
    site_filter_match,
    today,
)
from .excel.service import excel_service
from .ops import ops_counts

_DASH_LOCK = threading.Lock()
_DASH_CACHE: dict[str, Any] = {"token": "", "key": "", "payload": None}


def filtered(records: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = load_config()
    return [r for r in records if matches_filters(r, filters, cfg)]


def kpis(records: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = load_config()
    total = len(records)
    closed = [r for r in records if is_closed(r, cfg)]
    open_ = [r for r in records if is_status_open(r, cfg)]
    placed = [r for r in records if is_placed(r, cfg)]
    outstanding = [r for r in records if is_open(r, cfg)]
    overdue = [r for r in records if is_overdue(r, cfg)]
    pending = [r for r in records if is_pending(r, cfg)]
    in_prog = [r for r in records if is_in_progress(r, cfg)]
    closing = [closing_days(r) for r in closed]
    closing = [c for c in closing if c is not None]
    aging = [aging_days(r) for r in outstanding]
    aging = [a for a in aging if a is not None]
    t = today()
    created_today = [r for r in records if to_date(r.get("created_date")) == t]
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
    delivered_today = [
        r
        for r in records
        if str(r.get("issue") or "").strip().lower() == "delivered"
        and (
            to_date(r.get("closed_date")) == t
            or to_date(r.get("scheduled_date")) == t
            or to_date(r.get("completion_date")) == t
        )
    ]
    blockades = [r for r in records if is_blockade(r, cfg)]
    return {
        "total": total,
        "open": len(open_),
        "placed": len(placed),
        "outstanding": len(outstanding),
        "closed": len(closed),
        "pending": len(pending),
        "overdue": len(overdue),
        "in_progress": len(in_prog),
        "completion_rate": round((len(closed) / total * 100) if total else 0, 1),
        "average_closing_days": round(mean(closing), 1) if closing else None,
        "average_aging_days": round(mean(aging), 1) if aging else None,
        "oldest_open_days": max(aging) if aging else 0,
        "created_today": len(created_today),
        "done_today": len(done_today),
        "delivered_today": len(delivered_today),
        "blockades": len(blockades),
        "progress_open": round((len(in_prog) / len(outstanding) * 100) if outstanding else 0, 1),
    }


def invalidate_dash_cache() -> None:
    with _DASH_LOCK:
        _DASH_CACHE["payload"] = None
        _DASH_CACHE["token"] = ""
        _DASH_CACHE["key"] = ""


def today_activity(records: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = load_config()
    t = today()
    created = [r for r in records if to_date(r.get("created_date")) == t]
    done = [
        r
        for r in records
        if is_closed(r, cfg)
        and (
            to_date(r.get("closed_date")) == t
            or to_date(r.get("completion_date")) == t
            or to_date(r.get("scheduled_date")) == t
        )
    ]
    return {
        "date": t.isoformat(),
        "created": len(created),
        "done": len(done),
        "created_items": [annotate(r, cfg) for r in created[:25]],
        "done_items": [annotate(r, cfg) for r in done[:25]],
    }


def blockades(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cfg = load_config()
    stuck = [r for r in records if is_blockade(r, cfg)]
    counts = Counter()
    for r in stuck:
        st = str(r.get("status") or "").strip() or "Unknown"
        counts[st] += 1
    total = len(stuck) or 1
    out = []
    for name, value in counts.most_common():
        out.append({"name": name, "value": value, "pct": round(value / total * 100, 1)})
    return out


def last_days(records: list[dict[str, Any]], n: int = 14) -> list[dict[str, Any]]:
    cfg = load_config()
    t = today()
    points = []
    for i in range(n - 1, -1, -1):
        day = t - timedelta(days=i)
        created = [r for r in records if to_date(r.get("created_date")) == day]
        closed = [
            r
            for r in records
            if is_closed(r, cfg)
            and (
                to_date(r.get("closed_date")) == day
                or to_date(r.get("completion_date")) == day
                or to_date(r.get("scheduled_date")) == day
            )
        ]
        points.append(
            {
                "name": day.strftime("%d %b"),
                "date": day.isoformat(),
                "created": len(created),
                "done": len(closed),
            }
        )
    return points


def status_distribution(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(r.get("status") or "Unknown") for r in records)
    total = sum(counts.values()) or 1
    return [{"name": k, "value": v, "pct": round(v / total * 100, 1)} for k, v in counts.most_common()]


def reasons(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cfg = load_config()
    open_recs = [r for r in records if is_open(r, cfg)]
    counts = Counter(reason_for_open(r) for r in open_recs)
    total = len(open_recs) or 1
    out = []
    for name, value in counts.most_common():
        out.append({"name": name, "value": value, "pct": round(value / total * 100, 1)})
    return out


def aging(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cfg = load_config()
    open_recs = [r for r in records if is_open(r, cfg)]
    buckets = []
    for b in cfg.aging_buckets:
        n = 0
        for r in open_recs:
            d = aging_days(r)
            if d is None:
                continue
            if d < b["min"]:
                continue
            if b["max"] is None or d <= b["max"]:
                n += 1
        buckets.append({"id": b["id"], "name": b["label"], "value": n})
    return buckets


def group_by(records: list[dict[str, Any]], field: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
    cfg = load_config()
    groups: dict[str, list] = defaultdict(list)
    for r in records:
        if field == "priority":
            key = canonical_priority(r.get(field)) or "Unassigned"
        else:
            key = str(r.get(field) or "Unassigned")
        groups[key].append(r)
    rows = []
    for name, recs in groups.items():
        closed = [r for r in recs if is_closed(r, cfg)]
        open_ = [r for r in recs if is_open(r, cfg)]
        overdue = [r for r in recs if is_overdue(r, cfg)]
        closing = [closing_days(r) for r in closed]
        closing = [c for c in closing if c is not None]
        rows.append(
            {
                "name": name,
                "total": len(recs),
                "open": len(open_),
                "closed": len(closed),
                "overdue": len(overdue),
                "completion_rate": round((len(closed) / len(recs) * 100) if recs else 0, 1),
                "average_closing_days": round(mean(closing), 1) if closing else None,
            }
        )
    rows.sort(key=lambda x: x["total"], reverse=True)
    if limit:
        rows = rows[:limit]
    return rows


def employee_performance(records: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = load_config()
    groups: dict[str, list] = defaultdict(list)
    for rec in records:
        groups[str(rec.get("assigned_to") or "Unassigned")].append(rec)
    rows = []
    for name, recs in groups.items():
        closed = [r for r in recs if is_closed(r, cfg)]
        open_ = [r for r in recs if is_open(r, cfg)]
        overdue = [r for r in recs if is_overdue(r, cfg)]
        placed = [r for r in recs if is_placed(r, cfg)]
        pending = [r for r in recs if is_pending(r, cfg)]
        closing = [c for c in (closing_days(r) for r in closed) if c is not None]
        aging = [a for a in (aging_days(r) for r in open_) if a is not None]
        rows.append(
            {
                "name": name,
                "total": len(recs),
                "open": len([r for r in recs if is_status_open(r, cfg)]),
                "outstanding": len(open_),
                "placed": len(placed),
                "pending": len(pending),
                "closed": len(closed),
                "overdue": len(overdue),
                "completion_rate": round((len(closed) / len(recs) * 100) if recs else 0, 1),
                "average_closing_days": round(mean(closing), 1) if closing else None,
                "average_aging_days": round(mean(aging), 1) if aging else None,
                "oldest_open_days": max(aging) if aging else 0,
            }
        )
    rows.sort(key=lambda x: (-x["overdue"], -x["outstanding"], x["name"].lower()))
    return {
        "employees": rows,
        "kpis": kpis(records),
        "workload": [
            {
                "name": r["name"],
                "open": r["open"],
                "placed": r["placed"],
                "closed": r["closed"],
                "overdue": r["overdue"],
                "outstanding": r["outstanding"],
            }
            for r in rows[:30]
        ],
        "completion": [{"name": r["name"], "completion_rate": r["completion_rate"]} for r in rows[:30]],
    }


def weekly(records: list[dict[str, Any]], year: int, week: int) -> dict[str, Any]:
    cfg = load_config()
    start, end = week_bounds(year, week)
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    series = []
    for i, name in enumerate(days):
        day = (start + timedelta(days=i)).date()
        created = [r for r in records if to_date(r.get("created_date")) == day]
        completed = [
            r
            for r in records
            if to_date(r.get("completion_date")) == day or to_date(r.get("closed_date")) == day
        ]
        closed = [r for r in records if is_closed(r, cfg) and to_date(r.get("closed_date") or r.get("completion_date")) == day]
        still_open = [
            r
            for r in records
            if is_open(r, cfg)
            and to_date(r.get("created_date")) is not None
            and to_date(r.get("created_date")) <= day
        ]
        overdue = [r for r in still_open if is_overdue(r, cfg, on=day)]
        series.append(
            {
                "name": name,
                "date": day.isoformat(),
                "created": len(created),
                "completed": len(completed),
                "closed": len(closed),
                "open": len(still_open),
                "overdue": len(overdue),
            }
        )
    return {
        "year": year,
        "week": week,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "label": f"Week {week} — {year}",
        "days": series,
        "kpis": kpis(
            [
                r
                for r in records
                if (d := to_date(r.get("created_date"))) and start.date() <= d <= end.date()
            ]
        ),
    }


def monthly(records: list[dict[str, Any]], year: int) -> dict[str, Any]:
    cfg = load_config()
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    series = []
    for m, name in enumerate(months, 1):
        created = [r for r in records if (d := parse_date(r.get("created_date"))) and d.year == year and d.month == m]
        completed = [
            r
            for r in records
            if (d := parse_date(r.get("completion_date") or r.get("closed_date")))
            and d.year == year
            and d.month == m
        ]
        closed = [
            r
            for r in records
            if is_closed(r, cfg)
            and (d := parse_date(r.get("closed_date") or r.get("completion_date")))
            and d.year == year
            and d.month == m
        ]
        # snapshot: still open at end of month (created in or before month, not closed by month end)
        if m == 12:
            month_end = date(year, 12, 31)
        else:
            month_end = date(year, m + 1, 1) - timedelta(days=1)
        open_snap = []
        overdue_snap = []
        for r in records:
            created_d = to_date(r.get("created_date"))
            if not created_d or created_d > month_end:
                continue
            closed_d = to_date(r.get("closed_date") or r.get("completion_date"))
            if closed_d and closed_d <= month_end and is_closed(r, cfg):
                continue
            # if currently closed after month_end, it was open at month end
            if closed_d and closed_d > month_end:
                open_snap.append(r)
            elif is_open(r, cfg):
                open_snap.append(r)
            due = to_date(r.get("due_date"))
            if due and due < month_end:
                if not closed_d or closed_d > month_end:
                    overdue_snap.append(r)
        total = len(created)
        series.append(
            {
                "name": name[:3],
                "full": name,
                "month": m,
                "created": total,
                "completed": len(completed),
                "closed": len(closed),
                "open": len(open_snap),
                "overdue": len(overdue_snap),
                "completion_rate": round((len(closed) / total * 100) if total else 0, 1),
            }
        )
    year_recs = [r for r in records if (d := parse_date(r.get("created_date"))) and d.year == year]
    return {"year": year, "months": series, "kpis": kpis(year_recs)}


def yearly(records: list[dict[str, Any]]) -> dict[str, Any]:
    years = sorted(
        {
            parse_date(r.get("created_date")).year
            for r in records
            if parse_date(r.get("created_date"))
        }
    )
    if not years:
        years = [today().year]
    series = []
    prev = None
    for y in years:
        recs = [r for r in records if (d := parse_date(r.get("created_date"))) and d.year == y]
        k = kpis(recs)
        yoy = None
        if prev:
            yoy = {
                "total": _delta(prev["total"], k["total"]),
                "closed": _delta(prev["closed"], k["closed"]),
                "completion_rate": round(k["completion_rate"] - prev["completion_rate"], 1),
            }
        series.append({"year": y, **k, "yoy": yoy})
        prev = k
    return {"years": series}


def _delta(old: int, new: int) -> dict[str, Any]:
    change = new - old
    pct = round((change / old * 100) if old else 0, 1)
    return {"change": change, "pct": pct}


def trend(records: list[dict[str, Any]], months: int = 12) -> list[dict[str, Any]]:
    cfg = load_config()
    t = today()
    points = []
    for i in range(months - 1, -1, -1):
        y = t.year
        m = t.month - i
        while m <= 0:
            m += 12
            y -= 1
        created = [r for r in records if (d := parse_date(r.get("created_date"))) and d.year == y and d.month == m]
        closed = [
            r
            for r in records
            if is_closed(r, cfg)
            and (d := parse_date(r.get("closed_date") or r.get("completion_date")))
            and d.year == y
            and d.month == m
        ]
        points.append(
            {
                "name": f"{y}-{m:02d}",
                "created": len(created),
                "closed": len(closed),
                "open": len([r for r in created if is_open(r, cfg)]),
            }
        )
    return points


def _mm_children_from_rows(rows: list[dict[str, Any]], filter_key: str, limit: int = 12) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        fid = r.get("id") or r["name"]
        out.append(
            {
                "id": f"{filter_key}:{fid}",
                "label": r["name"],
                "value": r["total"],
                "open": r["open"],
                "closed": r["closed"],
                "filter": {filter_key: fid},
            }
        )
    return out


def group_by_sites(records: list[dict[str, Any]], cfg=None) -> list[dict[str, Any]]:
    """One row per worksheet / SH5-SH1 camp, same identities as SiteSwitcher chips.

    Single pass: each record's site hay-stack and status flags are computed once
    (the old per-site×per-record matching re-derived both ~21×2193 times and
    dominated dashboard load time). Match semantics identical to
    site_filter_match(rec, [sid])."""
    cfg = cfg or load_config()
    items = [i for i in filter_site_items(cfg) if str(i.get("id") or "").strip()]
    if not items or not records:
        return []
    from .domain import camp_site_of, find_camp_site

    def _normv(v: Any) -> str:
        return str(v or "").strip().lower()

    # Per-site precomputed matchers (one pass over ~21 sites, not per record).
    site_matchers = []
    for item in items:
        sid = str(item.get("id") or "").strip()
        needle = _normv(sid)
        site_camp = find_camp_site(sid, cfg)
        site_camp_id = str((site_camp or {}).get("id") or "")
        site_matchers.append((item, sid, needle, site_camp_id))

    counters = {
        sid: {"total": 0, "open": 0, "closed": 0, "overdue": 0}
        for _item, sid, _n, _c in site_matchers
    }
    for rec in records:
        dept = str(rec.get("department") or rec.get("_site") or "").strip()
        hay = {_normv(dept)} if dept else set()
        camp = camp_site_of(rec, cfg)
        camp_id = str((camp or {}).get("id") or "")
        if camp:
            hay.update(
                {
                    _normv(camp.get("id")),
                    _normv(camp.get("label")),
                    _normv(camp.get("group")),
                    _normv(f"{camp.get('group')} {camp.get('label')}"),
                }
            )
            hay.update(_normv(p) for p in (camp.get("prefixes") or []) if p)
        rec_open = is_open(rec, cfg)
        rec_closed = is_closed(rec, cfg)
        rec_overdue = is_overdue(rec, cfg)
        for item, sid, needle, site_camp_id in site_matchers:
            hit = needle in hay or (site_camp_id and site_camp_id == camp_id)
            if not hit and needle in {"sh5", "sh1"} and camp and _normv(camp.get("group")) == needle:
                hit = True
            if not hit and needle == _normv(dept):
                hit = True
            if hit:
                c = counters[sid]
                c["total"] += 1
                if rec_open:
                    c["open"] += 1
                if rec_closed:
                    c["closed"] += 1
                if rec_overdue:
                    c["overdue"] += 1
    rows: list[dict[str, Any]] = []
    for item, sid, _needle, _sc in site_matchers:
        c = counters[sid]
        if not c["total"]:
            continue
        rows.append(
            {
                "id": sid,
                "name": item.get("label") or sid,
                "kind": item.get("kind") or "sheet",
                "group": item.get("group") or "",
                "total": c["total"],
                "open": c["open"],
                "closed": c["closed"],
                "overdue": c["overdue"],
                "completion_rate": round((c["closed"] / c["total"] * 100) if c["total"] else 0, 1),
            }
        )
    return rows


def _mm_site_nodes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for r in rows:
        fid = r.get("id") or r["name"]
        node: dict[str, Any] = {
            "id": f"department:{fid}",
            "label": r["name"],
            "value": r["total"],
            "open": r.get("open"),
            "closed": r.get("closed"),
            "filter": {"department": fid},
        }
        if r.get("kind") == "group":
            node["children"] = [
                {
                    "id": f"department:{x.get('id') or x['name']}",
                    "label": x["name"],
                    "value": x["total"],
                    "open": x.get("open"),
                    "closed": x.get("closed"),
                    "filter": {"department": x.get("id") or x["name"]},
                }
                for x in rows
                if x.get("kind") == "camp" and x.get("group") == fid
            ]
        elif r.get("kind") == "sheet" and fid == "SH5-SH1":
            node["children"] = [
                {
                    "id": f"department:{x.get('id') or x['name']}",
                    "label": x["name"],
                    "value": x["total"],
                    "open": x.get("open"),
                    "closed": x.get("closed"),
                    "filter": {"department": x.get("id") or x["name"]},
                }
                for x in rows
                if x.get("kind") == "group"
            ]
        nodes.append(node)
    return nodes


def mindmap(
    records: list[dict[str, Any]],
    k: Optional[dict[str, Any]] = None,
    groups: Optional[dict[str, list]] = None,
    blockade_rows: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    k = k or kpis(records)
    groups = groups or {}
    blockade_rows = blockade_rows if blockade_rows is not None else blockades(records)
    site_rows = groups.get("department") or []
    if not site_rows or not any(r.get("kind") in {"camp", "group"} for r in site_rows):
        site_rows = group_by_sites(records)
    return {
        "root": {
            "id": "all",
            "label": "All material requests",
            "value": k["total"],
            "filter": {},
        },
        "branches": [
            {
                "id": "sites",
                "label": "Sites",
                "value": k["total"],
                "filter": {},
                "children": _mm_site_nodes(site_rows),
            },
            {
                "id": "status",
                "label": "Status",
                "value": k["total"],
                "filter": {},
                "children": _mm_children_from_rows(groups.get("status") or [], "status"),
            },
            {
                "id": "blockades",
                "label": "Blockades",
                "value": k["blockades"],
                "filter": {"flag": "blockade"},
                "children": [
                    {"id": f"st:{b['name']}", "label": b["name"], "value": b["value"], "filter": {"flag": "blockade", "status": b["name"]}}
                    for b in blockade_rows
                ],
            },
            {
                "id": "people",
                "label": "Assigned to",
                "value": len(groups.get("assigned_to") or []),
                "filter": {},
                "children": _mm_children_from_rows(groups.get("assigned_to") or [], "assigned_to"),
            },
            {
                "id": "delivery",
                "label": "Delivery",
                "value": k["total"],
                "filter": {},
                "children": _mm_children_from_rows(groups.get("delay_reason") or groups.get("issue") or [], "delay_reason"),
            },
            {
                "id": "priority",
                "label": "Priority",
                "value": k["total"],
                "filter": {},
                "children": _mm_children_from_rows(groups.get("priority") or [], "priority"),
            },
        ],
    }


def _filter_key(filters: dict[str, Any]) -> str:
    return json.dumps(filters or {}, sort_keys=True, default=str)


def _options_from(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    fields = ["status", "priority", "department", "location", "assigned_to", "work_type", "delay_reason", "issue", "supplier"]
    out: dict[str, list[str]] = {}
    for field in fields:
        if field == "priority":
            vals = {canonical_priority(r.get(field)) for r in records if str(r.get(field) or "").strip()}
            vals.discard("")
        else:
            vals = {str(r.get(field)).strip() for r in records if str(r.get(field) or "").strip()}
        out[field] = sorted(vals, key=str.lower)
    extra = site_choices()
    items = filter_site_items()
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        sid = str(item.get("id") or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        ordered.append(sid)
    for name in list(out.get("department") or []) + list(extra):
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    out["department"] = ordered
    out["department_items"] = items
    out["sites"] = extra
    return out


def dashboard_payload(filters: dict[str, Any]) -> dict[str, Any]:
    all_records = excel_service.get_all()
    token = excel_service.sync_token()
    key = _filter_key(filters)
    with _DASH_LOCK:
        cached = _DASH_CACHE
        if cached["token"] == token and cached["key"] == key and cached["payload"] is not None:
            return dict(cached["payload"])
    records = filtered(all_records, filters)
    cfg = load_config()
    t = today()
    departments = group_by_sites(records, cfg)
    employees = group_by(records, "assigned_to")
    priorities = group_by(records, "priority")
    work_types = group_by(records, "work_type")
    locations = group_by(records, "location")
    groups = {
        "department": departments,
        "assigned_to": employees,
        "status": group_by(records, "status"),
        "priority": priorities,
        "work_type": work_types,
        "location": locations,
        "supplier": group_by(records, "supplier", limit=40),
        "issue": group_by(records, "issue"),
        "delay_reason": group_by(records, "delay_reason"),
    }
    k = kpis(records)
    blockade_rows = blockades(records)
    recent = sorted(records, key=lambda r: str(r.get("created_date") or ""), reverse=True)[:8]
    payload = {
        "kpis": k,
        "status": status_distribution(records),
        "reasons": reasons(records),
        "aging": aging(records),
        "departments": departments,
        "employees": employees,
        "priorities": priorities,
        "work_types": work_types,
        "locations": locations,
        "groups": groups,
        "delivery": [
            {"name": name, "value": value, "pct": round(value / max(len(records), 1) * 100, 1)}
            for name, value in Counter(str(r.get("issue") or "Unknown") for r in records).most_common()
        ],
        "blockades": blockade_rows,
        "mindmap": mindmap(records, k=k, groups=groups, blockade_rows=blockade_rows),
        "last_days": last_days(all_records, 14),
        "trend": trend(all_records, 12),
        "recent": [annotate(r, cfg) for r in recent],
        "ops": ops_counts(records),
        "options": _options_from(all_records),
        "sites": filter_site_items(cfg),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "as_of": t.isoformat(),
        "count": len(records),
        "closed_statuses": cfg.closed_statuses,
        "sync_token": token,
    }
    with _DASH_LOCK:
        _DASH_CACHE.update({"token": token, "key": key, "payload": payload})
    return payload


def parse_query_filters(params: dict[str, Any]) -> dict[str, Any]:
    def as_list(v):
        if v is None or v == "":
            return None
        if isinstance(v, list):
            return [str(x) for x in v if str(x)]
        return [p.strip() for p in str(v).split(",") if p.strip()]

    return {
        "q": params.get("q") or "",
        "period": params.get("period") or "",
        "date_from": params.get("date_from") or params.get("from") or "",
        "date_to": params.get("date_to") or params.get("to") or "",
        "year": params.get("year") or "",
        "month": params.get("month") or "",
        "week": params.get("week") or "",
        "status": as_list(params.get("status")),
        "priority": as_list(params.get("priority")),
        "department": as_list(params.get("department")),
        "location": as_list(params.get("location")),
        "assigned_to": as_list(params.get("assigned_to")),
        "work_type": as_list(params.get("work_type")),
        "delay_reason": as_list(params.get("delay_reason")),
        "supplier": as_list(params.get("supplier")),
        "issue": as_list(params.get("issue")),
        "flag": params.get("flag") or "",
        "aging": params.get("aging") or "",
        "aging_min": params.get("aging_min") or "",
        "reason": params.get("reason") or "",
    }
