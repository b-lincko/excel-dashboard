from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402
from app import database  # noqa: E402
from app.routers import auth as auth_router  # noqa: E402


def test_login_lockout_does_not_block_real_admin():
    database.init_db()
    auth_router._LOGIN_FAILS.clear()
    client = TestClient(app)
    for _ in range(8):
        res = client.post("/api/auth/login", json={"username": "no-such-user", "password": "wrong"})
        assert res.status_code == 401
    locked = client.post("/api/auth/login", json={"username": "no-such-user", "password": "wrong"})
    assert locked.status_code == 429
    ok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert ok.status_code == 200
    auth_router._LOGIN_FAILS.clear()


def test_settings_never_returns_jwt_secret():
    database.init_db()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    got = client.get("/api/settings", headers=headers)
    assert got.status_code == 200
    data = got.json()["settings"]
    assert "jwt_secret" not in data
    assert data.get("jwt_secret_set") is True


def test_new_user_password_min_eight():
    database.init_db()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    short = client.post(
        "/api/users",
        headers=headers,
        json={"username": "tiny", "password": "1234567", "role": "user"},
    )
    assert short.status_code == 422
