from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import AppConfig, save_config, load_config  # noqa: E402
from app.dates import parse_date  # noqa: E402
from app.domain import is_closed, is_open, is_overdue  # noqa: E402
from app.excel.service import ExcelService  # noqa: E402
from app.stats import kpis  # noqa: E402
from app.validation import validate_work_order  # noqa: E402


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


def test_excel_exists():
    assert (ROOT / "file.xlsx").exists()


def test_read_work_orders(workbook):
    _, svc = workbook
    recs = svc.get_all(force=True)
    assert len(recs) >= 2000
    rec = recs[0]
    assert rec["work_order_id"]
    assert rec["record_id"]
    assert rec["status"]
    assert rec["_sheet"] in {"Linkco_MR_Log (SH5 & SH1)", "Linkco_MR_Log (F5)"}
    assert rec["department"] in {"SH5-SH1", "F5"}
    assert parse_date(rec["created_date"]) is not None or rec["created_date"] == ""


def test_unique_record_ids(workbook):
    _, svc = workbook
    recs = svc.get_all(force=True)
    ids = [r["record_id"] for r in recs]
    assert len(ids) == len(set(ids))
    # IM WO # may repeat (multiple MRs per work order)
    assert len({r["work_order_id"] for r in recs}) < len(recs)


def test_kpis_match_records(workbook):
    _, svc = workbook
    recs = svc.get_all(force=True)
    k = kpis(recs)
    assert k["total"] == len(recs)
    assert k["closed"] == sum(1 for r in recs if is_closed(r))
    assert k["open"] == sum(1 for r in recs if is_open(r))
    assert k["open"] + k["closed"] == k["total"]
    assert k["overdue"] == sum(1 for r in recs if is_overdue(r))
    assert 0 <= k["completion_rate"] <= 100


def test_update_writes_excel(workbook):
    path, svc = workbook
    recs = svc.get_all(force=True)
    target = next(r for r in recs if is_open(r))
    rid = target["record_id"]
    updated = svc.update_record(rid, {"remarks": "Updated by automated test"}, username="pytest")
    assert updated["remarks"] == "Updated by automated test"
    again = svc.get_by_id(rid)
    assert again["remarks"] == "Updated by automated test"


def test_create_appends_row(workbook):
    _, svc = workbook
    before = len(svc.get_all(force=True))
    created = svc.create_record(
        {
            "description": "Test create from pytest",
            "status": "OPEN",
            "priority": "MEDIUM",
            "department": "F5",
            "work_type": "Local PO",
        },
        username="pytest",
    )
    assert created["work_order_id"]
    recs = svc.get_all(force=True)
    assert len(recs) == before + 1
    assert sum(1 for r in recs if r["record_id"] == created["record_id"]) == 1


def test_validation_close_before_create():
    errors = validate_work_order(
        {
            "description": "x",
            "status": "CLOSED",
            "created_date": "2026-09-05 10:00",
            "closed_date": "2026-09-01 10:00",
        }
    )
    assert any("Closing date" in e for e in errors)


def test_auth_and_dashboard(workbook):
    from app.main import app
    from app import database

    database.init_db()
    client = TestClient(app)
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert ok.status_code == 200
    token = ok.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    dash = client.get("/api/dashboard", headers=headers)
    assert dash.status_code == 200
    body = dash.json()
    assert body["kpis"]["total"] > 2000
    assert body["mindmap"]["root"]["value"] == body["kpis"]["total"]
    assert body["mindmap"]["branches"]
    assert body.get("recent") is not None
    assert body.get("options")
    again = client.get("/api/dashboard", headers=headers)
    assert again.status_code == 200
    layout = client.put("/api/auth/layout", headers=headers, json={"widgets": [{"id": "kpis_today", "type": "kpis_today", "span": "full"}]})
    assert layout.status_code == 200
    got = client.get("/api/auth/layout", headers=headers)
    assert got.status_code == 200
    assert got.json()["widgets"][0]["type"] == "kpis_today"
    wos = client.get("/api/work-orders?page_size=10", headers=headers)
    assert wos.status_code == 200
    assert wos.json()["total"] > 2000
    # Empty-filter dashboard used to request /api/work-orders&page_size=… (404).
    glued = client.get("/api/work-orders&page_size=8&sort=created_date", headers=headers)
    assert glued.status_code == 404
    ok_list = client.get("/api/work-orders?page_size=8&sort=created_date", headers=headers)
    assert ok_list.status_code == 200
    assert len(ok_list.json()["items"]) == 8
    health = client.get("/api/health")
    assert health.status_code == 200


def test_upload_scans_workbook(workbook):
    from app.main import app
    from app import database
    from app.excel.service import excel_service

    database.init_db()
    excel_service.invalidate()
    path, _ = workbook
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    content = path.read_bytes()
    res = client.post(
        "/api/sync/upload",
        headers=headers,
        files={"file": ("file.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["sync"]["record_count"] > 2000
    assert body["mindmap"]["root"]["value"] == body["sync"]["record_count"]
    reject = client.post(
        "/api/sync/upload",
        headers=headers,
        files={"file": ("notes.txt", b"not-an-excel-file", "text/plain")},
    )
    assert reject.status_code == 400


def test_ping_and_week_filter(workbook):
    from app.main import app
    from app import database
    from app.excel.service import excel_service

    database.init_db()
    excel_service.invalidate()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    ping = client.get("/api/sync/ping", headers=headers)
    assert ping.status_code == 200
    body = ping.json()
    assert body["synchronized"] is True
    assert body["record_count"] > 2000
    assert body["sync_token"]
    again = client.get("/api/sync/ping", headers=headers)
    assert again.json()["sync_token"] == body["sync_token"]
    week = client.get("/api/work-orders?year=2026&week=36&page_size=5", headers=headers)
    assert week.status_code == 200
    weekly = client.get("/api/dashboard/weekly?year=2026&week=36", headers=headers)
    assert weekly.status_code == 200
    assert weekly.json()["kpis"]["total"] == week.json()["total"]


def test_ops_queue_and_suppliers(workbook):
    from app.main import app
    from app import database
    from app.excel.service import excel_service
    from app.domain import is_ntp, is_open, is_overdue, is_pending_po

    database.init_db()
    excel_service.invalidate()
    _, svc = workbook
    recs = svc.get_all(force=True)
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    queue = client.get("/api/ops/queue", headers=headers)
    assert queue.status_code == 200
    body = queue.json()
    assert body["counts"]["overdue"] == sum(1 for r in recs if is_overdue(r))
    assert body["counts"]["ntp"] == sum(1 for r in recs if is_ntp(r) and is_open(r))
    assert "overdue" in body["queues"]
    ntp = client.get("/api/work-orders?flag=ntp&page_size=5", headers=headers)
    assert ntp.status_code == 200
    assert ntp.json()["total"] == body["counts"]["ntp"]
    suppliers = client.get("/api/ops/suppliers", headers=headers)
    assert suppliers.status_code == 200
    sbody = suppliers.json()
    assert sbody["kpis"]["pending_po"] == sum(1 for r in recs if is_pending_po(r))
    assert sbody["suppliers"]
    pending = client.get("/api/work-orders?flag=pending_po&page_size=5", headers=headers)
    assert pending.status_code == 200
    assert pending.json()["total"] == sbody["kpis"]["pending_po"]


def test_preserve_other_sheets(workbook):
    from openpyxl import load_workbook
    from openpyxl.worksheet.formula import ArrayFormula

    path, svc = workbook
    recs = svc.get_all(force=True)
    target = recs[0]
    svc.update_record(target["record_id"], {"remarks": "sheet-preserve"}, username="pytest")
    wb = load_workbook(path)
    assert "Linkco_MR_Log (SH5 & SH1)" in wb.sheetnames
    assert "Linkco_MR_Log (F5)" in wb.sheetnames
    assert "SH1 & SH5 - REPORT" in wb.sheetnames
    ws = wb["Linkco_MR_Log (SH5 & SH1)"]
    assert str(ws["L1"].value).startswith("=")
    assert str(ws["A4"].value).startswith("=")
    assert isinstance(ws["H4"].value, ArrayFormula) or str(ws["H4"].value).startswith("=")
    wb.close()
