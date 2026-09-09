from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import approvals, database, mailer  # noqa: E402
from app import config as config_mod  # noqa: E402
from app.config import invalidate_config_cache, load_config, save_config  # noqa: E402
from app.main import app  # noqa: E402


def _setup_db(tmp_path, monkeypatch, name="ping.db"):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / name)
    database.init_db()


def _make_rec(rid="TEST:PO-PING", wo="483001", po="PO-PING"):
    rec = {
        "record_id": rid,
        "work_order_id": wo,
        "po_number": po,
        "status": "PLACED",
        "supplier": "AAGE",
        "assigned_to": "",
    }
    database.upsert_wo_record(rec)
    return rec


def _actors():
    return (
        database.get_user_by_username("abubacar"),
        database.get_user_by_username("nesar"),
        database.get_user_by_username("manager"),
    )


def _bodies(username):
    return [str(n.get("body") or "") for n in database.list_notifications(username, limit=100)]


def test_follow_up_pings_manager_then_cooldown(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    rec = _make_rec()
    abu, nesar, manager = _actors()
    approvals.assign(rec, abu, "Nesar")
    rec = database.get_wo_record(rec["record_id"])
    approvals.submit(rec, nesar)
    rec = database.get_wo_record(rec["record_id"])

    # The technician (assignee) follows up with the manager who must sign.
    out = approvals.follow_up(rec, nesar, note="Please sign today")
    assert any(ev["action"] == "ping" for ev in out["events"])
    assert any("Please sign today" in ev["comment"] for ev in out["events"] if ev["action"] == "ping")
    assert any("followed up" in body and "waiting for your signature" in body for body in _bodies("manager"))

    # Cooldown blocks an immediate second nudge.
    try:
        approvals.follow_up(rec, abu, note="again")
        raise AssertionError("cooldown should block a second follow-up")
    except approvals.PingCooldown:
        pass

    # The manager is the target, not a follower-upper.
    try:
        approvals.follow_up(rec, manager)
        raise AssertionError("manager should not be able to follow up their own signature")
    except PermissionError:
        pass

    caps = approvals.capabilities(abu, rec, approvals.approval_for(rec))
    assert caps["can_ping"] is True
    assert caps["ping_label"] == "the manager(s) who must sign"
    assert caps["last_ping_at"]
    assert caps["ping_cooldown_minutes"] >= 0


def test_follow_up_state_rules(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch, "ping-states.db")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "app_config.json")
    invalidate_config_cache()
    cfg = load_config()
    cfg.po_ping_cooldown_minutes = 0  # this test walks every state on one record
    save_config(cfg)
    invalidate_config_cache()

    rec = _make_rec("TEST:PO-PING-2", "483002", "PO-PING-2")
    abu, nesar, manager = _actors()

    # Nothing assigned yet.
    try:
        approvals.follow_up(rec, abu)
        raise AssertionError("empty state should refuse follow-up")
    except ValueError:
        pass

    approvals.assign(rec, abu, "Nesar")
    rec = database.get_wo_record(rec["record_id"])
    # Assigned: the dispatcher can nudge the technician.
    out = approvals.follow_up(rec, abu)
    assert any("assigned to you" not in body and "followed up" in body for body in _bodies("nesar"))
    assert out["state"] == "assigned"

    approvals.submit(rec, nesar)
    rec = database.get_wo_record(rec["record_id"])
    signed = approvals.decide(rec, manager, approve=True, signature_png="data:image/png;base64,aaaa")
    assert signed["state"] == "approved"
    rec = database.get_wo_record(rec["record_id"])
    # Approved: holder (Nesar) gets the nudge so the slip moves on.
    approvals.follow_up(rec, abu)
    assert any("you hold the signed slip" in body for body in _bodies("nesar"))

    approvals.send_accounts(rec, abu)
    rec = database.get_wo_record(rec["record_id"])
    try:
        approvals.follow_up(rec, abu)
        raise AssertionError("sent_to_accounts should refuse follow-up")
    except ValueError:
        pass
    caps = approvals.capabilities(abu, rec, approvals.approval_for(rec))
    assert caps["can_ping"] is False


def test_ping_api_and_follow_up_email(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch, "ping-api.db")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "app_config.json")
    invalidate_config_cache()
    cfg = load_config()
    cfg.email_provider = "smtp"
    cfg.smtp_host = "smtp.example.com"
    cfg.email_from_address = "ops@example.com"
    save_config(cfg)
    invalidate_config_cache()

    manager = database.get_user_by_username("manager")
    database.update_user(manager["id"], email="manager@example.com")

    rec = _make_rec("TEST:PO-PING-3", "483003", "PO-PING-3")
    abu, nesar, _manager = _actors()
    approvals.assign(rec, abu, "Nesar")
    rec = database.get_wo_record(rec["record_id"])
    approvals.submit(rec, nesar)

    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    mailer.OUTBOX.clear()

    url = f"/api/work-orders/{rec['record_id']}/approval/ping"
    ok = client.post(url, headers=headers, json={"note": "Delivery is waiting"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["caps"]["can_ping"] is True
    assert any(ev["action"] == "ping" for ev in body["approval"]["events"])
    assert any(
        m["to"] == "manager@example.com" and "follow-up" in str(m.get("subject") or "").lower()
        for m in mailer.OUTBOX
    )

    again = client.post(url, headers=headers, json={"note": "spam"})
    assert again.status_code == 429
    assert "follow-up was sent" in str(again.json().get("detail") or "")

    # A stranger cannot follow up someone else's slip (the slip is waiting for
    # a signature; "user" is not the dispatcher, assignee, holder or coordinator).
    client2 = TestClient(app)
    token2 = client2.post("/api/auth/login", json={"username": "user", "password": "user123"}).json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}
    rec2 = _make_rec("TEST:PO-PING-4", "483004", "PO-PING-4")
    approvals.assign(rec2, abu, "Nesar")
    rec2 = database.get_wo_record(rec2["record_id"])
    approvals.submit(rec2, nesar)
    refused = client2.post(f"/api/work-orders/{rec2['record_id']}/approval/ping", headers=headers2, json={})
    assert refused.status_code == 403
