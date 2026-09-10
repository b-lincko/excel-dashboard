from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from . import database, notify
from .config import load_config
from .security import user_permissions

STATES = ("none", "assigned", "submitted", "changes_requested", "approved", "sent_to_accounts")
LOCKED_STATES = {"approved", "sent_to_accounts"}
PING_STATES = {"assigned", "changes_requested", "submitted", "approved"}
PO_LOCK_FIELDS = {
    "po_number",
    "supplier",
    "lines",
    "scheduled_date",
    "closed_date",
    "work_type",
    "description",
    "unit_price",
    "price",
    "total_price",
    "final_price",
}
PRICE_FIELDS = ("unit_price", "price", "total_price", "final_price")


class PingCooldown(Exception):
    """Raised when a follow-up is sent again inside the cooldown window."""


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def technician_users() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for user in database.list_users():
        if not user.get("is_active"):
            continue
        if str(user.get("role") or "").strip().lower() != "user":
            continue
        name = str(user.get("full_name") or user.get("username") or "").strip()
        if not name:
            continue
        out.append(
            {
                "username": user["username"],
                "full_name": str(user.get("full_name") or ""),
                "label": name,
            }
        )
    return out


def technician_names() -> list[str]:
    return [u["label"] for u in technician_users()]


def is_technician_name(name: Any) -> bool:
    needle = _norm(name)
    if not needle:
        return False
    for user in technician_users():
        if needle in {_norm(user.get("username")), _norm(user.get("full_name")), _norm(user.get("label"))}:
            return True
    return False


def assignee_allowed(name: Any, current: Any = "") -> bool:
    text = str(name or "").strip()
    if not text:
        return True
    if is_technician_name(text):
        return True
    return _norm(text) == _norm(current)


def has_perm(user: Optional[dict[str, Any]], perm: str) -> bool:
    if not user:
        return False
    if str(user.get("role") or "").lower() == "admin":
        return True
    return perm in user_permissions(user)


def users_with_perm(perm: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for user in database.list_users():
        if not user.get("is_active"):
            continue
        if has_perm(user, perm):
            out.append(user)
    return out


def empty_approval(rec: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    rec = rec or {}
    return {
        "record_id": str(rec.get("record_id") or ""),
        "work_order_id": str(rec.get("work_order_id") or ""),
        "state": "none",
        "coordinator": "",
        "assignee": "",
        "manager": "",
        "accounts_by": "",
        "comment": "",
        "signature_png": "",
        "signed_at": "",
        "signed_by": "",
        "managers": "",
        "holder": "",
        "locked": 0,
        "updated_at": "",
        "updated_by": "",
        "events": [],
    }


def get_approval(record_id: str) -> Optional[dict[str, Any]]:
    return database.get_po_approval(record_id)


def approval_for(rec: dict[str, Any]) -> dict[str, Any]:
    rid = str(rec.get("record_id") or "")
    item = get_approval(rid) if rid else None
    if not item:
        item = empty_approval(rec)
    item["locked"] = 1 if item.get("state") in LOCKED_STATES else int(item.get("locked") or 0)
    item["events"] = database.list_po_approval_events(rid) if rid else []
    return item


def is_locked(rec: dict[str, Any]) -> bool:
    rid = str(rec.get("record_id") or "")
    if not rid:
        return False
    item = get_approval(rid)
    if not item:
        return False
    return item.get("state") in LOCKED_STATES or bool(item.get("locked"))


def locked_fields(changes: dict[str, Any], rec: dict[str, Any]) -> list[str]:
    if not is_locked(rec):
        return []
    return [k for k in (changes or {}) if k in PO_LOCK_FIELDS]


def _notify_many(usernames: list[str], actor: str, kind: str, body: str, rec: dict[str, Any]) -> None:
    skip = {actor}
    rid = str(rec.get("record_id") or "")
    wo = str(rec.get("work_order_id") or "")
    for name in usernames:
        if not name or name in skip:
            continue
        notify.notify(name, kind, body, record_id=rid, work_order_id=wo)
        skip.add(name)


def notify_dispatchers(actor: str, rec: dict[str, Any], body: str) -> None:
    names = [str(u.get("username") or "") for u in users_with_perm("po_dispatch")]
    _notify_many(names, actor, "po", body, rec)


def notify_accounts(actor: str, rec: dict[str, Any], body: str) -> None:
    names = [str(u.get("username") or "") for u in users_with_perm("accounts")]
    if not names:
        names = [str(u.get("username") or "") for u in users_with_perm("po_dispatch")]
    _notify_many(names, actor, "accounts", body, rec)


def notify_po_created(actor: str, rec: dict[str, Any], previous_po: str = "") -> None:
    current = str(rec.get("po_number") or "").strip()
    if not current:
        return
    if str(previous_po or "").strip() == current:
        return
    wo = rec.get("work_order_id") or rec.get("record_id")
    notify_dispatchers(actor, rec, f"{actor} recorded PO {current} on {wo}")


def _resolve_login(name: Any) -> Optional[str]:
    needle = _norm(name)
    if not needle:
        return None
    for user in database.list_users():
        if not user.get("is_active"):
            continue
        if needle in {_norm(user.get("username")), _norm(user.get("full_name"))}:
            return str(user.get("username") or "")
    return None


def public_approval(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item or {})
    sig = str(out.get("signature_png") or "")
    out["has_signature"] = bool(sig)
    out.pop("signature_png", None)
    out["manager_list"] = split_names(out.get("managers") or "")
    return out


def split_names(raw: Any) -> list[str]:
    text = str(raw or "").replace(";", ",")
    out: list[str] = []
    seen: set[str] = set()
    for part in text.split(","):
        name = part.strip()
        key = _norm(name)
        if not name or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def people() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for user in database.list_users():
        if not user.get("is_active"):
            continue
        name = str(user.get("full_name") or user.get("username") or "").strip()
        out.append(
            {
                "username": user["username"],
                "full_name": str(user.get("full_name") or ""),
                "label": name or user["username"],
                "role": str(user.get("role") or ""),
            }
        )
    return out


def manager_users() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for user in users_with_perm("po_approve"):
        if str(user.get("role") or "").lower() == "admin":
            continue
        name = str(user.get("full_name") or user.get("username") or "").strip()
        out.append(
            {
                "username": user["username"],
                "full_name": str(user.get("full_name") or ""),
                "label": name or user["username"],
            }
        )
    if not out:
        for user in users_with_perm("po_approve"):
            name = str(user.get("full_name") or user.get("username") or "").strip()
            out.append(
                {
                    "username": user["username"],
                    "full_name": str(user.get("full_name") or ""),
                    "label": name or user["username"],
                }
            )
    return out


def _normalize_managers(raw: Any) -> list[str]:
    names = raw if isinstance(raw, (list, tuple)) else split_names(raw)
    allowed: dict[str, str] = {}
    for u in manager_users():
        allowed[_norm(u["username"])] = u["username"]
        allowed[_norm(u.get("full_name"))] = u["username"]
        allowed[_norm(u.get("label"))] = u["username"]
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        login = allowed.get(_norm(name)) or _resolve_login(name)
        if not login or login in seen:
            continue
        person = database.get_user_by_username(login)
        if not person or not has_perm(person, "po_approve"):
            continue
        seen.add(login)
        out.append(login)
        if len(out) >= 3:
            break
    return out


def _is_selected_manager(user: Optional[dict[str, Any]], approval: dict[str, Any]) -> bool:
    if not user:
        return False
    if str(user.get("role") or "").lower() == "admin":
        return True
    if not has_perm(user, "po_approve"):
        return False
    selected = {_norm(n) for n in split_names(approval.get("managers") or "")}
    if not selected:
        return str(approval.get("state") or "") == "submitted"
    me = {_norm(user.get("username")), _norm(user.get("full_name"))}
    return bool(me & selected)


def _is_holder(user: Optional[dict[str, Any]], approval: dict[str, Any]) -> bool:
    if not user:
        return False
    holder = str(approval.get("holder") or "")
    if not holder:
        return False
    if _norm(user.get("username")) == _norm(holder) or _norm(user.get("full_name")) == _norm(holder):
        return True
    return _resolve_login(holder) == user.get("username")


def assign(rec: dict[str, Any], actor: dict[str, Any], assignee: str) -> dict[str, Any]:
    if not has_perm(actor, "po_dispatch"):
        raise PermissionError("Only a PO dispatcher (Abubacar, or a user granted that right) can assign a PO.")
    name = str(assignee or "").strip()
    if not is_technician_name(name):
        raise ValueError("Assign the PO to a technician (role User), not an admin or manager.")
    current = approval_for(rec)
    if current.get("state") in LOCKED_STATES:
        raise ValueError("This PO is approved and locked.")
    item = database.upsert_po_approval(
        str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
        state="assigned",
        coordinator=actor["username"],
        assignee=name,
        manager="",
        managers="",
        holder="",
        accounts_by=current.get("accounts_by") or "",
        comment="",
        signature_png="",
        signed_at="",
        signed_by="",
        locked=0,
        updated_by=actor["username"],
    )
    database.add_po_approval_event(str(rec.get("record_id") or ""), "assign", actor["username"], f"Assigned to {name}")
    login = _resolve_login(name)
    wo = rec.get("work_order_id") or rec.get("record_id")
    if login and login != actor["username"]:
        notify.notify(
            login,
            "po",
            f"{actor['username']} assigned PO {wo} to you",
            record_id=str(rec.get("record_id") or ""),
            work_order_id=str(rec.get("work_order_id") or ""),
        )
    return {**item, "events": database.list_po_approval_events(str(rec.get("record_id") or ""))}


def unassign(rec: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    if not has_perm(actor, "po_dispatch"):
        raise PermissionError("Only a dispatcher can unassign a purchase approval.")
    current = approval_for(rec)
    if current.get("state") in LOCKED_STATES:
        raise ValueError("This purchase slip is signed and locked.")
    item = database.upsert_po_approval(
        str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
        state="none",
        coordinator=current.get("coordinator") or actor["username"],
        assignee="",
        manager="",
        managers="",
        holder="",
        accounts_by="",
        comment="",
        signature_png="",
        signed_at="",
        signed_by="",
        locked=0,
        updated_by=actor["username"],
    )
    database.add_po_approval_event(str(rec.get("record_id") or ""), "unassign", actor["username"], "Unassigned")
    return {**item, "events": database.list_po_approval_events(str(rec.get("record_id") or ""))}


def submit(rec: dict[str, Any], actor: dict[str, Any], managers: Any = None) -> dict[str, Any]:
    current = approval_for(rec)
    if current.get("state") in LOCKED_STATES:
        raise ValueError("This PO is approved and locked.")
    if current.get("state") not in {"assigned", "changes_requested"}:
        raise ValueError("Assign the PO to a technician before sending it to the operational manager.")
    mine = _norm(actor.get("username")) in {_norm(current.get("assignee")), _norm(actor.get("full_name"))}
    assignee_login = _resolve_login(current.get("assignee"))
    dispatcher = has_perm(actor, "po_dispatch") or str(actor.get("role") or "") == "admin"
    if not mine and not dispatcher:
        raise PermissionError("Only the assigned technician or a dispatcher can send this purchase slip to a manager.")
    picks = _normalize_managers(managers)
    if not picks:
        picks = [u["username"] for u in manager_users()[:3]]
    if not picks:
        raise ValueError("Pick at least one manager to send this purchase slip to.")
    item = database.upsert_po_approval(
        str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
        state="submitted",
        coordinator=current.get("coordinator") or "",
        assignee=current.get("assignee") or "",
        manager="",
        managers=",".join(picks),
        holder="",
        accounts_by=current.get("accounts_by") or "",
        comment=current.get("comment") or "",
        signature_png="",
        signed_at="",
        signed_by="",
        locked=0,
        updated_by=actor["username"],
    )
    labels = ", ".join(picks)
    database.add_po_approval_event(
        str(rec.get("record_id") or ""), "submit", actor["username"], f"Sent to {labels}"
    )
    wo = rec.get("work_order_id") or rec.get("record_id")
    _notify_many(picks, actor["username"], "po", f"{actor['username']} sent purchase slip {wo} for your signature", rec)
    return {**item, "events": database.list_po_approval_events(str(rec.get("record_id") or ""))}


def decide(
    rec: dict[str, Any],
    actor: dict[str, Any],
    *,
    approve: bool,
    comment: str = "",
    signature_png: str = "",
    return_to: str = "",
) -> dict[str, Any]:
    if not has_perm(actor, "po_approve"):
        raise PermissionError("Only a manager can sign or return this purchase slip.")
    current = approval_for(rec)
    if current.get("state") != "submitted":
        raise ValueError("There is no purchase slip waiting for a manager. Send it first.")
    if not _is_selected_manager(actor, current):
        raise PermissionError("This slip was not sent to you.")
    if current.get("state") in LOCKED_STATES:
        raise ValueError("This purchase slip is already signed and locked.")
    note = str(comment or "").strip()
    wo = rec.get("work_order_id") or rec.get("record_id")
    rid = str(rec.get("record_id") or "")
    if approve:
        if not str(signature_png or "").strip():
            raise ValueError("Draw a digital signature to approve this purchase slip.")
        holder = _resolve_login(return_to) or str(return_to or "").strip()
        if not holder:
            holder = _resolve_login(current.get("assignee")) or str(current.get("assignee") or "")
        item = database.upsert_po_approval(
            rid,
            work_order_id=str(rec.get("work_order_id") or ""),
            state="approved",
            coordinator=current.get("coordinator") or "",
            assignee=current.get("assignee") or "",
            manager=actor["username"],
            managers=current.get("managers") or "",
            holder=holder,
            accounts_by="",
            comment=note,
            signature_png=str(signature_png or ""),
            signed_at=database.now_iso(),
            signed_by=actor["username"],
            locked=1,
            updated_by=actor["username"],
        )
        database.add_po_approval_event(
            rid, "approve", actor["username"], note or f"Signed and sent to {holder or 'sender'}"
        )
        ping = []
        for name in (holder, current.get("coordinator"), _resolve_login(current.get("assignee")), current.get("assignee")):
            login = _resolve_login(name) or (name if name and database.get_user_by_username(str(name)) else None)
            if login:
                ping.append(login)
        _notify_many(
            ping,
            actor["username"],
            "po",
            f"{actor['username']} signed purchase slip {wo}. It is locked.",
            rec,
        )
        return {**item, "events": database.list_po_approval_events(rid)}
    if not note:
        raise ValueError("Write the changes you need when returning a purchase slip.")
    item = database.upsert_po_approval(
        rid,
        work_order_id=str(rec.get("work_order_id") or ""),
        state="changes_requested",
        coordinator=current.get("coordinator") or "",
        assignee=current.get("assignee") or "",
        manager=actor["username"],
        managers=current.get("managers") or "",
        holder="",
        accounts_by="",
        comment=note,
        signature_png="",
        signed_at="",
        signed_by="",
        locked=0,
        updated_by=actor["username"],
    )
    database.add_po_approval_event(rid, "deny", actor["username"], note)
    login = _resolve_login(current.get("assignee"))
    if login:
        notify.notify(
            login,
            "po",
            f"{actor['username']} returned PO {wo} with changes: {note[:160]}",
            record_id=rid,
            work_order_id=str(rec.get("work_order_id") or ""),
        )
    return {**item, "events": database.list_po_approval_events(rid)}


def send_accounts(rec: dict[str, Any], actor: dict[str, Any], to: str = "") -> dict[str, Any]:
    if not accounts_enabled():
        raise ValueError("The Accounts step is switched off — a signed slip is already complete.")
    current = approval_for(rec)
    if current.get("state") != "approved":
        raise ValueError("Sign the purchase slip before sending it to Accounts.")
    if not (
        has_perm(actor, "po_dispatch")
        or has_perm(actor, "accounts")
        or _is_holder(actor, current)
        or str(actor.get("role") or "").lower() == "admin"
    ):
        raise PermissionError("Only the person holding this signed slip (or a dispatcher) can send it to Accounts.")
    dest = _resolve_login(to) or str(to or "").strip()
    item = database.upsert_po_approval(
        str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
        state="sent_to_accounts",
        coordinator=current.get("coordinator") or actor["username"],
        assignee=current.get("assignee") or "",
        manager=current.get("manager") or "",
        managers=current.get("managers") or "",
        holder=dest or current.get("holder") or "",
        accounts_by=actor["username"],
        comment=current.get("comment") or "",
        signature_png=current.get("signature_png") or "",
        signed_at=current.get("signed_at") or "",
        signed_by=current.get("signed_by") or "",
        locked=1,
        updated_by=actor["username"],
    )
    note = f"Sent to Accounts" + (f" ({dest})" if dest else "")
    database.add_po_approval_event(str(rec.get("record_id") or ""), "send_accounts", actor["username"], note)
    wo = rec.get("work_order_id") or rec.get("record_id")
    ping = [dest] if dest else []
    ping.extend(str(u.get("username") or "") for u in users_with_perm("accounts"))
    if not ping:
        ping = [str(u.get("username") or "") for u in users_with_perm("po_dispatch")]
    _notify_many(ping, actor["username"], "accounts", f"{actor['username']} sent signed purchase slip {wo} to Accounts", rec)
    return {**item, "events": database.list_po_approval_events(str(rec.get("record_id") or ""))}


def route(rec: dict[str, Any], actor: dict[str, Any], to: str) -> dict[str, Any]:
    current = approval_for(rec)
    if current.get("state") != "approved":
        raise ValueError("Sign the purchase slip before sending it on.")
    if not (
        has_perm(actor, "po_dispatch")
        or _is_holder(actor, current)
        or str(actor.get("role") or "").lower() == "admin"
    ):
        raise PermissionError("Only the person holding this signed slip can send it to someone else.")
    dest = _resolve_login(to) or str(to or "").strip()
    if not dest:
        raise ValueError("Pick someone to send this signed slip to.")
    item = database.upsert_po_approval(
        str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
        state="approved",
        coordinator=current.get("coordinator") or "",
        assignee=current.get("assignee") or "",
        manager=current.get("manager") or "",
        managers=current.get("managers") or "",
        holder=dest,
        accounts_by=current.get("accounts_by") or "",
        comment=current.get("comment") or "",
        signature_png=current.get("signature_png") or "",
        signed_at=current.get("signed_at") or "",
        signed_by=current.get("signed_by") or "",
        locked=1,
        updated_by=actor["username"],
    )
    database.add_po_approval_event(str(rec.get("record_id") or ""), "route", actor["username"], f"Sent to {dest}")
    wo = rec.get("work_order_id") or rec.get("record_id")
    notify.notify(
        dest,
        "po",
        f"{actor['username']} sent signed purchase slip {wo} to you",
        record_id=str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
    )
    return {**item, "events": database.list_po_approval_events(str(rec.get("record_id") or ""))}


# ---------- Follow up (ping) ----------

PING_LABELS = {
    "assigned": "the technician",
    "changes_requested": "the technician",
    "submitted": "the manager(s) who must sign",
    "approved": "the person holding the signed slip",
}


def ping_target_label(state: Any) -> str:
    return PING_LABELS.get(str(state or "").strip().lower(), "")


def ping_targets(approval: dict[str, Any]) -> list[str]:
    """Logins that currently hold the ball on this slip."""
    state = str(approval.get("state") or "").strip().lower()
    out: list[str] = []
    if state == "submitted":
        for name in split_names(approval.get("managers") or ""):
            login = _resolve_login(name)
            if login and login not in out:
                out.append(login)
    elif state in {"assigned", "changes_requested"}:
        login = _resolve_login(approval.get("assignee"))
        if login:
            out.append(login)
    elif state == "approved":
        login = _resolve_login(approval.get("holder"))
        if login:
            out.append(login)
    return out


def last_ping_at(approval: dict[str, Any]) -> str:
    for ev in reversed(approval.get("events") or []):
        if str(ev.get("action") or "") == "ping":
            return str(ev.get("created_at") or "")
    return ""


def _parse_ping_time(value: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def accounts_enabled() -> bool:
    """Admin toggle (Settings > Purchase approval): is the Accounts step on?
    Off (default) a signed slip is complete; the lane and the send action hide."""
    try:
        from .config import load_config

        return bool(getattr(load_config(), "po_accounts_process", False))
    except Exception:
        return False


def ping_cooldown_minutes() -> int:
    try:
        return max(0, int(getattr(load_config(), "po_ping_cooldown_minutes", 30) or 0))
    except Exception:
        return 30


def can_ping(user: Optional[dict[str, Any]], approval: dict[str, Any]) -> bool:
    if not user:
        return False
    state = str(approval.get("state") or "").strip().lower()
    if state not in PING_STATES:
        return False
    login = _norm(user.get("username"))
    involved = (
        has_perm(user, "po_dispatch")
        or _resolve_login(approval.get("assignee")) == user.get("username")
        or _is_holder(user, approval)
        or _norm(approval.get("coordinator")) == login
    )
    if not involved:
        return False
    return any(t for t in ping_targets(approval) if _norm(t) != login)


def follow_up(rec: dict[str, Any], actor: dict[str, Any], note: str = "") -> dict[str, Any]:
    """Nudge whoever is holding the ball: managers sign, technician fixes/sends, holder routes."""
    current = approval_for(rec)
    state = str(current.get("state") or "").strip().lower()
    rid = str(rec.get("record_id") or "")
    if state in {"", "none"}:
        raise ValueError("Nothing to follow up yet — assign a technician to this PO first.")
    if state == "sent_to_accounts":
        raise ValueError("This slip is already with Accounts — nothing to follow up.")
    if state not in PING_STATES:
        raise ValueError("There is nothing to follow up on this slip right now.")
    login = str(actor.get("username") or "")
    involved = (
        has_perm(actor, "po_dispatch")
        or _resolve_login(current.get("assignee")) == login
        or _is_holder(actor, current)
        or _norm(current.get("coordinator")) == _norm(login)
    )
    if not involved:
        raise PermissionError("Only someone on this purchase slip (dispatcher, technician, holder) can follow up.")
    targets = [t for t in ping_targets(current) if t and _norm(t) != _norm(login)]
    if not targets:
        raise ValueError("Everyone who needs it already has it — there is nobody to follow up.")
    cooldown = ping_cooldown_minutes()
    last = _parse_ping_time(last_ping_at(current))
    if cooldown > 0 and last:
        waited = (datetime.now(timezone.utc) - last).total_seconds() / 60.0
        if waited < cooldown:
            raise PingCooldown(
                f"A follow-up was sent {max(1, int(waited))} minutes ago — try again in about {max(1, int(cooldown - waited))} minutes."
            )
    text = str(note or "").strip()[:200]
    wo = rec.get("work_order_id") or rec.get("record_id")
    labels = ", ".join(targets)
    database.add_po_approval_event(rid, "ping", login, text or f"Follow-up sent to {labels}")
    message = f"{login} followed up on purchase slip {wo}"
    if state == "submitted":
        message += " — it is waiting for your signature"
    elif state == "assigned":
        message += " — please update suppliers and send it to the manager"
    elif state == "changes_requested":
        message += " — please make the requested changes and send it again"
    elif state == "approved":
        message += " — you hold the signed slip, please send it on or to Accounts"
    if text:
        message += f": {text}"
    _notify_many(targets, login, "ping", message, rec)
    return {**current, "events": database.list_po_approval_events(rid)}


def capabilities(user: dict[str, Any], rec: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    state = str(approval.get("state") or "none")
    assignee = str(approval.get("assignee") or "")
    mine = _norm(user.get("username")) in {_norm(assignee), _norm(user.get("full_name"))} or _norm(
        user.get("full_name")
    ) == _norm(assignee)
    if _resolve_login(assignee) == user.get("username"):
        mine = True
    holding = _is_holder(user, approval)
    return {
        "can_assign": has_perm(user, "po_dispatch") and state not in LOCKED_STATES,
        "can_unassign": has_perm(user, "po_dispatch") and state in {"assigned", "submitted", "changes_requested"},
        "can_submit": state in {"assigned", "changes_requested"} and (mine or has_perm(user, "po_dispatch")),
        "can_decide": _is_selected_manager(user, approval) and state == "submitted",
        "can_route": state == "approved" and (holding or has_perm(user, "po_dispatch")),
        "can_send_accounts": accounts_enabled()
        and state == "approved"
        and (holding or has_perm(user, "po_dispatch") or has_perm(user, "accounts")),
        "can_ping": can_ping(user, approval),
        "ping_label": ping_target_label(state),
        "ping_targets": ping_targets(approval),
        "last_ping_at": last_ping_at(approval),
        "ping_cooldown_minutes": ping_cooldown_minutes(),
        "technicians": technician_users(),
        "managers": manager_users(),
        "people": people(),
        "dispatchers": [
            {"username": u["username"], "full_name": u.get("full_name") or ""}
            for u in users_with_perm("po_dispatch")
        ],
    }


LANE_BY_STATE = {
    "none": "incoming",
    "": "incoming",
    "assigned": "assigned",
    "changes_requested": "changes",
    "submitted": "to_sign",
    "approved": "ready",
    "sent_to_accounts": "accounts",
}

LANES = ("incoming", "assigned", "changes", "to_sign", "ready", "accounts")


def lane_for(state: Any) -> str:
    return LANE_BY_STATE.get(str(state or "none").strip().lower(), "incoming")


def is_mine(user: Optional[dict[str, Any]], approval: dict[str, Any]) -> bool:
    if not user:
        return False
    if _is_holder(user, approval):
        return True
    if str(approval.get("state") or "") == "submitted" and _is_selected_manager(user, approval):
        return True
    signer = str(approval.get("signed_by") or "")
    if signer and (_norm(signer) == _norm(user.get("username") or "") or _resolve_login(signer) == user.get("username")):
        return True
    assignee = str(approval.get("assignee") or "")
    if not assignee:
        return False
    if _norm(user.get("username")) in {_norm(assignee), _norm(user.get("full_name"))}:
        return True
    if _norm(user.get("full_name")) == _norm(assignee):
        return True
    return _resolve_login(assignee) == user.get("username")


def _slim_rec(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": rec.get("record_id") or "",
        "work_order_id": rec.get("work_order_id") or rec.get("record_id") or "",
        "po_number": rec.get("po_number") or "",
        "supplier": rec.get("supplier") or "",
        "status": rec.get("status") or "",
        "department": rec.get("department") or rec.get("_site") or "",
        "assigned_to": rec.get("assigned_to") or "",
        "description": str(rec.get("description") or "")[:240],
        "unit_price": rec.get("unit_price") or "",
        "price": rec.get("price") or "",
        "total_price": rec.get("total_price") or "",
        "final_price": rec.get("final_price") or "",
        "closed_date": rec.get("closed_date") or "",
        "scheduled_date": rec.get("scheduled_date") or "",
    }


def _visible(user: dict[str, Any], lane: str, mine: bool) -> bool:
    if str(user.get("role") or "").lower() == "admin":
        return True
    if has_perm(user, "po_dispatch"):
        return True
    if has_perm(user, "po_approve") and lane in {"to_sign", "changes"}:
        return mine
    if has_perm(user, "accounts") and lane in {"ready", "accounts"}:
        return True
    return mine


def default_lane(user: dict[str, Any], counts: dict[str, int]) -> str:
    if has_perm(user, "po_dispatch") and counts.get("incoming"):
        return "incoming"
    if has_perm(user, "po_approve") and counts.get("to_sign"):
        return "to_sign"
    if has_perm(user, "po_dispatch") and counts.get("ready"):
        return "ready"
    if counts.get("changes"):
        return "changes"
    if counts.get("assigned"):
        return "assigned"
    if accounts_enabled() and has_perm(user, "accounts") and counts.get("accounts"):
        return "accounts"
    if has_perm(user, "po_approve"):
        return "to_sign"
    if has_perm(user, "po_dispatch"):
        return "incoming"
    return "assigned"


def inbox(user: dict[str, Any], q: str = "") -> dict[str, Any]:
    recs = database.load_wo_cache()
    by_rid = {str(r.get("record_id") or ""): r for r in recs if r.get("record_id")}
    rows = {str(r.get("record_id") or ""): r for r in database.list_po_approvals() if r.get("record_id")}
    packed: list[dict[str, Any]] = []
    seen: set[str] = set()
    needle = _norm(q)
    login = _norm(str(user.get("username") or ""))
    personal: dict[str, list[dict[str, Any]]] = {"to_sign": [], "sent": [], "signed": []}

    def _bucket(appr: dict[str, Any], item: dict[str, Any]) -> None:
        """Personal views (independent of lane visibility): slips waiting for my
        signature, slips I sent out, and signed slips that involve me."""
        state = str(appr.get("state") or "")
        if state == "submitted":
            if _is_selected_manager(user, appr):
                personal["to_sign"].append(item)
            sender = _norm(str(_resolve_login(appr.get("updated_by")) or appr.get("updated_by") or ""))
            if login and sender == login:
                personal["sent"].append(
                    {
                        **item,
                        "ping": {
                            "can": can_ping(user, appr),
                            "last": last_ping_at(appr),
                            "cooldown_min": ping_cooldown_minutes(),
                            "target": ping_target_label(state),
                        },
                    }
                )
        elif state in {"assigned", "changes_requested"}:
            tech = _norm(str(_resolve_login(appr.get("assignee")) or appr.get("assignee") or ""))
            if login and tech == login:
                personal["sent"].append(item)
        elif state in {"approved", "sent_to_accounts"}:
            holder = _norm(str(_resolve_login(appr.get("holder")) or appr.get("holder") or ""))
            signer = _norm(str(_resolve_login(appr.get("signed_by")) or appr.get("signed_by") or ""))
            if login and login in {x for x in (holder, signer) if x}:
                personal["signed"].append(item)

    def pack(rec: dict[str, Any], appr: dict[str, Any]) -> Optional[dict[str, Any]]:
        rid = str(rec.get("record_id") or appr.get("record_id") or "")
        if not rid or rid in seen:
            return None
        state = str(appr.get("state") or "none")
        po = str(rec.get("po_number") or "").strip()
        if state in {"none", ""} and not po:
            return None
        lane = lane_for(state)
        item = _slim_rec(rec)
        item["record_id"] = rid
        item["approval"] = public_approval({**empty_approval(rec), **appr, "events": []})
        item["lane"] = lane
        item["mine"] = is_mine(user, appr)
        if needle:
            hay = " ".join(
                str(item.get(k) or "")
                for k in ("work_order_id", "po_number", "supplier", "assigned_to", "description", "department")
            ).lower()
            hay += " " + str(appr.get("assignee") or "").lower()
            if needle not in hay:
                return None
        seen.add(rid)
        return item

    for rid, appr in rows.items():
        rec = by_rid.get(rid) or database.get_wo_record(rid) or {
            "record_id": rid,
            "work_order_id": appr.get("work_order_id"),
        }
        rec = {**rec, "record_id": rid}
        item = pack(rec, appr)
        if item:
            _bucket(appr, item)
            if _visible(user, item["lane"], item["mine"]):
                packed.append(item)
    for rec in recs:
        rid = str(rec.get("record_id") or "")
        if not rid or rid in seen:
            continue
        if not str(rec.get("po_number") or "").strip():
            continue
        item = pack(rec, empty_approval(rec))
        if item and _visible(user, item["lane"], item["mine"]):
            packed.append(item)

    packed.sort(
        key=lambda it: (
            str((it.get("approval") or {}).get("updated_at") or ""),
            str(it.get("work_order_id") or ""),
        ),
        reverse=True,
    )
    lanes: dict[str, list[dict[str, Any]]] = {key: [] for key in LANES}
    for item in packed:
        lanes.setdefault(item["lane"], []).append(item)
    counts = {key: len(lanes.get(key) or []) for key in LANES}
    accounts_on = accounts_enabled()
    if not accounts_on:
        # The Accounts step is switched off: hide the lane entirely (data is
        # kept, and comes back when an admin re-enables the step).
        lanes.pop("accounts", None)
        counts.pop("accounts", None)
    return {
        "lanes": lanes,
        "counts": counts,
        "total": len(packed),
        "default_lane": default_lane(user, counts),
        "accounts_enabled": accounts_on,
        "mine": personal,
        "mine_counts": {key: len(val) for key, val in personal.items()},
        "technicians": technician_users(),
        "caps": {
            "can_dispatch": has_perm(user, "po_dispatch"),
            "can_approve": has_perm(user, "po_approve"),
            "can_accounts": has_perm(user, "po_dispatch") or has_perm(user, "accounts"),
            "is_technician": str(user.get("role") or "").lower() == "user",
        },
    }
