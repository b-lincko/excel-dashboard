from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import ATTACHMENTS_DIR, DB_PATH, DATA_DIR
from .passwords import hash_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    work_order_id TEXT,
    field TEXT,
    old_value TEXT,
    new_value TEXT,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_wo ON audit_log(work_order_id);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(created_at);
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    created_at TEXT NOT NULL,
    created_by TEXT
);
CREATE TABLE IF NOT EXISTS record_extras (
    record_id TEXT PRIMARY KEY,
    work_order_id TEXT,
    delay_kind TEXT,
    delay_source TEXT,
    delay_justification TEXT,
    updated_at TEXT,
    updated_by TEXT
);
CREATE TABLE IF NOT EXISTS wo_cache (
    record_id TEXT PRIMARY KEY,
    work_order_id TEXT,
    payload TEXT NOT NULL,
    fingerprint TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_wo_cache_wo ON wo_cache(work_order_id);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    work_order_id TEXT,
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    mime TEXT,
    size INTEGER,
    kind TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_att_record ON attachments(record_id);
CREATE TABLE IF NOT EXISTS chat_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'channel',
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT
);
CREATE TABLE IF NOT EXISTS chat_members (
    thread_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    PRIMARY KEY (thread_id, username)
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_msg ON chat_messages(thread_id, id);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    owner TEXT,
    description TEXT,
    start_date TEXT,
    due_date TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT
);
CREATE TABLE IF NOT EXISTS project_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    assignee TEXT,
    due_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_links (
    project_id INTEGER NOT NULL,
    record_id TEXT NOT NULL,
    PRIMARY KEY (project_id, record_id)
);
CREATE TABLE IF NOT EXISTS watches (
    username TEXT NOT NULL,
    record_id TEXT NOT NULL,
    work_order_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (username, record_id)
);
CREATE INDEX IF NOT EXISTS idx_watch_record ON watches(record_id);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    kind TEXT NOT NULL,
    record_id TEXT,
    work_order_id TEXT,
    thread_id INTEGER,
    body TEXT,
    created_at TEXT NOT NULL,
    read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(username, id);
CREATE TABLE IF NOT EXISTS saved_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL,
    shared INTEGER NOT NULL DEFAULT 0,
    filters TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS handovers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    department TEXT,
    shift TEXT,
    notes TEXT,
    snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS queue_seen (
    record_id TEXT NOT NULL,
    username TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (record_id, username)
);
CREATE INDEX IF NOT EXISTS idx_seen_record ON queue_seen(record_id);
CREATE TABLE IF NOT EXISTS mr_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    work_order_id TEXT,
    supplier TEXT NOT NULL DEFAULT '',
    material TEXT NOT NULL DEFAULT '',
    qty TEXT,
    unit TEXT,
    notes TEXT,
    needed_date TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    created_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_mr_lines_record ON mr_lines(record_id);
CREATE INDEX IF NOT EXISTS idx_mr_lines_supplier ON mr_lines(supplier);
CREATE INDEX IF NOT EXISTS idx_mr_lines_material ON mr_lines(material);
CREATE TABLE IF NOT EXISTS supplier_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name TEXT NOT NULL COLLATE NOCASE,
    material TEXT NOT NULL COLLATE NOCASE,
    notes TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT,
    UNIQUE(supplier_name, material)
);
CREATE INDEX IF NOT EXISTS idx_supplier_items_name ON supplier_items(supplier_name);
CREATE TABLE IF NOT EXISTS supplier_aliases (
    alias TEXT PRIMARY KEY COLLATE NOCASE,
    canonical TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_supplier_aliases_canon ON supplier_aliases(canonical);
CREATE TABLE IF NOT EXISTS wo_presence (
    record_id TEXT NOT NULL,
    username TEXT NOT NULL,
    full_name TEXT,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (record_id, username)
);
CREATE INDEX IF NOT EXISTS idx_presence_seen ON wo_presence(seen_at);
"""

DEFAULT_USERS = [
    {
        "username": "admin",
        "full_name": "System Administrator",
        "email": "admin@woms.local",
        "password": "admin123",
        "role": "admin",
    },
    {
        "username": "manager",
        "full_name": "Operations Manager",
        "email": "manager@woms.local",
        "password": "manager123",
        "role": "manager",
    },
    {
        "username": "user",
        "full_name": "Plant Technician",
        "email": "user@woms.local",
        "password": "user123",
        "role": "user",
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.Error:
        pass
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        if "last_login" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
        if "extra_permissions" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN extra_permissions TEXT")
        chat_cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_threads)")}
        if "record_id" not in chat_cols:
            conn.execute("ALTER TABLE chat_threads ADD COLUMN record_id TEXT")
        if "work_order_id" not in chat_cols:
            conn.execute("ALTER TABLE chat_threads ADD COLUMN work_order_id TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_record ON chat_threads(record_id)")
        line_cols = {r[1] for r in conn.execute("PRAGMA table_info(mr_lines)")}
        if "needed_date" not in line_cols:
            conn.execute("ALTER TABLE mr_lines ADD COLUMN needed_date TEXT")
        sup_cols = {r[1] for r in conn.execute("PRAGMA table_info(suppliers)")}
        for col, spec in (
            ("phone", "TEXT"),
            ("email", "TEXT"),
            ("contact", "TEXT"),
            ("lead_time_days", "INTEGER"),
            ("notes", "TEXT"),
        ):
            if col not in sup_cols:
                conn.execute(f"ALTER TABLE suppliers ADD COLUMN {col} {spec}")
        general = conn.execute("SELECT id FROM chat_threads WHERE kind = 'channel' AND title = 'General'").fetchone()
        if not general:
            conn.execute(
                "INSERT INTO chat_threads (kind, title, created_at, created_by) VALUES ('channel', 'General', ?, 'system')",
                (now_iso(),),
            )
        if count == 0:
            for u in DEFAULT_USERS:
                conn.execute(
                    """INSERT INTO users (username, full_name, email, password_hash, role, is_active, created_at)
                       VALUES (?, ?, ?, ?, ?, 1, ?)""",
                    (
                        u["username"],
                        u["full_name"],
                        u["email"],
                        hash_password(u["password"]),
                        u["role"],
                        now_iso(),
                    ),
                )


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    return dict(row)


def get_user_by_username(username: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return row_to_dict(row)


def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return row_to_dict(row)


def list_users() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, username, full_name, email, role, is_active, created_at, last_login, extra_permissions
               FROM users ORDER BY id"""
        ).fetchall()
        return [dict(r) for r in rows]


def touch_login(user_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso(), user_id))


def create_user(
    username: str,
    full_name: str,
    email: str,
    password: str,
    role: str,
    extra_permissions: Optional[str] = None,
) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO users (username, full_name, email, password_hash, role, is_active, created_at, extra_permissions)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            (username, full_name, email, hash_password(password), role, now_iso(), extra_permissions),
        )
        uid = cur.lastrowid
    user = get_user_by_id(uid)
    assert user is not None
    return user


def update_user(user_id: int, **fields: Any) -> Optional[dict[str, Any]]:
    allowed = {"full_name", "email", "role", "is_active", "password", "extra_permissions"}
    sets = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        if k == "password":
            sets.append("password_hash = ?")
            values.append(hash_password(v))
        else:
            sets.append(f"{k} = ?")
            values.append(v)
    if not sets:
        return get_user_by_id(user_id)
    values.append(user_id)
    with connect() as conn:
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", values)
    return get_user_by_id(user_id)


def delete_user(user_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0


def add_audit(
    username: str,
    action: str,
    work_order_id: str = "",
    field: str = "",
    old_value: str = "",
    new_value: str = "",
    details: str = "",
) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO audit_log (username, work_order_id, field, old_value, new_value, action, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (username, work_order_id, field, old_value, new_value, action, details, now_iso()),
        )


def list_audit(
    work_order_id: Optional[str] = None,
    username: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where = []
    params: list[Any] = []
    if work_order_id:
        where.append("work_order_id = ?")
        params.append(work_order_id)
    if username:
        where.append("username = ?")
        params.append(username)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM audit_log {clause}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM audit_log {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [dict(r) for r in rows], total


def get_sync_meta(key: str) -> Optional[str]:
    with connect() as conn:
        row = conn.execute("SELECT value FROM sync_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def get_setting(key: str) -> Optional[str]:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def set_sync_meta(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO sync_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def list_suppliers() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM suppliers ORDER BY name COLLATE NOCASE").fetchall()
        return [dict(r) for r in rows]


def get_supplier(supplier_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        return dict(row) if row else None


def get_supplier_by_name(name: str) -> Optional[dict[str, Any]]:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM suppliers WHERE name = ? COLLATE NOCASE",
            (cleaned,),
        ).fetchone()
        return dict(row) if row else None


def add_supplier(name: str, created_by: str = "") -> dict[str, Any]:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise ValueError("Supplier name is required")
    existing = get_supplier_by_name(cleaned)
    if existing:
        return existing
    with connect() as conn:
        conn.execute(
            "INSERT INTO suppliers (name, created_at, created_by) VALUES (?, ?, ?)",
            (cleaned, now_iso(), created_by),
        )
        row = conn.execute(
            "SELECT * FROM suppliers WHERE name = ? COLLATE NOCASE",
            (cleaned,),
        ).fetchone()
    assert row is not None
    return dict(row)


def update_supplier(supplier_id: int, **fields: Any) -> Optional[dict[str, Any]]:
    allowed = {"name", "phone", "email", "contact", "lead_time_days", "notes"}
    sets = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "name":
            v = " ".join(str(v or "").split())
            if not v:
                continue
        elif k == "lead_time_days":
            if v in ("", None):
                v = None
            else:
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    continue
        sets.append(f"{k} = ?")
        values.append(v)
    if not sets:
        return get_supplier(supplier_id)
    values.append(supplier_id)
    with connect() as conn:
        conn.execute(f"UPDATE suppliers SET {', '.join(sets)} WHERE id = ?", values)
    return get_supplier(supplier_id)


def get_record_extra(record_id: str) -> Optional[dict[str, Any]]:
    if not record_id:
        return None
    with connect() as conn:
        row = conn.execute("SELECT * FROM record_extras WHERE record_id = ?", (record_id,)).fetchone()
        return dict(row) if row else None


def get_all_record_extras() -> dict[str, dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM record_extras").fetchall()
        return {str(r["record_id"]): dict(r) for r in rows}


def get_record_extras(record_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = [str(i) for i in record_ids if i]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM record_extras WHERE record_id IN ({placeholders})",
            ids,
        ).fetchall()
        return {str(r["record_id"]): dict(r) for r in rows}


def upsert_record_extra(
    record_id: str,
    username: str,
    work_order_id: str = "",
    delay_kind: Optional[str] = None,
    delay_source: Optional[str] = None,
    delay_justification: Optional[str] = None,
) -> dict[str, Any]:
    current = get_record_extra(record_id) or {}
    kind = delay_kind if delay_kind is not None else current.get("delay_kind") or ""
    source = delay_source if delay_source is not None else current.get("delay_source") or ""
    justification = (
        delay_justification if delay_justification is not None else current.get("delay_justification") or ""
    )
    wo = work_order_id or current.get("work_order_id") or ""
    with connect() as conn:
        conn.execute(
            """INSERT INTO record_extras
               (record_id, work_order_id, delay_kind, delay_source, delay_justification, updated_at, updated_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(record_id) DO UPDATE SET
                 work_order_id = excluded.work_order_id,
                 delay_kind = excluded.delay_kind,
                 delay_source = excluded.delay_source,
                 delay_justification = excluded.delay_justification,
                 updated_at = excluded.updated_at,
                 updated_by = excluded.updated_by""",
            (record_id, wo, kind, source, justification, now_iso(), username),
        )
    extra = get_record_extra(record_id)
    assert extra is not None
    return extra


def replace_wo_cache(records: list[dict[str, Any]], fingerprint: str = "") -> int:
    ts = now_iso()
    rows: list[tuple[str, str, str, str, str]] = []
    for rec in records:
        rid = str(rec.get("record_id") or "")
        if not rid:
            continue
        rows.append(
            (
                rid,
                str(rec.get("work_order_id") or ""),
                json.dumps(rec, default=str),
                fingerprint,
                ts,
            )
        )
    with connect() as conn:
        conn.execute("DELETE FROM wo_cache")
        conn.executemany(
            """INSERT INTO wo_cache (record_id, work_order_id, payload, fingerprint, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        conn.execute(
            "INSERT INTO sync_meta (key, value) VALUES ('cache_count', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(len(rows)),),
        )
        conn.execute(
            "INSERT INTO sync_meta (key, value) VALUES ('cache_fingerprint', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (fingerprint,),
        )
    return len(rows)


def load_wo_cache() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT payload FROM wo_cache").fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def wo_cache_count() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM wo_cache").fetchone()
        return int(row["c"] if row else 0)


def _payload_to_record(raw: Any) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def get_wo_record(wo_id: str) -> Optional[dict[str, Any]]:
    key = str(wo_id or "").strip()
    if not key:
        return None
    with connect() as conn:
        row = conn.execute("SELECT payload FROM wo_cache WHERE record_id = ?", (key,)).fetchone()
        if not row:
            row = conn.execute("SELECT payload FROM wo_cache WHERE work_order_id = ?", (key,)).fetchone()
    if not row:
        return None
    return _payload_to_record(row["payload"])


def upsert_wo_record(rec: dict[str, Any], fingerprint: str = "") -> dict[str, Any]:
    rid = str((rec or {}).get("record_id") or "").strip()
    if not rid:
        raise ValueError("record_id is required")
    cleaned = {k: v for k, v in (rec or {}).items() if not str(k).startswith("_excel_backup")}
    ts = now_iso()
    payload = json.dumps(cleaned, default=str)
    with connect() as conn:
        conn.execute(
            """INSERT INTO wo_cache (record_id, work_order_id, payload, fingerprint, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(record_id) DO UPDATE SET
                 work_order_id = excluded.work_order_id,
                 payload = excluded.payload,
                 fingerprint = excluded.fingerprint,
                 updated_at = excluded.updated_at""",
            (rid, str(cleaned.get("work_order_id") or ""), payload, fingerprint or ts, ts),
        )
        conn.execute(
            "INSERT INTO sync_meta (key, value) VALUES ('token', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (ts,),
        )
    item = get_wo_record(rid)
    assert item is not None
    return item


def delete_wo_record(wo_id: str) -> bool:
    rec = get_wo_record(wo_id)
    if not rec:
        return False
    rid = str(rec.get("record_id") or wo_id)
    with connect() as conn:
        conn.execute("DELETE FROM wo_cache WHERE record_id = ?", (rid,))
        conn.execute("DELETE FROM mr_lines WHERE record_id = ?", (rid,))
        conn.execute("DELETE FROM record_extras WHERE record_id = ?", (rid,))
    return True


def database_status() -> dict[str, Any]:
    return {
        "source": "database",
        "record_count": wo_cache_count(),
        "user_count": len(list_users()),
        "last_seed": get_sync_meta("last_seed"),
        "last_write": get_sync_meta("last_write"),
        "last_write_user": get_sync_meta("last_write_user"),
        "token": get_sync_meta("token"),
    }


def reset_database() -> dict[str, Any]:
    """Delete the SQLite file and recreate empty schema + default users."""
    errors: list[str] = []
    try:
        for extra in ("", "-wal", "-shm"):
            path = Path(str(DB_PATH) + extra) if extra else DB_PATH
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                errors.append(f"Could not delete {path.name}: {exc}")
        try:
            if ATTACHMENTS_DIR.exists():
                shutil.rmtree(ATTACHMENTS_DIR)
            ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(f"Could not clear attachments: {exc}")
        init_db()
        return {"ok": not errors, "errors": errors, "users": [u["username"] for u in DEFAULT_USERS]}
    except Exception as exc:
        errors.append(str(exc))
        return {"ok": False, "errors": errors}


def snapshot_to(dest: Path) -> Path:
    """Copy the live SQLite file with the backup API (safe while connections are open)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(DB_PATH), timeout=15)
    dst = sqlite3.connect(str(tmp), timeout=15)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()
    tmp.replace(dest)
    return dest


def restore_from(src: Path) -> None:
    """Replace live SQLite contents from a snapshot without deleting the open file."""
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError("Database snapshot not found")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    incoming = sqlite3.connect(str(src), timeout=15)
    live = sqlite3.connect(str(DB_PATH), timeout=15)
    try:
        incoming.backup(live)
        live.commit()
    finally:
        live.close()
        incoming.close()
    init_db()


def snapshot_wo_count(path: Path) -> int:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("Database snapshot not found")
    conn = sqlite3.connect(str(path), timeout=5)
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM wo_cache").fetchone()
        return int(row["c"] if isinstance(row, sqlite3.Row) else (row[0] if row else 0))
    finally:
        conn.close()


def add_attachment(
    record_id: str,
    filename: str,
    stored_name: str,
    mime: str,
    size: int,
    created_by: str,
    work_order_id: str = "",
    kind: str = "file",
    note: str = "",
) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO attachments
               (record_id, work_order_id, filename, stored_name, mime, size, kind, note, created_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record_id, work_order_id, filename, stored_name, mime, size, kind, note, now_iso(), created_by),
        )
        aid = cur.lastrowid
    item = get_attachment(int(aid))
    assert item is not None
    return item


def list_attachments(record_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE record_id = ? ORDER BY id DESC",
            (record_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_attachment(attachment_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        return dict(row) if row else None


def delete_attachment(attachment_id: int) -> Optional[dict[str, Any]]:
    item = get_attachment(attachment_id)
    if not item:
        return None
    with connect() as conn:
        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    return item


def list_chat_threads(username: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT t.*,
                      (SELECT body FROM chat_messages m WHERE m.thread_id = t.id ORDER BY m.id DESC LIMIT 1) AS last_body,
                      (SELECT created_at FROM chat_messages m WHERE m.thread_id = t.id ORDER BY m.id DESC LIMIT 1) AS last_at,
                      (SELECT COUNT(*) FROM chat_messages m WHERE m.thread_id = t.id) AS message_count
               FROM chat_threads t
               LEFT JOIN chat_members cm ON cm.thread_id = t.id AND cm.username = ?
               WHERE t.kind IN ('channel', 'work_order') OR cm.username IS NOT NULL
               ORDER BY COALESCE(last_at, t.created_at) DESC""",
            (username,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_chat_thread(thread_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM chat_threads WHERE id = ?", (thread_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        members = conn.execute(
            "SELECT username FROM chat_members WHERE thread_id = ? ORDER BY username",
            (thread_id,),
        ).fetchall()
        item["members"] = [m["username"] for m in members]
        return item


def user_can_access_thread(thread_id: int, username: str) -> bool:
    thread = get_chat_thread(thread_id)
    if not thread:
        return False
    if thread.get("kind") in {"channel", "work_order"}:
        return True
    return username in (thread.get("members") or [])


def create_chat_thread(
    kind: str,
    title: str,
    created_by: str,
    members: Optional[list[str]] = None,
    record_id: str = "",
    work_order_id: str = "",
) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO chat_threads (kind, title, created_at, created_by, record_id, work_order_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (kind, title, now_iso(), created_by, record_id or None, work_order_id or None),
        )
        tid = int(cur.lastrowid)
        people = set(members or [])
        people.add(created_by)
        for name in people:
            if name:
                conn.execute(
                    "INSERT OR IGNORE INTO chat_members (thread_id, username) VALUES (?, ?)",
                    (tid, name),
                )
    item = get_chat_thread(tid)
    assert item is not None
    return item


def get_or_create_dm(username: str, other: str) -> dict[str, Any]:
    a, b = sorted([username, other])
    title = f"{a} · {b}"
    with connect() as conn:
        row = conn.execute(
            """SELECT t.id FROM chat_threads t
               JOIN chat_members m1 ON m1.thread_id = t.id AND m1.username = ?
               JOIN chat_members m2 ON m2.thread_id = t.id AND m2.username = ?
               WHERE t.kind = 'direct'""",
            (a, b),
        ).fetchone()
        if row:
            item = get_chat_thread(int(row["id"]))
            assert item is not None
            return item
    return create_chat_thread("direct", title, username, [a, b])


def get_or_create_wo_thread(record_id: str, work_order_id: str, created_by: str) -> dict[str, Any]:
    rid = str(record_id or "").strip()
    if not rid:
        raise ValueError("record_id is required")
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM chat_threads WHERE kind = 'work_order' AND record_id = ?",
            (rid,),
        ).fetchone()
        if row:
            item = get_chat_thread(int(row["id"]))
            assert item is not None
            return item
    wo = str(work_order_id or "").strip() or rid
    return create_chat_thread("work_order", f"WO {wo}", created_by, record_id=rid, work_order_id=wo)


def get_wo_thread(record_id: str) -> Optional[dict[str, Any]]:
    rid = str(record_id or "").strip()
    if not rid:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM chat_threads WHERE kind = 'work_order' AND record_id = ?",
            (rid,),
        ).fetchone()
        if not row:
            return None
    return get_chat_thread(int(row["id"]))


def list_watch_events(record_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT username, work_order_id, created_at FROM watches WHERE record_id = ? ORDER BY created_at",
            (record_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_chat_message(thread_id: int, username: str, body: str) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO chat_messages (thread_id, username, body, created_at) VALUES (?, ?, ?, ?)",
            (thread_id, username, body, now_iso()),
        )
        mid = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (mid,)).fetchone()
    assert row is not None
    return dict(row)


def list_chat_messages(thread_id: int, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 200), 500))
    with connect() as conn:
        if after_id:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE thread_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
                (thread_id, after_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM (
                     SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY id DESC LIMIT ?
                   ) AS recent ORDER BY id ASC""",
                (thread_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


def list_projects() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT p.*,
                      (SELECT COUNT(*) FROM project_tasks t WHERE t.project_id = p.id) AS task_count,
                      (SELECT COUNT(*) FROM project_tasks t WHERE t.project_id = p.id AND t.status = 'done') AS done_count,
                      (SELECT COUNT(*) FROM project_links l WHERE l.project_id = p.id) AS wo_count
               FROM projects p ORDER BY p.id DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def create_project(
    name: str,
    created_by: str,
    status: str = "active",
    owner: str = "",
    description: str = "",
    start_date: str = "",
    due_date: str = "",
) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO projects (name, status, owner, description, start_date, due_date, created_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, status or "active", owner, description, start_date, due_date, now_iso(), created_by),
        )
        pid = int(cur.lastrowid)
    item = get_project(pid)
    assert item is not None
    return item


def get_project(project_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["tasks"] = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM project_tasks WHERE project_id = ? ORDER BY id", (project_id,)
            ).fetchall()
        ]
        item["links"] = [
            dict(r) for r in conn.execute("SELECT * FROM project_links WHERE project_id = ?", (project_id,)).fetchall()
        ]
        return item


def update_project(project_id: int, **fields: Any) -> Optional[dict[str, Any]]:
    allowed = {"name", "status", "owner", "description", "start_date", "due_date"}
    sets = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        sets.append(f"{k} = ?")
        values.append(v)
    if sets:
        values.append(project_id)
        with connect() as conn:
            conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", values)
    return get_project(project_id)


def delete_project(project_id: int) -> bool:
    with connect() as conn:
        conn.execute("DELETE FROM project_tasks WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM project_links WHERE project_id = ?", (project_id,))
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cur.rowcount > 0


def add_project_task(
    project_id: int,
    title: str,
    assignee: str = "",
    due_date: str = "",
    notes: str = "",
    status: str = "open",
) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO project_tasks (project_id, title, status, assignee, due_date, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, title, status or "open", assignee, due_date, notes, now_iso()),
        )
        tid = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM project_tasks WHERE id = ?", (tid,)).fetchone()
    assert row is not None
    return dict(row)


def update_project_task(task_id: int, **fields: Any) -> Optional[dict[str, Any]]:
    allowed = {"title", "status", "assignee", "due_date", "notes"}
    sets = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        sets.append(f"{k} = ?")
        values.append(v)
    if not sets:
        with connect() as conn:
            row = conn.execute("SELECT * FROM project_tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None
    values.append(task_id)
    with connect() as conn:
        conn.execute(f"UPDATE project_tasks SET {', '.join(sets)} WHERE id = ?", values)
        row = conn.execute("SELECT * FROM project_tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def delete_project_task(task_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM project_tasks WHERE id = ?", (task_id,))
        return cur.rowcount > 0


def link_project_wo(project_id: int, record_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_links (project_id, record_id) VALUES (?, ?)",
            (project_id, record_id),
        )


def unlink_project_wo(project_id: int, record_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM project_links WHERE project_id = ? AND record_id = ?",
            (project_id, record_id),
        )


def add_watch(username: str, record_id: str, work_order_id: str = "") -> dict[str, Any]:
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO watches (username, record_id, work_order_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (username, record_id, work_order_id, now_iso()),
        )
        if work_order_id:
            conn.execute(
                "UPDATE watches SET work_order_id = ? WHERE username = ? AND record_id = ? AND (work_order_id IS NULL OR work_order_id = '')",
                (work_order_id, username, record_id),
            )
    return {"username": username, "record_id": record_id, "work_order_id": work_order_id, "watching": True}


def remove_watch(username: str, record_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM watches WHERE username = ? AND record_id = ?",
            (username, record_id),
        )
        return cur.rowcount > 0


def is_watching(username: str, record_id: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM watches WHERE username = ? AND record_id = ?",
            (username, record_id),
        ).fetchone()
        return bool(row)


def list_watched_ids(username: str) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT record_id FROM watches WHERE username = ? ORDER BY created_at DESC",
            (username,),
        ).fetchall()
        return [str(r["record_id"]) for r in rows]


def list_watchers(record_id: str) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT username FROM watches WHERE record_id = ? ORDER BY username",
            (record_id,),
        ).fetchall()
        return [str(r["username"]) for r in rows]


def add_notification(
    username: str,
    kind: str,
    body: str,
    record_id: str = "",
    work_order_id: str = "",
    thread_id: Optional[int] = None,
) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO notifications (username, kind, record_id, work_order_id, thread_id, body, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (username, kind, record_id or None, work_order_id or None, thread_id, body, now_iso()),
        )
        nid = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM notifications WHERE id = ?", (nid,)).fetchone()
    assert row is not None
    return dict(row)


def list_notifications(username: str, unread_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 200))
    clause = "AND read_at IS NULL" if unread_only else ""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM notifications WHERE username = ? {clause} ORDER BY id DESC LIMIT ?",
            (username, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def unread_notification_count(username: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE username = ? AND read_at IS NULL",
            (username,),
        ).fetchone()
        return int(row["c"] if row else 0)


def mark_notifications_read(username: str, ids: Optional[list[int]] = None) -> int:
    ts = now_iso()
    with connect() as conn:
        if ids:
            placeholders = ",".join("?" for _ in ids)
            cur = conn.execute(
                f"""UPDATE notifications SET read_at = ?
                    WHERE username = ? AND read_at IS NULL AND id IN ({placeholders})""",
                [ts, username, *ids],
            )
        else:
            cur = conn.execute(
                "UPDATE notifications SET read_at = ? WHERE username = ? AND read_at IS NULL",
                (ts, username),
            )
        return int(cur.rowcount or 0)


def create_saved_view(name: str, username: str, filters: dict[str, Any], shared: bool = False) -> dict[str, Any]:
    payload = json.dumps(filters or {}, default=str)
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO saved_views (name, username, shared, filters, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name, username, 1 if shared else 0, payload, now_iso()),
        )
        vid = int(cur.lastrowid)
    item = get_saved_view(vid)
    assert item is not None
    return item


def get_saved_view(view_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM saved_views WHERE id = ?", (view_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["filters"] = json.loads(item.get("filters") or "{}")
    except json.JSONDecodeError:
        item["filters"] = {}
    item["shared"] = bool(item.get("shared"))
    return item


def list_saved_views(username: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM saved_views
               WHERE username = ? OR shared = 1
               ORDER BY shared ASC, id DESC""",
            (username,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["filters"] = json.loads(item.get("filters") or "{}")
        except json.JSONDecodeError:
            item["filters"] = {}
        item["shared"] = bool(item.get("shared"))
        item["mine"] = item.get("username") == username
        out.append(item)
    return out


def delete_saved_view(view_id: int, username: str, *, admin: bool = False) -> bool:
    with connect() as conn:
        if admin:
            cur = conn.execute("DELETE FROM saved_views WHERE id = ?", (view_id,))
        else:
            cur = conn.execute(
                "DELETE FROM saved_views WHERE id = ? AND username = ?",
                (view_id, username),
            )
        return cur.rowcount > 0


def create_handover(
    username: str,
    notes: str,
    snapshot: dict[str, Any],
    department: str = "",
    shift: str = "",
) -> dict[str, Any]:
    payload = json.dumps(snapshot or {}, default=str)
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO handovers (username, department, shift, notes, snapshot, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (username, department or "", shift or "", notes or "", payload, now_iso()),
        )
        hid = int(cur.lastrowid)
    item = get_handover(hid)
    assert item is not None
    return item


def get_handover(handover_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM handovers WHERE id = ?", (handover_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["snapshot"] = json.loads(item.get("snapshot") or "{}")
    except json.JSONDecodeError:
        item["snapshot"] = {}
    return item


def list_handovers(limit: int = 30) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 30), 100))
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM handovers ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["snapshot"] = json.loads(item.get("snapshot") or "{}")
        except json.JSONDecodeError:
            item["snapshot"] = {}
        out.append(item)
    return out


def mark_queue_seen(record_id: str, username: str) -> dict[str, Any]:
    rid = str(record_id or "").strip()
    if not rid:
        raise ValueError("record_id is required")
    ts = now_iso()
    with connect() as conn:
        conn.execute(
            """INSERT INTO queue_seen (record_id, username, seen_at) VALUES (?, ?, ?)
               ON CONFLICT(record_id, username) DO UPDATE SET seen_at = excluded.seen_at""",
            (rid, username, ts),
        )
    return {"record_id": rid, "username": username, "seen_at": ts}


def list_queue_seen(record_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    ids = [str(i) for i in record_ids if i]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT record_id, username, seen_at FROM queue_seen WHERE record_id IN ({placeholders}) ORDER BY seen_at",
            ids,
        ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row["record_id"]), []).append(
            {"username": row["username"], "seen_at": row["seen_at"]}
        )
    return out


def list_mr_lines(record_id: str) -> list[dict[str, Any]]:
    rid = str(record_id or "").strip()
    if not rid:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM mr_lines WHERE record_id = ? ORDER BY sort_order, id",
            (rid,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_mr_lines_many(record_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    ids = [str(i).strip() for i in record_ids if str(i).strip()]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM mr_lines WHERE record_id IN ({placeholders}) ORDER BY sort_order, id",
            ids,
        ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row["record_id"]), []).append(dict(row))
    return out


def list_all_mr_lines() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM mr_lines ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def replace_mr_lines(
    record_id: str,
    items: list[dict[str, Any]],
    created_by: str = "",
    work_order_id: str = "",
) -> list[dict[str, Any]]:
    rid = str(record_id or "").strip()
    if not rid:
        raise ValueError("record_id is required")
    wo = str(work_order_id or "").strip()
    cleaned: list[dict[str, Any]] = []
    for row in items or []:
        if not isinstance(row, dict):
            continue
        supplier = " ".join(str(row.get("supplier") or "").split())
        material = " ".join(str(row.get("material") or "").split())
        if not supplier and not material:
            continue
        cleaned.append(
            {
                "supplier": supplier,
                "material": material,
                "qty": " ".join(str(row.get("qty") or "").split()),
                "unit": " ".join(str(row.get("unit") or "").split()),
                "notes": " ".join(str(row.get("notes") or "").split()),
                "needed_date": " ".join(str(row.get("needed_date") or "").split())[:10],
            }
        )
    ts = now_iso()
    with connect() as conn:
        conn.execute("DELETE FROM mr_lines WHERE record_id = ?", (rid,))
        for idx, row in enumerate(cleaned):
            conn.execute(
                """INSERT INTO mr_lines
                   (record_id, work_order_id, supplier, material, qty, unit, notes, needed_date, sort_order, created_at, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rid,
                    wo,
                    row["supplier"],
                    row["material"],
                    row["qty"],
                    row["unit"],
                    row["notes"],
                    row.get("needed_date") or "",
                    idx,
                    ts,
                    created_by,
                ),
            )
    return list_mr_lines(rid)


def list_supplier_items(supplier_name: str = "") -> list[dict[str, Any]]:
    name = " ".join(str(supplier_name or "").split())
    with connect() as conn:
        if name:
            rows = conn.execute(
                "SELECT * FROM supplier_items WHERE supplier_name = ? COLLATE NOCASE ORDER BY material COLLATE NOCASE",
                (name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM supplier_items ORDER BY supplier_name COLLATE NOCASE, material COLLATE NOCASE"
            ).fetchall()
        return [dict(r) for r in rows]


def add_supplier_item(
    supplier_name: str,
    material: str,
    notes: str = "",
    created_by: str = "",
) -> Optional[dict[str, Any]]:
    name = " ".join(str(supplier_name or "").split())
    item = " ".join(str(material or "").split())
    if not name or not item:
        return None
    with connect() as conn:
        conn.execute(
            """INSERT INTO supplier_items (supplier_name, material, notes, created_at, created_by)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(supplier_name, material) DO UPDATE SET
                 notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE supplier_items.notes END""",
            (name, item, " ".join(str(notes or "").split()), now_iso(), created_by),
        )
        row = conn.execute(
            "SELECT * FROM supplier_items WHERE supplier_name = ? COLLATE NOCASE AND material = ? COLLATE NOCASE",
            (name, item),
        ).fetchone()
    return dict(row) if row else None


def replace_supplier_items(supplier_name: str, materials: list[str], created_by: str = "") -> list[dict[str, Any]]:
    name = " ".join(str(supplier_name or "").split())
    if not name:
        raise ValueError("Supplier name is required")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in materials or []:
        item = " ".join(str(raw or "").split())
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    ts = now_iso()
    with connect() as conn:
        conn.execute("DELETE FROM supplier_items WHERE supplier_name = ? COLLATE NOCASE", (name,))
        for item in cleaned:
            conn.execute(
                """INSERT INTO supplier_items (supplier_name, material, notes, created_at, created_by)
                   VALUES (?, ?, '', ?, ?)""",
                (name, item, ts, created_by),
            )
    return list_supplier_items(name)


def delete_supplier_item(item_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM supplier_items WHERE id = ?", (item_id,))
        return cur.rowcount > 0


def list_supplier_aliases() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM supplier_aliases ORDER BY canonical COLLATE NOCASE, alias COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_supplier_alias(alias: str, canonical: str, created_by: str = "") -> dict[str, Any]:
    alias_name = " ".join(str(alias or "").split())
    canon = " ".join(str(canonical or "").split())
    if not alias_name or not canon:
        raise ValueError("Alias and canonical name are required")
    if alias_name.lower() == canon.lower():
        raise ValueError("Alias cannot be the same as the canonical name")
    with connect() as conn:
        conn.execute(
            """INSERT INTO supplier_aliases (alias, canonical, created_at, created_by)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(alias) DO UPDATE SET canonical = excluded.canonical, created_by = excluded.created_by""",
            (alias_name, canon, now_iso(), created_by),
        )
        row = conn.execute(
            "SELECT * FROM supplier_aliases WHERE alias = ? COLLATE NOCASE",
            (alias_name,),
        ).fetchone()
    assert row is not None
    return dict(row)


def rename_supplier_refs(old_name: str, new_name: str) -> None:
    old = " ".join(str(old_name or "").split())
    new = " ".join(str(new_name or "").split())
    if not old or not new or old.lower() == new.lower():
        return
    with connect() as conn:
        conn.execute(
            "UPDATE mr_lines SET supplier = ? WHERE supplier = ? COLLATE NOCASE",
            (new, old),
        )
        conn.execute(
            "UPDATE supplier_items SET supplier_name = ? WHERE supplier_name = ? COLLATE NOCASE",
            (new, old),
        )
        conn.execute(
            "UPDATE supplier_aliases SET canonical = ? WHERE canonical = ? COLLATE NOCASE",
            (new, old),
        )


PRESENCE_TTL_SEC = 45


def _like_pattern(q: str) -> str:
    text = " ".join(str(q or "").split())
    if not text:
        return ""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def record_ids_matching_q(q: str) -> set[str]:
    """Match WO id, payload text, or any supplier/item line. Used by list search."""
    pattern = _like_pattern(q)
    if not pattern:
        return set()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT record_id FROM wo_cache
             WHERE work_order_id LIKE ? ESCAPE '\\' COLLATE NOCASE
                OR record_id LIKE ? ESCAPE '\\' COLLATE NOCASE
                OR payload LIKE ? ESCAPE '\\' COLLATE NOCASE
            UNION
            SELECT record_id FROM mr_lines
             WHERE supplier LIKE ? ESCAPE '\\' COLLATE NOCASE
                OR material LIKE ? ESCAPE '\\' COLLATE NOCASE
                OR notes LIKE ? ESCAPE '\\' COLLATE NOCASE
            """,
            (pattern,) * 6,
        ).fetchall()
    return {str(r["record_id"]) for r in rows if r["record_id"]}


def suggest_workspace(q: str, limit: int = 8) -> dict[str, list[dict[str, Any]]]:
    """Fast typeahead groups: orders, suppliers, materials, people."""
    pattern = _like_pattern(q)
    limit_n = max(1, min(int(limit or 8), 20))
    empty: dict[str, list[dict[str, Any]]] = {"orders": [], "suppliers": [], "materials": [], "people": []}
    if not pattern:
        return empty
    with connect() as conn:
        order_rows = conn.execute(
            """
            SELECT record_id, work_order_id, payload FROM wo_cache
             WHERE work_order_id LIKE ? ESCAPE '\\' COLLATE NOCASE
                OR record_id LIKE ? ESCAPE '\\' COLLATE NOCASE
                OR payload LIKE ? ESCAPE '\\' COLLATE NOCASE
             LIMIT ?
            """,
            (pattern, pattern, pattern, limit_n),
        ).fetchall()
        supplier_rows = conn.execute(
            """
            SELECT name FROM (
                SELECT name FROM suppliers WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE
                UNION
                SELECT supplier AS name FROM mr_lines
                 WHERE supplier LIKE ? ESCAPE '\\' COLLATE NOCASE AND supplier != ''
            ) ORDER BY name COLLATE NOCASE LIMIT ?
            """,
            (pattern, pattern, limit_n),
        ).fetchall()
        material_rows = conn.execute(
            """
            SELECT material, supplier FROM mr_lines
             WHERE material LIKE ? ESCAPE '\\' COLLATE NOCASE AND material != ''
             LIMIT ?
            """,
            (pattern, limit_n),
        ).fetchall()
        if len(material_rows) < limit_n:
            extra = conn.execute(
                """
                SELECT material, supplier_name AS supplier FROM supplier_items
                 WHERE material LIKE ? ESCAPE '\\' COLLATE NOCASE
                 LIMIT ?
                """,
                (pattern, limit_n),
            ).fetchall()
            seen = {(str(r["material"] or "").lower(), str(r["supplier"] or "").lower()) for r in material_rows}
            for row in extra:
                key = (str(row["material"] or "").lower(), str(row["supplier"] or "").lower())
                if key in seen:
                    continue
                seen.add(key)
                material_rows.append(row)
                if len(material_rows) >= limit_n:
                    break
        people_rows = conn.execute(
            """
            SELECT username, full_name, role FROM users
             WHERE is_active = 1
               AND (username LIKE ? ESCAPE '\\' COLLATE NOCASE
                    OR IFNULL(full_name, '') LIKE ? ESCAPE '\\' COLLATE NOCASE)
             ORDER BY username COLLATE NOCASE LIMIT ?
            """,
            (pattern, pattern, limit_n),
        ).fetchall()
    orders: list[dict[str, Any]] = []
    for row in order_rows:
        rec = _payload_to_record(row["payload"]) or {}
        orders.append(
            {
                "kind": "order",
                "record_id": row["record_id"],
                "work_order_id": row["work_order_id"] or rec.get("work_order_id") or "",
                "label": rec.get("work_order_id") or row["work_order_id"] or row["record_id"],
                "hint": " · ".join(
                    p
                    for p in (
                        rec.get("department"),
                        rec.get("status"),
                        rec.get("assigned_to"),
                        rec.get("supplier"),
                    )
                    if p
                ),
                "description": str(rec.get("description") or "")[:160],
            }
        )
    suppliers = [
        {"kind": "supplier", "label": r["name"], "hint": "Supplier"}
        for r in supplier_rows
        if r["name"]
    ]
    materials = []
    seen_mat: set[str] = set()
    for row in material_rows:
        mat = str(row["material"] or "").strip()
        if not mat or mat.lower() in seen_mat:
            continue
        seen_mat.add(mat.lower())
        materials.append(
            {
                "kind": "material",
                "label": mat,
                "hint": str(row["supplier"] or "").strip() or "Item",
                "supplier": str(row["supplier"] or "").strip(),
            }
        )
    people = [
        {
            "kind": "person",
            "label": r["username"],
            "hint": r["full_name"] or r["role"] or "",
            "username": r["username"],
            "full_name": r["full_name"] or "",
        }
        for r in people_rows
    ]
    return {"orders": orders, "suppliers": suppliers, "materials": materials, "people": people}


def touch_presence(record_id: str, username: str, full_name: str = "") -> dict[str, Any]:
    rid = str(record_id or "").strip()
    user = str(username or "").strip()
    if not rid or not user:
        raise ValueError("record_id and username are required")
    ts = now_iso()
    with connect() as conn:
        conn.execute(
            """INSERT INTO wo_presence (record_id, username, full_name, seen_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(record_id, username) DO UPDATE SET
                 full_name = excluded.full_name,
                 seen_at = excluded.seen_at""",
            (rid, user, full_name or user, ts),
        )
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=PRESENCE_TTL_SEC * 4)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("DELETE FROM wo_presence WHERE seen_at < ?", (cutoff,))
    return {"record_id": rid, "username": user, "seen_at": ts}


def list_presence(record_id: str, exclude: str = "") -> list[dict[str, Any]]:
    rid = str(record_id or "").strip()
    if not rid:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=PRESENCE_TTL_SEC)).strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        rows = conn.execute(
            """SELECT username, full_name, seen_at FROM wo_presence
               WHERE record_id = ? AND seen_at >= ?
               ORDER BY username COLLATE NOCASE""",
            (rid, cutoff),
        ).fetchall()
    skip = str(exclude or "").strip().lower()
    out = []
    for row in rows:
        if skip and str(row["username"] or "").lower() == skip:
            continue
        out.append({"username": row["username"], "full_name": row["full_name"] or "", "seen_at": row["seen_at"]})
    return out


# Ensure schema exists for scripts/tests that never hit FastAPI startup.
init_db()
