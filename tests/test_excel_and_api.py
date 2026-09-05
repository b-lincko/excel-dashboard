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
    wos = client.get("/api/work-orders?page_size=10", headers=headers)
    assert wos.status_code == 200
    assert wos.json()["total"] > 2000
    health = client.get("/api/health")
    assert health.status_code == 200


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
