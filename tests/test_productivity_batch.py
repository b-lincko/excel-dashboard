from __future__ import annotations

import shutil
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import database, security  # noqa: E402
from app.config import AppConfig, save_config  # noqa: E402
from app.dates import parse_date  # noqa: E402
from app.domain import is_stale, today  # noqa: E402
from app.escalation import run_escalation  # noqa: E402
from app.excel.service import ExcelService  # noqa: E402


@pytest.fixture()
def workbook(tmp_path):
    src = ROOT / "file.xlsx"
    dest = tmp_path / "file.xlsx"
    shutil.copy2(src, dest)
    cfg = AppConfig()
    cfg.excel_path = str(dest)
    cfg.backup_dir = str(tmp_path / "backups")
    save_config(cfg)
    svc = ExcelService()
    svc.invalidate()
    yield dest, svc
    cfg = AppConfig()
    cfg.excel_path = str(ROOT / "file.xlsx")
    cfg.backup_dir = str(ROOT / "backups")
    save_config(cfg)
    svc.invalidate()


@pytest.fixture()
def client(workbook, tmp_path, monkeypatch):
    db = tmp_path / "woms.db"
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    monkeypatch.setattr(security, "enforce_password_change", lambda: False)
    from app.main import app

    c = TestClient(app)
    token = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    c.headers.update({"Authorization": f"Bearer {token}"})
    yield c


def _open_rec(work_order_id: str, **over):
    rec = {
        "work_order_id": work_order_id,
        "status": "OPEN",
        "description": "test MR",
        "created_date": today().isoformat(),
        "due_date": (today() + timedelta(days=10)).isoformat(),
        "supplier": "DupSupplier",
    }
    rec.update(over)
    return rec


def test_export_csv_and_xlsx(client):
    r = client.get("/api/work-orders", params={"fmt": "csv"})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    body = r.content.decode("utf-8-sig")
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert len(lines) >= 2  # header + at least one row
    assert "work order" in lines[0].lower()  # workbook display headers

    r = client.get("/api/work-orders", params={"fmt": "xlsx"})
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]

    # fmt unset -> normal JSON list
    r = client.get("/api/work-orders")
    assert r.status_code == 200
    assert r.json().get("items") is not None


def test_duplicate_warning_flow(client):
    data = _open_rec("DUP-TEST-1")
    r = client.post("/api/work-orders", json={"data": data})
    assert r.status_code == 200, r.text

    # same work_order_id + supplier within the window -> 409 with duplicates
    r = client.post("/api/work-orders", json={"data": _open_rec("DUP-TEST-1")})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["duplicates"], "expected at least one duplicate"
    assert any(d["work_order_id"] == "DUP-TEST-1" for d in detail["duplicates"])

    # different supplier -> no warning
    r = client.post("/api/work-orders", json={"data": _open_rec("DUP-TEST-1", supplier="OtherCo")})
    assert r.status_code == 200

    # confirm_duplicate -> allowed through
    r = client.post(
        "/api/work-orders",
        json={"data": _open_rec("DUP-TEST-1"), "confirm_duplicate": True},
    )
    assert r.status_code == 200


def test_is_stale_semantics():
    cfg = AppConfig()
    old_due = (today() - timedelta(days=10)).isoformat()
    near_due = (today() - timedelta(days=2)).isoformat()
    assert is_stale({"status": "OPEN", "due_date": old_due}, cfg) is True
    assert is_stale({"status": "OPEN", "due_date": near_due}, cfg) is False
    assert is_stale({"status": "OPEN", "due_date": ""}, cfg) is False
    assert is_stale({"status": "CLOSED", "due_date": old_due}, cfg) is False
    # placed: stale counts from the ETA (closed_date)
    assert is_stale({"status": "PLACED", "closed_date": old_due}, cfg) is True
    cfg7 = AppConfig()
    cfg7.stale_after_days = 30
    assert is_stale({"status": "OPEN", "due_date": old_due}, cfg7) is False


def test_escalation_pings_once_per_cooldown(client, workbook):
    _, svc = workbook
    cfg_cfg = AppConfig()
    cfg_cfg.escalate_after_days = 7
    save_config(cfg_cfg)

    recs = svc.get_all()
    target = recs[0]
    rid = str(target["record_id"])
    svc.update_record(
        rid,
        {
            "status": "OPEN",
            "due_date": (today() - timedelta(days=15)).isoformat(),
            "assigned_to": "Nesar",
        },
        username="pytest",
    )

    out = run_escalation("pytest")
    assert out["checked"] >= 1
    assert out["pinged"] >= 1  # the workbook has stale records with seeded assignees
    assert database.last_notification_at("escalate", rid) is not None

    # cooldown: immediately again -> no second ping
    out2 = run_escalation("pytest")
    assert out2["pinged"] == 0

    # no assignee match -> never pinged
    svc.update_record(str(recs[1]["record_id"]), {"status": "OPEN", "due_date": (today() - timedelta(days=15)).isoformat(), "assigned_to": "Nobody Real"}, username="pytest")
    run_escalation("pytest")
    assert database.last_notification_at("escalate", str(recs[1]["record_id"])) is None


def test_options_include_delay_reasons(client):
    r = client.get("/api/work-orders/options")
    assert r.status_code == 200
    data = r.json()
    opts = data.get("options", data)
    reasons = opts.get("delay_reason_options")
    assert isinstance(reasons, list) and reasons, "delay_reason_options must be exposed"
    assert any("Supplier" in str(x) for x in reasons)
