from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any, Optional

from .config import load_config
from .dates import parse_date, quarter_of, to_date, week_bounds
from .domain import (
    aging_days,
    annotate,
    closing_days,
    is_closed,
    is_in_progress,
    is_open,
    is_overdue,
    is_pending,
    matches_filters,
    reason_for_open,
    today,
)
from .excel.service import excel_service


def filtered(records: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = load_config()
    return [r for r in records if matches_filters(r, filters, cfg)]


def kpis(records: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = load_config()
    total = len(records)
    closed = [r for r in records if is_closed(r, cfg)]
    open_ = [r for r in records if is_open(r, cfg)]
    overdue = [r for r in records if is_overdue(r, cfg)]
    pending = [r for r in records if is_pending(r, cfg)]
    in_prog = [r for r in records if is_in_progress(r, cfg)]
    closing = [closing_days(r) for r in closed]
    closing = [c for c in closing if c is not None]
    aging = [aging_days(r) for r in open_]
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
    blockades = [
        r
        for r in open_
        if str(r.get("status") or "").strip().upper() in {"UNDER NTP", "ON HOLD", "OPEN"}
        or is_overdue(r, cfg)
    ]
    return {
        "total": total,
        "open": len(open_),
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
        "progress_open": round((len(in_prog) / len(open_) * 100) if open_ else 0, 1),
    }


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
    open_recs = [r for r in records if is_open(r, cfg)]
    counts = Counter()
    for r in open_recs:
        st = str(r.get("status") or "OPEN").strip() or "OPEN"
        counts[st] += 1
    total = len(open_recs) or 1
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


def group_by(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    cfg = load_config()
    groups: dict[str, list] = defaultdict(list)
    for r in records:
        groups[str(r.get(field) or "Unassigned")].append(r)
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
    return rows


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


def dashboard_payload(filters: dict[str, Any]) -> dict[str, Any]:
    records = filtered(excel_service.get_all(), filters)
    cfg = load_config()
    t = today()
    iso = t.isocalendar()
    return {
        "kpis": kpis(records),
        "status": status_distribution(records),
        "reasons": reasons(records),
        "aging": aging(records),
        "departments": group_by(records, "department"),
        "employees": group_by(records, "assigned_to"),
        "priorities": group_by(records, "priority"),
        "work_types": group_by(records, "work_type"),
        "locations": group_by(records, "location"),
        "delivery": [
            {"name": name, "value": value, "pct": round(value / max(len(records), 1) * 100, 1)}
            for name, value in Counter(str(r.get("issue") or "Unknown") for r in records).most_common()
        ],
        "blockades": blockades(records),
        "today": today_activity(records),
        "last_days": last_days(excel_service.get_all(), 14),
        "trend": trend(excel_service.get_all(), 12),
        "weekly": weekly(excel_service.get_all(), int(iso[0]), int(iso[1])),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "as_of": t.isoformat(),
        "count": len(records),
        "closed_statuses": cfg.closed_statuses,
    }


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
        "flag": params.get("flag") or "",
        "aging": params.get("aging") or "",
        "reason": params.get("reason") or "",
    }
