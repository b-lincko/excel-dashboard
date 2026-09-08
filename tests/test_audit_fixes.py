from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402
from app import database  # noqa: E402


def _admin():
    database.init_db()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_logout_revokes_current_token():
    client, headers = _admin()
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    out = client.post("/api/auth/logout", headers=headers)
    assert out.status_code == 200
    again = client.get("/api/auth/me", headers=headers)
    assert again.status_code == 401


def test_password_change_invalidates_old_token():
    client, headers = _admin()
    name = f"pw_{os.urandom(3).hex()}"
    created = client.post(
        "/api/users",
        headers=headers,
        json={"username": name, "password": "ChangeMe1", "role": "user"},
    )
    assert created.status_code == 200, created.text
    signed = client.post("/api/auth/login", json={"username": name, "password": "ChangeMe1"})
    old = signed.json()["access_token"]
    old_headers = {"Authorization": f"Bearer {old}"}
    changed = client.post(
        "/api/auth/password",
        headers=old_headers,
        json={"current_password": "ChangeMe1", "new_password": "ChangeMe2"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json().get("access_token")
    stale = client.get("/api/auth/me", headers=old_headers)
    assert stale.status_code == 401
    fresh_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    me = client.get("/api/auth/me", headers=fresh_headers)
    assert me.status_code == 200
    assert me.json()["must_change_password"] is False


def test_sync_upload_requires_settings():
    client, headers = _admin()
    name = f"buyer_{os.urandom(3).hex()}"
    created = client.post(
        "/api/users",
        headers=headers,
        json={"username": name, "password": "ChangeMe1", "role": "user"},
    )
    assert created.status_code == 200, created.text
    signed = client.post("/api/auth/login", json={"username": name, "password": "ChangeMe1"})
    assert signed.status_code == 200
    uheaders = {"Authorization": f"Bearer {signed.json()['access_token']}"}
    res = client.post(
        "/api/sync/upload",
        headers=uheaders,
        files={"file": ("file.xlsx", b"PK not-really-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 403


def test_refresh_reports_soft_reload():
    client, headers = _admin()
    refresh = client.post("/api/sync/refresh", headers=headers)
    assert refresh.status_code == 200
    assert refresh.json().get("hard") is False
    assert refresh.json().get("source") == "database"


def test_folder_listing_stays_inside_app():
    client, headers = _admin()
    blocked = client.get("/api/settings/folders", headers=headers, params={"path": "/etc"})
    assert blocked.status_code == 400
    root = client.get("/api/settings/folders", headers=headers, params={"path": "/"})
    assert root.status_code == 400
    ok = client.get("/api/settings/folders", headers=headers)
    assert ok.status_code == 200
    body = ok.json()
    for item in body.get("roots") or []:
        assert item["path"] not in {"/", "/etc", "/home"}


def test_write_safety_backups_are_pruned(tmp_path):
    from app.config import AppConfig, save_config, load_config
    from app.excel.service import ExcelService

    cfg = load_config()
    previous = AppConfig.model_validate(cfg.model_dump())
    try:
        cfg.backup_dir = str(tmp_path / "backups")
        cfg.backup_write_keep = 3
        save_config(cfg)
        svc = ExcelService()
        day = tmp_path / "backups" / "2026-09-08"
        day.mkdir(parents=True)
        for i in range(6):
            p = day / f"file_2026-09-08_0{i}0000_update.xlsx"
            p.write_bytes(b"PK dummy")
            os.utime(p, (time.time() - (10 - i), time.time() - (10 - i)))
        removed = svc.prune_backups(3, reasons=svc.WRITE_REASONS)
        assert removed == 3
        assert len(list(day.glob("*_update.xlsx"))) == 3
    finally:
        save_config(previous)
