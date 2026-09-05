from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import DB_PATH, DATA_DIR
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
    created_at TEXT NOT NULL
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
            "SELECT id, username, full_name, email, role, is_active, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def create_user(username: str, full_name: str, email: str, password: str, role: str) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO users (username, full_name, email, password_hash, role, is_active, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?)""",
            (username, full_name, email, hash_password(password), role, now_iso()),
        )
        uid = cur.lastrowid
    user = get_user_by_id(uid)
    assert user is not None
    return user


def update_user(user_id: int, **fields: Any) -> Optional[dict[str, Any]]:
    allowed = {"full_name", "email", "role", "is_active", "password"}
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


def set_sync_meta(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO sync_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# Ensure schema exists for scripts/tests that never hit FastAPI startup.
init_db()
