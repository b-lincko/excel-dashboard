from __future__ import annotations

"""Auto-escalation (2026-09-12): overdue MRs older than escalate_after_days get
an inbox ping for the assignee, at most once per escalation_cooldown_days.
Runs on a small daemon thread next to the backup scheduler; the manual trigger
lives at POST /api/ops/escalation/run (settings permission)."""

import os
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

from . import database
from .config import load_config
from .dates import to_date
from .domain import is_stale, today
from .excel.service import excel_service
from .notify import notify, resolve_assignee

_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()

INTERVAL_SECONDS = 6 * 3600
FIRST_RUN_SECONDS = 120  # keep tests / quick restarts free of background pings


def run_escalation(username: str = "system") -> dict[str, Any]:
    cfg = load_config()
    if not getattr(cfg, "escalation_enabled", True):
        return {"enabled": False, "checked": 0, "pinged": 0}
    after = int(getattr(cfg, "escalate_after_days", 7) or 7)
    cooldown = int(getattr(cfg, "escalation_cooldown_days", 3) or 0)
    checked = 0
    pinged = 0
    try:
        records = excel_service.get_all()
    except Exception:
        return {"enabled": True, "checked": 0, "pinged": 0, "error": "records unavailable"}
    _ = after  # kept for config parity; is_stale owns the threshold
    for rec in records:
        if not is_stale(rec, cfg):
            continue
        checked += 1
        rid = str(rec.get("record_id") or "")
        target = resolve_assignee(rec.get("assigned_to"))
        if not target or not rid:
            continue
        if cooldown > 0:
            last = database.last_notification_at("escalate", rid)
            if last:
                seen = to_date(last) or to_date(str(last)[:10])
                floor = today() - timedelta(days=cooldown)
                if seen and seen >= floor:
                    continue
        wo = str(rec.get("work_order_id") or rid)
        clock = to_date(rec.get("closed_date")) if str(rec.get("status") or "").strip().upper() == "PLACED" else to_date(rec.get("due_date"))
        days = (today() - clock).days if clock else 0
        notify(
            target,
            "escalate",
            f"{wo} is {days} day{'s' if days != 1 else ''} overdue - please update the status or add delay notes",
            record_id=rid,
            work_order_id=wo,
        )
        pinged += 1
    database.set_sync_meta("last_escalation", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return {"enabled": True, "checked": checked, "pinged": pinged, "ran_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def _loop() -> None:
    while not _stop.wait(FIRST_RUN_SECONDS):
        with _lock:
            try:
                run_escalation()
            except Exception as exc:  # never kill the thread
                print(f"[WOMS] escalation pass failed: {exc}")
        if _stop.wait(INTERVAL_SECONDS):
            break


def start_escalator() -> None:
    global _thread
    if os.environ.get("WOMS_ESCALATE", "1").strip().lower() in {"0", "false", "off"}:
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="woms-escalator", daemon=True)
    _thread.start()


def stop_escalator() -> None:
    _stop.set()
