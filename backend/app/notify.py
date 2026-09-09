from __future__ import annotations

import re
from typing import Any, Optional

from . import database

MENTION_RE = re.compile(r"@([A-Za-z0-9._-]+)")


def parse_mentions(text: str) -> list[str]:
    seen: list[str] = []
    keys: set[str] = set()
    for match in MENTION_RE.finditer(text or ""):
        name = match.group(1)
        key = name.lower()
        if key in keys:
            continue
        keys.add(key)
        seen.append(name)
    return seen


def resolve_usernames(raw: list[str]) -> list[str]:
    users = {u["username"].lower(): u["username"] for u in database.list_users() if u.get("is_active")}
    out: list[str] = []
    for name in raw:
        resolved = users.get(str(name or "").lower())
        if resolved and resolved not in out:
            out.append(resolved)
    return out


def resolve_assignee(name: Any) -> Optional[str]:
    """Map an Assign-to cell (full name or username) to an active login."""
    needle = str(name or "").strip().lower()
    if not needle:
        return None
    for user in database.list_users():
        if not user.get("is_active"):
            continue
        username = str(user.get("username") or "").strip()
        full_name = str(user.get("full_name") or "").strip()
        if needle in {username.lower(), full_name.lower()}:
            return username
    return None


def notify_assignment(
    actor: str,
    rec: dict[str, Any],
    previous: str = "",
    skip: Optional[set[str]] = None,
) -> list[str]:
    """Inbox ping when Assign to changes to a user (by username or full name)."""
    current = str((rec or {}).get("assigned_to") or "").strip()
    if not current:
        return []
    if str(previous or "").strip().lower() == current.lower():
        return []
    username = resolve_assignee(current)
    if not username or username == actor:
        return []
    ignored = set(skip or set())
    if username in ignored:
        return []
    prev_user = resolve_assignee(previous)
    if prev_user and prev_user == username:
        return []
    wo = str(rec.get("work_order_id") or rec.get("record_id") or "")
    notify(
        username,
        "assign",
        f"{actor} assigned {wo} to you",
        record_id=str(rec.get("record_id") or ""),
        work_order_id=str(rec.get("work_order_id") or ""),
    )
    return [username]


def notify(
    username: str,
    kind: str,
    body: str,
    *,
    record_id: str = "",
    work_order_id: str = "",
    thread_id: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    if not username:
        return None
    item = database.add_notification(
        username=username,
        kind=kind,
        body=body,
        record_id=record_id or "",
        work_order_id=work_order_id or "",
        thread_id=thread_id,
    )
    try:
        from . import mailer

        mailer.maybe_notify_email(
            username,
            kind,
            body,
            record_id=record_id or "",
            work_order_id=work_order_id or "",
            thread_id=thread_id,
        )
    except Exception:
        pass
    return item


def fanout_mentions(
    actor: str,
    text: str,
    *,
    record_id: str = "",
    work_order_id: str = "",
    thread_id: Optional[int] = None,
) -> list[str]:
    snippet = " ".join((text or "").split())
    if len(snippet) > 180:
        snippet = snippet[:177] + "…"
    wo = work_order_id or record_id
    pinged: list[str] = []
    for name in resolve_usernames(parse_mentions(text)):
        if name == actor:
            continue
        where = f" on {wo}" if wo else ""
        notify(
            name,
            "mention",
            f"{actor} mentioned you{where}: {snippet}",
            record_id=record_id,
            work_order_id=work_order_id,
            thread_id=thread_id,
        )
        pinged.append(name)
    return pinged


def notify_watchers(
    actor: str,
    rec: dict[str, Any],
    summary: str,
    skip: Optional[set[str]] = None,
) -> list[str]:
    rid = str(rec.get("record_id") or "")
    if not rid:
        return []
    ignored = set(skip or set())
    ignored.add(actor)
    wo = str(rec.get("work_order_id") or "")
    sent: list[str] = []
    for name in database.list_watchers(rid):
        if name in ignored:
            continue
        notify(name, "watch", summary, record_id=rid, work_order_id=wo)
        sent.append(name)
    return sent


def notify_thread_message(
    actor: str,
    thread: dict[str, Any],
    text: str,
    skip: Optional[set[str]] = None,
) -> list[str]:
    """Inbox ping for chat messages (DM, channel, work-order thread)."""
    snippet = " ".join((text or "").split())
    if len(snippet) > 180:
        snippet = snippet[:177] + "…"
    ignored = set(skip or set())
    ignored.add(actor)
    members = [str(n) for n in (thread.get("members") or []) if n]
    kind = str(thread.get("kind") or "")
    if kind in {"channel", "work_order"} and not members:
        members = [u["username"] for u in database.list_users() if u.get("is_active") and u.get("username")]
    title = str(thread.get("title") or "chat").strip() or "chat"
    rid = str(thread.get("record_id") or "")
    wo = str(thread.get("work_order_id") or "")
    tid = thread.get("id")
    try:
        tid_int = int(tid) if tid is not None else None
    except (TypeError, ValueError):
        tid_int = None
    sent: list[str] = []
    for name in members:
        if name in ignored:
            continue
        notify(
            name,
            "message",
            f"{actor} in {title}: {snippet}",
            record_id=rid,
            work_order_id=wo,
            thread_id=tid_int,
        )
        sent.append(name)
        ignored.add(name)
    return sent
