from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402
from app import database, mailer  # noqa: E402
from app.config import AppConfig, invalidate_config_cache, load_config, save_config  # noqa: E402
from app import config as config_mod  # noqa: E402


def _admin():
    database.init_db()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_settings_never_returns_mail_secrets(tmp_path, monkeypatch):
    path = tmp_path / "app_config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", path)
    invalidate_config_cache()
    cfg = load_config()
    cfg.email_provider = "smtp"
    cfg.email_from_address = "ops@example.com"
    cfg.smtp_host = "smtp.example.com"
    cfg.smtp_password = "smtp-secret"
    cfg.resend_api_key = "re_secret"
    save_config(cfg)
    client, headers = _admin()
    got = client.get("/api/settings", headers=headers)
    assert got.status_code == 200, got.text
    data = got.json()["settings"]
    assert "smtp_password" not in data
    assert "resend_api_key" not in data
    assert "jwt_secret" not in data
    assert data.get("smtp_password_set") is True
    assert data.get("resend_api_key_set") is True
    keep = client.put("/api/settings", headers=headers, json={"values": {"email_provider": "smtp", "smtp_password": ""}})
    assert keep.status_code == 200, keep.text
    invalidate_config_cache()
    again = load_config()
    assert again.smtp_password == "smtp-secret"
    invalidate_config_cache()


def test_verify_link_and_request_email(tmp_path, monkeypatch):
    db = tmp_path / "mail.db"
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    path = tmp_path / "app_config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", path)
    invalidate_config_cache()
    cfg = load_config()
    cfg.email_provider = "smtp"
    cfg.email_from_address = "ops@example.com"
    cfg.smtp_host = "smtp.example.com"
    cfg.email_public_url = "https://mr.example.com"
    save_config(cfg)
    mailer.OUTBOX.clear()
    client, headers = _admin()
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "mailuser",
            "password": "ChangeMe1",
            "full_name": "Mail User",
            "email": "tech@example.com",
            "role": "user",
        },
    )
    assert created.status_code == 200, created.text
    assert any(m["to"] == "tech@example.com" and "verify" in (m.get("url") or "") for m in mailer.OUTBOX)
    verify_url = next(m["url"] for m in mailer.OUTBOX if "verify-email" in (m.get("url") or ""))
    token = verify_url.split("token=")[-1]
    done = client.post("/api/auth/verify-email", json={"token": token})
    assert done.status_code == 200, done.text
    user = database.get_user_by_username("mailuser")
    assert user and user.get("email_verified")
    mailer.OUTBOX.clear()
    rec = {
        "record_id": "TEST:MAIL-1",
        "work_order_id": "9001",
        "assigned_to": "Mail User",
    }
    from app import notify

    notify.notify_assignment("admin", rec, previous="")
    assert any(m["to"] == "tech@example.com" and "9001" in (m.get("text") or "") for m in mailer.OUTBOX)
    mailer.OUTBOX.clear()
    forgot = client.post("/api/auth/forgot", json={"username": "mailuser"})
    assert forgot.status_code == 200
    reset = next(m for m in mailer.OUTBOX if "reset-password" in (m.get("url") or ""))
    rtoken = reset["url"].split("token=")[-1]
    pw = client.post("/api/auth/reset-password", json={"token": rtoken, "new_password": "ChangeMe9"})
    assert pw.status_code == 200, pw.text
    signed = client.post("/api/auth/login", json={"username": "mailuser", "password": "ChangeMe9"})
    assert signed.status_code == 200
    skipped = mailer.send_mail("admin@woms.local", "x", "y")
    assert skipped.get("skipped")
    invalidate_config_cache()


def test_email_off_skips_send():
    mailer.OUTBOX.clear()
    invalidate_config_cache()
    cfg = load_config()
    if mailer.provider_name(cfg) != "off":
        return
    result = mailer.send_mail("person@example.com", "Hello", "Body")
    assert result.get("skipped")
    assert mailer.OUTBOX == []
