from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import database  # noqa: E402
from app.config import AppConfig, save_config  # noqa: E402
from app.excel.service import ExcelService, excel_service  # noqa: E402


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


def _admin():
    database.init_db()
    excel_service.invalidate()
    client = TestClient(__import__("app.main", fromlist=["app"]).app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_load_without_force_keeps_database(workbook):
    _, svc = workbook
    recs = svc.get_all(force=True)
    target = recs[0]
    rid = target["record_id"]
    patched = dict(target)
    patched["remarks"] = "db-sot-keep"
    database.upsert_wo_record(patched)
    svc.invalidate()
    again = svc.get_all()
    hit = next(r for r in again if r["record_id"] == rid)
    assert hit["remarks"] == "db-sot-keep"
    ping = svc.ping()
    assert ping["source"] == "database"
    assert ping["record_count"] == len(again)


def test_save_keeps_db_when_excel_missing(workbook):
    from app.excel.service import ExcelUnavailable

    _, svc = workbook
    recs = svc.get_all(force=True)
    rid = recs[0]["record_id"]

    def boom(*_a, **_k):
        raise ExcelUnavailable("Excel file is currently unavailable.")

    svc._excel_update_record = boom  # type: ignore[method-assign]
    updated = svc.update_record(rid, {"remarks": "db-first-no-excel"}, username="pytest")
    assert updated["remarks"] == "db-first-no-excel"
    assert updated.get("_excel_backup_ok") is False
    assert "unavailable" in str(updated.get("_excel_backup_error") or "").lower()
    stored = database.get_wo_record(rid)
    assert stored["remarks"] == "db-first-no-excel"


def test_seed_and_reset_confirm(workbook):
    dest, _ = workbook
    client, headers = _admin()
    refused = client.post("/api/settings/database/reset", headers=headers, json={"confirm": "nope"})
    assert refused.status_code == 400
    seeded = client.post("/api/settings/database/seed", headers=headers)
    assert seeded.status_code == 200, seeded.text
    body = seeded.json()
    assert body["ok"] is True
    assert body["count"] >= 2000
    status = client.get("/api/settings/database", headers=headers)
    assert status.status_code == 200
    assert status.json()["record_count"] >= 2000
    ping = client.get("/api/sync/ping", headers=headers)
    assert ping.json()["source"] == "database"
    refresh = client.post("/api/sync/refresh", headers=headers)
    assert refresh.status_code == 200
    assert refresh.json()["hard"] is True
    assert refresh.json()["source"] == "database"
    # Upload uses the same tmp workbook; must not 500.
    content = dest.read_bytes()
    uploaded = client.post(
        "/api/settings/database/upload",
        headers=headers,
        files={"file": ("file.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["ok"] is True


def test_manual_backup_pairs_database(workbook):
    _, svc = workbook
    recs = svc.get_all(force=True)
    rid = recs[0]["record_id"]
    original = str(recs[0].get("remarks") or "")
    path = svc.create_backup(reason="manual")
    assert path is not None and path.suffix.lower() == ".xlsx"
    dbp = path.with_suffix(".db")
    assert dbp.is_file()
    items = svc.list_backups()
    hit = next(i for i in items if i["path"] == str(path))
    assert hit["has_db"] is True
    patched = dict(database.get_wo_record(rid))
    patched["remarks"] = "after-snapshot-marker"
    database.upsert_wo_record(patched)
    write_only = svc.create_backup(reason="update")
    assert write_only is not None
    assert not write_only.with_suffix(".db").exists()
    result = svc.restore_backup(str(path))
    assert result["database"] is True
    assert result["excel"] is True
    stored = database.get_wo_record(rid)
    assert stored["remarks"] != "after-snapshot-marker"
    assert stored["remarks"] == original


def test_excel_only_restore_does_not_seed_db(workbook):
    _, svc = workbook
    recs = svc.get_all(force=True)
    rid = recs[0]["record_id"]
    path = svc.create_backup(reason="update")
    assert path is not None
    assert not path.with_suffix(".db").exists()
    patched = dict(database.get_wo_record(rid))
    patched["remarks"] = "live-db-must-stay"
    database.upsert_wo_record(patched)
    result = svc.restore_backup(str(path))
    assert result["excel"] is True
    assert result["database"] is False
    stored = database.get_wo_record(rid)
    assert stored["remarks"] == "live-db-must-stay"
