from __future__ import annotations

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
    sent = approvals.send_accounts(rec, abu)
    assert sent["state"] == "sent_to_accounts"
    pdf = po_approval_pdf(rec, approvals.approval_for(rec))
    assert pdf[:4] == b"%PDF"
