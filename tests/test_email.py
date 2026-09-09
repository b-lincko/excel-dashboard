from __future__ import annotations

import io
import sys
import urllib.error
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


def test_resend_posts_when_configured(monkeypatch):
    from app import mailer as mailer_mod

    class FakeResp:
        def read(self):
            return b'{"id":"re_test"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    captured = {}

    def fake_urlopen(req, timeout=20, context=None):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode("utf-8")
        captured["auth"] = req.headers.get("Authorization") or req.headers.get("authorization")
        return FakeResp()

    monkeypatch.setattr(mailer_mod, "_testing", lambda: False)
    monkeypatch.setattr(mailer_mod.urllib.request, "urlopen", fake_urlopen)

    class Cfg:
        email_provider = "resend"
        email_from_name = "Linkco MR"
        email_from_address = "ops@example.com"
        resend_api_key = "re_test_key"
        smtp_host = ""

    monkeypatch.setattr(mailer_mod, "load_config", lambda: Cfg())
    result = mailer_mod.send_mail("tech@example.com", "Hello", "Body text")
    assert result.get("ok") is True
    assert captured["url"] == "https://api.resend.com/emails"
    assert "re_test_key" in (captured.get("auth") or "")
    assert "ops@example.com" in captured["body"]
    assert "tech@example.com" in captured["body"]


def test_email_off_skips_send():
    mailer.OUTBOX.clear()
    invalidate_config_cache()
    cfg = load_config()
    if mailer.provider_name(cfg) != "off":
        return
    result = mailer.send_mail("person@example.com", "Hello", "Body")
    assert result.get("skipped")
    assert mailer.OUTBOX == []


_RESEND_403_BODY = (
    '{"statusCode":403,"name":"validation_error","message":"You can only send testing emails to your own email '
    'address ([linkco@spotmodapk.pro]). To send emails to other recipients, please verify a domain at '
    'resend.com/domains, and change the `from` address to an email using this domain."}'
)


def _resend_403():
    return urllib.error.HTTPError(
        "https://api.resend.com/emails",
        403,
        "Forbidden",
        {"Content-Type": "application/json"},
        io.BytesIO(_RESEND_403_BODY.encode("utf-8")),
    )


class _FakeResp:
    def read(self):
        return b'{"id":"re_test"}'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_resend_test_mode_redirects_to_owner(monkeypatch):
    """No verified domain: the app learns the owner from the 403, then delivers
    from onboarding@resend.dev to the owner with a [TEST ...] subject."""
    from app import mailer as mailer_mod

    calls = []

    def fake_urlopen(req, timeout=20, context=None):
        calls.append(req)
        if len(calls) == 1:
            raise _resend_403()
        return _FakeResp()

    saved = {}

    class Cfg:
        email_provider = "resend"
        email_from_name = "Linkco MR"
        email_from_address = "mr@linkco.com.qa"
        resend_api_key = "re_test_key"
        smtp_host = ""
        resend_test_inbox = ""

    monkeypatch.setattr(mailer_mod, "_testing", lambda: False)
    monkeypatch.setattr(mailer_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mailer_mod, "load_config", lambda: Cfg())
    monkeypatch.setattr(mailer_mod, "save_config", lambda cfg: saved.update(resend_test_inbox=cfg.resend_test_inbox))

    result = mailer_mod.send_mail("manager@example.com", "PO request", "Body text")
    assert result.get("ok") is True
    assert result.get("test_mode") is True
    assert result.get("to") == "linkco@spotmodapk.pro"
    assert result.get("intended_to") == "manager@example.com"
    assert len(calls) == 2
    second = calls[1].data.decode("utf-8")
    assert "onboarding@resend.dev" in second
    assert "linkco@spotmodapk.pro" in second
    assert "[TEST" in second and "manager@example.com" in second
    assert saved.get("resend_test_inbox") == "linkco@spotmodapk.pro"


def test_resend_test_mode_uses_known_inbox(monkeypatch):
    """A saved test inbox is reused even when the error body is not parsable."""
    from app import mailer as mailer_mod

    calls = []

    def fake_urlopen(req, timeout=20, context=None):
        calls.append(req)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                "https://api.resend.com/emails",
                403,
                "Forbidden",
                {"Content-Type": "application/json"},
                io.BytesIO(b'{"statusCode":403,"message":"please verify a domain at resend.com/domains"}'),
            )
        return _FakeResp()

    class Cfg:
        email_provider = "resend"
        email_from_name = "Linkco MR"
        email_from_address = "mr@linkco.com.qa"
        resend_api_key = "re_test_key"
        smtp_host = ""
        resend_test_inbox = "owner@spotmodapk.pro"

    monkeypatch.setattr(mailer_mod, "_testing", lambda: False)
    monkeypatch.setattr(mailer_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mailer_mod, "load_config", lambda: Cfg())
    monkeypatch.setattr(mailer_mod, "save_config", lambda cfg: None)

    result = mailer_mod.send_mail("owner@spotmodapk.pro", "Hello", "Body")
    assert result.get("ok") is True
    assert result.get("test_mode") is True
    assert result.get("to") == "owner@spotmodapk.pro"
    body = calls[1].data.decode("utf-8")
    assert "onboarding@resend.dev" in body
    # Recipient was already the owner - delivered as addressed.
    assert '"to": ["owner@spotmodapk.pro"]' in body
