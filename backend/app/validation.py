from __future__ import annotations

from typing import Any

from .config import load_config
from .dates import parse_date
from .domain import is_closed, is_open


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_work_order(data: dict[str, Any], partial: bool = False) -> list[str]:
    cfg = load_config()
    errors: list[str] = []
    if not partial:
        if not str(data.get("description") or "").strip() and not str(data.get("issue") or "").strip():
            errors.append("A description or issue is required.")
        if not str(data.get("status") or "").strip():
            errors.append("Status is required.")

    created = parse_date(data.get("created_date"))
    due = parse_date(data.get("due_date"))
    scheduled = parse_date(data.get("scheduled_date"))
    completion = parse_date(data.get("completion_date"))
    closed = parse_date(data.get("closed_date"))

    if created and due and due < created and not cfg.allow_close_before_create:
        errors.append("Due date cannot be earlier than the created date.")
    if created and scheduled and scheduled < created - __import__("datetime").timedelta(days=1):
        errors.append("Scheduled date is more than a day before the created date.")
    if created and completion and completion < created and not cfg.allow_close_before_create:
        errors.append("Completion date cannot be earlier than the created date.")
    if created and closed and closed < created and not cfg.allow_close_before_create:
        errors.append("Closing date cannot be earlier than the created date.")
    if completion and closed and closed < completion:
        errors.append("Closing date cannot be earlier than the completion date.")

    status = str(data.get("status") or "")
    if status:
        dummy = {"status": status}
        if is_closed(dummy, cfg) and cfg.require_closed_date_on_close:
            if not closed and not completion:
                errors.append("A closed/completed work order should have a completion or closing date.")
        if is_open(dummy, cfg) and closed and not cfg.allow_open_with_close_date:
            errors.append("An open work order should not have a closing date.")

    required_map = getattr(cfg, "status_required_fields", None) or {}
    needed: list[str] = []
    if status:
        for key, fields in required_map.items():
            if _norm(key) == _norm(status):
                needed = [str(f).strip() for f in (fields or []) if str(f).strip()]
                break
        labels = cfg.mapping.model_dump() if hasattr(cfg, "mapping") else {}
        for field in needed:
            if not str(data.get(field) or "").strip():
                label = field if field not in labels else field
                errors.append(f"Status {status} requires {label}.")
    return errors
