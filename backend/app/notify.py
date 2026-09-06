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
    return database.add_notification(
        username=username,
        kind=kind,
        body=body,
        record_id=record_id or "",
        work_order_id=work_order_id or "",
        thread_id=thread_id,
    )


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
