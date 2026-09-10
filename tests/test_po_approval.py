from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import approvals, database  # noqa: E402
from app.config import AppConfig  # noqa: E402
from app.domain import is_delayed, is_overdue  # noqa: E402
from app.excel.service import ExcelService  # noqa: E402
from app.reports import po_approval_pdf  # noqa: E402


def test_technicians_exclude_admin_and_manager():
    database.init_db()
    names = {n.lower() for n in approvals.technician_names()}
    assert "nesar" in names
    assert "arun" in names
    assert "abubacar" in names
    assert "admin" not in names
    assert "operations manager" not in names
    assert approvals.assignee_allowed("Nesar") is True
    assert approvals.assignee_allowed("admin") is False
    assert approvals.assignee_allowed("Operations Manager") is False
    assert approvals.assignee_allowed("") is True
    assert approvals.assignee_allowed("Legacy Name", current="Legacy Name") is True


def test_placed_overdue_uses_eta_not_due_date():
    cfg = AppConfig()
    rec = {"status": "PLACED", "due_date": "2000-01-01", "closed_date": "2099-01-01"}
    assert is_overdue(rec, cfg) is False
    assert is_delayed(rec, cfg) is False
    rec["closed_date"] = "2000-01-01"
    assert is_overdue(rec, cfg) is True
    assert is_delayed(rec, cfg) is False


def test_manual_due_date_when_purchase_type_empty():
    svc = ExcelService()
    rec = {"created_date": "2026-09-01", "work_type": "", "due_date": "2026-09-20"}
    svc._apply_due_date(rec)
    assert rec["due_date"].startswith("2026-09-20")
    rec2 = {"created_date": "2026-09-01", "work_type": "Local PO", "due_date": "2026-09-20"}
    svc._apply_due_date(rec2)
    assert rec2["due_date"] == "2026-09-06"


def test_po_assign_submit_approve_lock(tmp_path, monkeypatch):
    db = tmp_path / "po.db"
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    rec = {
        "record_id": "TEST:PO-1",
        "work_order_id": "481999",
        "po_number": "PO-1",
        "status": "PLACED",
        "assigned_to": "Nesar",
        "unit_price": "10",
        "price": "10",
        "total_price": "10",
        "final_price": "12",
    }
    database.upsert_wo_record(rec)
    abu = database.get_user_by_username("abubacar")
    assert abu
    extras = str(abu.get("extra_permissions") or "")
    assert "po_dispatch" in extras or approvals.has_perm(abu, "po_dispatch")
    assigned = approvals.assign(rec, abu, "Nesar")
    assert assigned["state"] == "assigned"
    nesar = database.get_user_by_username("nesar")
    submitted = approvals.submit(rec, nesar)
    assert submitted["state"] == "submitted"
    manager = database.get_user_by_username("manager")
    try:
        approvals.decide(rec, manager, approve=True, signature_png="")
        raise AssertionError("unsigned approve should fail")
    except ValueError:
        pass
    signed = approvals.decide(rec, manager, approve=True, signature_png="data:image/png;base64,aaaa")
    assert signed["state"] == "approved"
    assert signed["locked"] in (1, True)
    assert approvals.is_locked(rec) is True
    assert approvals.locked_fields({"po_number": "X"}, rec) == ["po_number"]
    # accounts step is opt-in since 2026-09-10; enable it for this legacy flow
    monkeypatch.setattr(approvals, "accounts_enabled", lambda: True)
    sent = approvals.send_accounts(rec, abu)
    assert sent["state"] == "sent_to_accounts"
    pdf = po_approval_pdf(rec, approvals.approval_for(rec))
    assert pdf[:4] == b"%PDF"


def test_inbox_lanes_and_resubmit(tmp_path, monkeypatch):
    db = tmp_path / "po-inbox.db"
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    rec = {
        "record_id": "TEST:PO-INBOX",
        "work_order_id": "482000",
        "po_number": "PO-IN",
        "status": "PLACED",
        "supplier": "AAGE",
        "assigned_to": "",
    }
    database.upsert_wo_record(rec)
    abu = database.get_user_by_username("abubacar")
    nesar = database.get_user_by_username("nesar")
    manager = database.get_user_by_username("manager")
    incoming = approvals.inbox(abu)
    assert any(i["record_id"] == rec["record_id"] for i in incoming["lanes"]["incoming"])
    hidden = approvals.inbox(nesar)
    assert not any(i["record_id"] == rec["record_id"] for lane in hidden["lanes"].values() for i in lane)
    approvals.assign(rec, abu, "Nesar")
    rec = database.get_wo_record(rec["record_id"])
    mine = approvals.inbox(nesar)
    assert any(i["record_id"] == rec["record_id"] for i in mine["lanes"]["assigned"])
    approvals.submit(rec, nesar)
    rec = database.get_wo_record(rec["record_id"])
    waiting = approvals.inbox(manager)
    assert any(i["record_id"] == rec["record_id"] for i in waiting["lanes"]["to_sign"])
    denied = approvals.decide(rec, manager, approve=False, comment="Fix qty")
    assert denied["state"] == "changes_requested"
    try:
        approvals.decide(rec, manager, approve=True, signature_png="data:image/png;base64,aaaa")
        raise AssertionError("approve without resubmit should fail")
    except ValueError:
        pass
    approvals.submit(rec, nesar)
    signed = approvals.decide(rec, manager, approve=True, signature_png="data:image/png;base64,aaaa")
    assert signed["state"] == "approved"
    ready = approvals.inbox(abu)
    assert any(i["record_id"] == rec["record_id"] for i in ready["lanes"]["ready"])


def test_unassign_managers_and_route(tmp_path, monkeypatch):
    db = tmp_path / "po-route.db"
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    rec = {
        "record_id": "TEST:PO-ROUTE",
        "work_order_id": "482100",
        "po_number": "PO-R",
        "status": "PLACED",
        "assigned_to": "Nesar",
    }
    database.upsert_wo_record(rec)
    abu = database.get_user_by_username("abubacar")
    nesar = database.get_user_by_username("nesar")
    manager = database.get_user_by_username("manager")
    approvals.assign(rec, abu, "Nesar")
    cleared = approvals.unassign(rec, abu)
    assert cleared["state"] == "none"
    assert not cleared.get("assignee")
    approvals.assign(rec, abu, "Nesar")
    sent = approvals.submit(rec, nesar, managers=["manager"])
    assert sent["state"] == "submitted"
    assert "manager" in str(sent.get("managers") or "")
    signed = approvals.decide(
        rec, manager, approve=True, signature_png="data:image/png;base64,aaaa", return_to="nesar"
    )
    assert signed["state"] == "approved"
    assert str(signed.get("holder") or "").lower() == "nesar"
    routed = approvals.route(rec, nesar, "abubacar")
    assert str(routed.get("holder") or "").lower() == "abubacar"
    # accounts step is opt-in since 2026-09-10; enable it for this legacy flow
    monkeypatch.setattr(approvals, "accounts_enabled", lambda: True)
    sent_acc = approvals.send_accounts(rec, abu, to="admin")
    assert sent_acc["state"] == "sent_to_accounts"

def test_unassign_route_and_dispatcher_submit(tmp_path, monkeypatch):
    """Regression: the unassign endpoint must exist, the submit endpoint must
    honor the picked managers, and a dispatcher/admin may submit (not only the
    assignee technician)."""
    from fastapi.testclient import TestClient

    from app.main import app

    db = tmp_path / "po-routes.db"
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    rec = {
        "record_id": "TEST:PO-ROUTES",
        "work_order_id": "484000",
        "po_number": "PO-ROUTES",
        "status": "PLACED",
        "supplier": "AAGE",
        "assigned_to": "",
    }
    database.upsert_wo_record(rec)
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/work-orders/{rec['record_id']}/approval"

    assigned = client.post(f"{base}/assign", headers=headers, json={"assignee": "Nesar"})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["approval"]["state"] == "assigned"
    # Admin counts as a dispatcher: the send-to-managers step must be visible.
    assert assigned.json()["caps"]["can_submit"] is True

    submitted = client.post(f"{base}/submit", headers=headers, json={"managers": ["manager"]})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["approval"]["state"] == "submitted"
    assert submitted.json()["approval"]["manager_list"] == ["manager"]

    # A technician who is not involved cannot unassign (403, not 405).
    tech_token = client.post("/api/auth/login", json={"username": "arun", "password": "arun1234"}).json()["access_token"]
    tech_headers = {"Authorization": f"Bearer {tech_token}"}
    forbidden = client.post(f"{base}/unassign", headers=tech_headers)
    assert forbidden.status_code == 403

    unassigned = client.post(f"{base}/unassign", headers=headers)
    assert unassigned.status_code == 200, unassigned.text
    assert unassigned.json()["approval"]["state"] == "none"

def test_approval_pdf_embeds_drawn_signature():
    """Regression: reportlab 5.x rejected the ImageReader passed to platypus
    Image (silent except -> 'No signature on file yet' on a signed slip), and
    the signature-line HRFlowable used an unparsable "80mm" width. A signed
    slip must embed the drawn signature as an image; an unsigned one must not."""
    import base64

    from PIL import Image, ImageDraw

    from app.reports import _signature_image, po_approval_pdf

    img = Image.new("RGB", (400, 140), "white")
    ImageDraw.Draw(img).line([(20, 70), (120, 30), (220, 100), (380, 50)], fill=(15, 23, 42), width=4, joint="curve")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    assert _signature_image(data_url) is not None
    assert _signature_image("") is None
    assert _signature_image("data:image/png;base64,!!!not-png!!!") is None

    rec = {"record_id": "TEST:SIGPDF", "work_order_id": "485000", "po_number": "PO-SIG"}
    signed = po_approval_pdf(rec, {"state": "approved", "signed_by": "manager", "signed_at": "2026-09-10 10:00:00", "signature_png": data_url})
    unsigned = po_approval_pdf(rec, {"state": "submitted"})
    assert signed[:4] == b"%PDF" and unsigned[:4] == b"%PDF"
    assert b"/Subtype /Image" in signed or b"/Subtype/Image" in signed, "drawn signature missing from signed PDF"
    assert b"/Subtype /Image" not in unsigned and b"/Subtype/Image" not in unsigned


def test_route_return_to_and_mine_views(tmp_path, monkeypatch):
    """Regression for the desk 'Method Not Allowed': the frontend posts
    /approval/route but the router endpoint never existed, and /approval/decide
    dropped return_to (recipient choice ignored). Also covers the personal
    inbox views: to_sign / sent (with ping info) / signed."""
    db = tmp_path / "po-route.db"
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    rec = {
        "record_id": "TEST:PO-ROUTE",
        "work_order_id": "486001",
        "po_number": "PO-ROUTE",
        "status": "PLACED",
        "supplier": "AAGE",
        "assigned_to": "",
    }
    database.upsert_wo_record(rec)
    abu = database.get_user_by_username("abubacar")
    nesar = database.get_user_by_username("nesar")
    manager = database.get_user_by_username("manager")

    # the 405 fix: the route endpoint must be registered on the work-orders router
    from app.routers import work_orders as wo_router_module

    rpaths = {getattr(r, "path", "") for r in wo_router_module.router.routes}
    assert "/api/work-orders/{wo_id}/approval/route" in rpaths
    assert "/api/work-orders/{wo_id}/approval/decide" in rpaths

    approvals.assign(rec, abu, "Nesar")
    rec = database.get_wo_record(rec["record_id"])
    approvals.submit(rec, nesar)
    rec = database.get_wo_record(rec["record_id"])

    # personal views while waiting for signature
    m_inbox = approvals.inbox(manager)
    assert any(i["record_id"] == rec["record_id"] for i in m_inbox["mine"]["to_sign"])
    n_inbox = approvals.inbox(nesar)
    sent = [i for i in n_inbox["mine"]["sent"] if i["record_id"] == rec["record_id"]]
    assert sent and sent[0]["ping"]["can"] is True
    assert "sign" in (sent[0]["ping"]["target"] or "")
    assert n_inbox["mine_counts"]["sent"] >= 1

    # decide must honour return_to (recipient dropdown), not ignore it
    signed = approvals.decide(
        rec, manager, approve=True, signature_png="data:image/png;base64,aaaa", return_to="Abubacar"
    )
    assert signed["state"] == "approved"
    assert signed["holder"] == "abubacar"
    rec = database.get_wo_record(rec["record_id"])

    # signed slip lands in the holder's and the signer's personal views
    for usr in (abu, manager):
        inx = approvals.inbox(usr)
        assert any(i["record_id"] == rec["record_id"] for i in inx["mine"]["signed"]), usr

    # passing the signed slip on: approvals.route + holder change
    routed = approvals.route(rec, abu, "Nesar")
    assert routed["state"] == "approved" and routed["locked"] in (1, True)
    assert routed["holder"] == "nesar"
    nesar_inx = approvals.inbox(nesar)
    assert any(i["record_id"] == rec["record_id"] for i in nesar_inx["mine"]["signed"])

    # a technician who does not hold the slip cannot route it
    arun = database.get_user_by_username("arun")
    try:
        approvals.route(rec, arun, "Nesar")
        raise AssertionError("route by a non-holder should fail")
    except (PermissionError, ValueError):
        pass


def test_accounts_step_toggle(tmp_path, monkeypatch):
    """Accounts step is OFF by default ('remove accounts for now'): the lane
    disappears from the inbox, the action is blocked with guidance, and a
    signed slip is terminal. Admins re-enable it in Settings (po_accounts_process)."""
    import pytest

    from app import config as config_mod

    db = tmp_path / "po-accounts.db"
    monkeypatch.setattr(database, "DB_PATH", db)
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "app_config.json")
    config_mod.invalidate_config_cache()
    database.init_db()
    rec = {
        "record_id": "TEST:PO-ACC",
        "work_order_id": "486010",
        "po_number": "PO-ACC",
        "status": "PLACED",
        "supplier": "AAGE",
    }
    database.upsert_wo_record(rec)
    abu = database.get_user_by_username("abubacar")
    manager = database.get_user_by_username("manager")

    assert approvals.accounts_enabled() is False
    approvals.assign(rec, abu, "Nesar")
    rec = database.get_wo_record(rec["record_id"])
    approvals.submit(rec, database.get_user_by_username("nesar"))
    rec = database.get_wo_record(rec["record_id"])
    approvals.decide(rec, manager, approve=True, signature_png="data:image/png;base64,aaaa", return_to="Abubacar")
    rec = database.get_wo_record(rec["record_id"])

    # off (default): no accounts lane/count, action blocked, nothing deleted
    inx = approvals.inbox(abu)
    assert "accounts" not in inx["lanes"] and "accounts" not in inx["counts"]
    assert inx["accounts_enabled"] is False
    caps = approvals.capabilities(abu, rec, approvals.approval_for(rec))
    assert caps["can_send_accounts"] is False
    with pytest.raises(ValueError, match="switched off"):
        approvals.send_accounts(rec, abu)
    # routing to a colleague still works while the step is off
    assert approvals.route(rec, abu, "Nesar")["holder"] == "nesar"

    # on: lane returns (data kept), action allowed, filing works
    cfg = config_mod.load_config()
    cfg.po_accounts_process = True
    config_mod.save_config(cfg)
    assert approvals.accounts_enabled() is True
    sent = approvals.send_accounts(rec, abu)
    assert sent["state"] == "sent_to_accounts"
    inx2 = approvals.inbox(abu)
    assert inx2["accounts_enabled"] is True
    assert "accounts" in inx2["lanes"]
    assert any(i["record_id"] == rec["record_id"] for i in inx2["lanes"]["accounts"])
