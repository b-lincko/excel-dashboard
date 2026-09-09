from __future__ import annotations

from typing import Any, Optional

from . import database, notify
from .security import user_permissions

STATES = ("none", "assigned", "submitted", "changes_requested", "approved", "sent_to_accounts")
LOCKED_STATES = {"approved", "sent_to_accounts"}
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
    return out


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


def submit(rec: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    current = approval_for(rec)
    if current.get("state") in LOCKED_STATES:
        raise ValueError("This PO is approved and locked.")
    if current.get("state") not in {"assigned", "changes_requested"}:
        raise ValueError("Assign the PO to a technician before sending it to the operational manager.")
    mine = _norm(actor.get("username")) in {_norm(current.get("assignee")), _norm(actor.get("full_name"))}
    assignee_login = _resolve_login(current.get("assignee"))
    if not mine and assignee_login != actor.get("username") and str(actor.get("role") or "") != "admin":
        if _norm(actor.get("full_name")) != _norm(current.get("assignee")):
            raise PermissionError("Only the assigned technician can send this PO to the manager.")
    item = database.upsert_po_approval(
        str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
        state="submitted",
        coordinator=current.get("coordinator") or "",
        assignee=current.get("assignee") or "",
        manager="",
        accounts_by=current.get("accounts_by") or "",
        comment=current.get("comment") or "",
        signature_png="",
        signed_at="",
        signed_by="",
        locked=0,
        updated_by=actor["username"],
    )
    database.add_po_approval_event(str(rec.get("record_id") or ""), "submit", actor["username"], "Sent to operational manager")
    wo = rec.get("work_order_id") or rec.get("record_id")
    managers = [str(u.get("username") or "") for u in users_with_perm("po_approve") if str(u.get("role") or "") != "admin"]
    if not managers:
        managers = [str(u.get("username") or "") for u in users_with_perm("po_approve")]
    _notify_many(managers, actor["username"], "po", f"{actor['username']} sent PO {wo} for signature", rec)
    return {**item, "events": database.list_po_approval_events(str(rec.get("record_id") or ""))}


def decide(
    rec: dict[str, Any],
    actor: dict[str, Any],
    *,
    approve: bool,
    comment: str = "",
    signature_png: str = "",
) -> dict[str, Any]:
    if not has_perm(actor, "po_approve"):
        raise PermissionError("Only an operational manager can sign or return this PO.")
    current = approval_for(rec)
    if current.get("state") not in {"submitted", "changes_requested"}:
        raise ValueError("There is no PO waiting for the manager.")
    if current.get("state") in LOCKED_STATES:
        raise ValueError("This PO is already approved and locked.")
    note = str(comment or "").strip()
    wo = rec.get("work_order_id") or rec.get("record_id")
    rid = str(rec.get("record_id") or "")
    if approve:
        if not str(signature_png or "").strip():
            raise ValueError("Draw a signature to approve this PO.")
        item = database.upsert_po_approval(
            rid,
            work_order_id=str(rec.get("work_order_id") or ""),
            state="approved",
            coordinator=current.get("coordinator") or "",
            assignee=current.get("assignee") or "",
            manager=actor["username"],
            accounts_by="",
            comment=note,
            signature_png=str(signature_png or ""),
            signed_at=database.now_iso(),
            signed_by=actor["username"],
            locked=1,
            updated_by=actor["username"],
        )
        database.add_po_approval_event(rid, "approve", actor["username"], note or "Signed and approved")
        ping = []
        for name in (current.get("coordinator"), _resolve_login(current.get("assignee")), current.get("assignee")):
            login = _resolve_login(name) or (name if name and database.get_user_by_username(str(name)) else None)
            if login:
                ping.append(login)
        _notify_many(ping, actor["username"], "po", f"{actor['username']} signed PO {wo}. It is locked.", rec)
        return {**item, "events": database.list_po_approval_events(rid)}
    if not note:
        raise ValueError("Write the changes you need when returning a PO.")
    item = database.upsert_po_approval(
        rid,
        work_order_id=str(rec.get("work_order_id") or ""),
        state="changes_requested",
        coordinator=current.get("coordinator") or "",
        assignee=current.get("assignee") or "",
        manager=actor["username"],
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


def send_accounts(rec: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    if not has_perm(actor, "po_dispatch") and not has_perm(actor, "accounts"):
        raise PermissionError("Only a dispatcher (Abubacar, or a user granted that right) can send the PO to Accounts.")
    current = approval_for(rec)
    if current.get("state") != "approved":
        raise ValueError("Approve and lock the PO before sending it to Accounts.")
    item = database.upsert_po_approval(
        str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
        state="sent_to_accounts",
        coordinator=current.get("coordinator") or actor["username"],
        assignee=current.get("assignee") or "",
        manager=current.get("manager") or "",
        accounts_by=actor["username"],
        comment=current.get("comment") or "",
        signature_png=current.get("signature_png") or "",
        signed_at=current.get("signed_at") or "",
        signed_by=current.get("signed_by") or "",
        locked=1,
        updated_by=actor["username"],
    )
    database.add_po_approval_event(str(rec.get("record_id") or ""), "send_accounts", actor["username"], "Sent to Accounts")
    wo = rec.get("work_order_id") or rec.get("record_id")
    notify_accounts(actor["username"], rec, f"{actor['username']} sent approved PO {wo} to Accounts")
    return {**item, "events": database.list_po_approval_events(str(rec.get("record_id") or ""))}


def capabilities(user: dict[str, Any], rec: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    state = str(approval.get("state") or "none")
    assignee = str(approval.get("assignee") or "")
    mine = _norm(user.get("username")) in {_norm(assignee), _norm(user.get("full_name"))} or _norm(
        user.get("full_name")
    ) == _norm(assignee)
    if _resolve_login(assignee) == user.get("username"):
        mine = True
    return {
        "can_assign": has_perm(user, "po_dispatch") and state not in LOCKED_STATES,
        "can_submit": mine and state in {"assigned", "changes_requested"},
        "can_decide": has_perm(user, "po_approve") and state == "submitted",
        "can_send_accounts": (has_perm(user, "po_dispatch") or has_perm(user, "accounts")) and state == "approved",
        "technicians": technician_users(),
        "dispatchers": [
            {"username": u["username"], "full_name": u.get("full_name") or ""}
            for u in users_with_perm("po_dispatch")
        ],
    }
