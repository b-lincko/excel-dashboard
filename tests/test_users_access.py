from __future__ import annotations

import uuid
import sys
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


def test_user_crud_access_profile_and_last_admin():
    client, headers = _admin()
    name = f"sam_{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": name,
            "password": "ChangeMe1",
            "full_name": "Sam Buyer",
            "email": "sam@local",
            "role": "user",
            "extra_permissions": ["backup", "create"],
        },
    )
    assert created.status_code == 200, created.text
    item = created.json()["item"]
    uid = item["id"]
    assert "backup" in item["permissions"]
    assert "create" in item["permissions"]

    catalog = client.get("/api/users/access-catalog", headers=headers)
    assert catalog.status_code == 200
    assert "backup" in catalog.json()["actions"]

    got = client.get(f"/api/users/{uid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["item"]["username"] == name

    renamed = client.put(
        f"/api/users/{uid}",
        headers=headers,
        json={"full_name": "Samantha Buyer", "email": "samantha@local"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["item"]["full_name"] == "Samantha Buyer"

    signed = client.post("/api/auth/login", json={"username": name, "password": "ChangeMe1"})
    assert signed.status_code == 200
    sheaders = {"Authorization": f"Bearer {signed.json()['access_token']}"}
    backups = client.get("/api/settings/backups", headers=sheaders)
    assert backups.status_code == 200, backups.text

    profile = client.put("/api/auth/profile", headers=sheaders, json={"full_name": "Sam B", "email": "sam.b@local"})
    assert profile.status_code == 200, profile.text
    assert profile.json()["full_name"] == "Sam B"

    pw = client.post(
        "/api/auth/password",
        headers=sheaders,
        json={"current_password": "ChangeMe1", "new_password": "ChangeMe2"},
    )
    assert pw.status_code == 200, pw.text
    again = client.post("/api/auth/login", json={"username": name, "password": "ChangeMe2"})
    assert again.status_code == 200

    admin_row = next(u for u in client.get("/api/users", headers=headers).json()["items"] if u["username"] == "admin")
    demote = client.put(f"/api/users/{admin_row['id']}", headers=headers, json={"role": "user"})
    assert demote.status_code == 400

    self_del = client.delete(f"/api/users/{admin_row['id']}", headers=headers)
    assert self_del.status_code == 400

    gone = client.delete(f"/api/users/{uid}", headers=headers)
    assert gone.status_code == 200, gone.text
    missing = client.get(f"/api/users/{uid}", headers=headers)
    assert missing.status_code == 404


def test_invalid_username_rejected():
    client, headers = _admin()
    bad = client.post(
        "/api/users",
        headers=headers,
        json={"username": "a", "password": "ChangeMe1", "role": "user"},
    )
    assert bad.status_code == 400
