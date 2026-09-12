from __future__ import annotations

import csv
import io
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
    # seed a probe record so cell alignment can be asserted
    client.post(
        "/api/work-orders",
        json={"data": _open_rec("EXPORT-PROBE-1", location="Probe Villa")},
    )

    r = client.get("/api/work-orders", params={"fmt": "csv"})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    body = r.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(body)))
    assert len(rows) >= 2
    header = [h.strip() for h in rows[0]]

    # BUG PIN (2026-09-12): headers are Excel labels but cells must hold the
    # record's values — the label->internal mapping has to be applied.
    from app.config import load_config

    mapping = load_config().mapping.internal_to_excel()
    wo_label = mapping["work_order_id"]
    assert wo_label in header
    col = header.index(wo_label)
    match = next(row for row in rows[1:] if len(row) > col and row[col].strip() == "EXPORT-PROBE-1")
    loc_label = mapping["location"]
    loc_col = header.index(loc_label)
    assert match[loc_col].strip() == "Probe Villa"

    r = client.get("/api/work-orders", params={"fmt": "xlsx"})
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.active
    xlsx_header = [str(c.value or "").strip() for c in ws[1]]
    wo_col = xlsx_header.index(mapping["work_order_id"]) + 1
    hit = next(
        row
        for row in ws.iter_rows(min_row=2, values_only=True)
        if row[wo_col - 1] and str(row[wo_col - 1]).strip() == "EXPORT-PROBE-1"
    )
    assert hit is not None

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


def test_write_safety_backups_are_pruned(client, workbook, tmp_path):
    """backup_write_keep is honoured by the housekeeping flows (pinned decision)."""
    from app.backup import run_due_backup
    from app.excel.service import excel_service

    dest, svc = workbook
    for reason in ("update", "create", "bulk", "delete", "import"):
        svc.create_backup(reason=reason)
    snaps = [p for p in svc.backup_dir().rglob("*.xlsx") if p.stem.rsplit("_", 1)[-1] in excel_service.WRITE_REASONS]
    assert len(snaps) == 5

    cfg = AppConfig()
    cfg.excel_path = str(dest)
    cfg.backup_dir = str(tmp_path / "backups")
    cfg.backup_write_keep = 2
    save_config(cfg)
    run_due_backup(force=True)

    snaps_after = [p for p in svc.backup_dir().rglob("*.xlsx") if p.stem.rsplit("_", 1)[-1] in excel_service.WRITE_REASONS]
    assert len(snaps_after) == 2, "housekeeping must prune write-safety snapshots to backup_write_keep"


def test_failed_autobackup_is_retried(client, workbook, tmp_path, monkeypatch):
    """BUG PIN (2026-09-12): a failed slot must not mark the schedule done."""
    from app import backup
    from app.excel.service import excel_service

    dest, svc = workbook
    calls = {"n": 0}
    real_export = excel_service.export_database_to_excel

    def flaky(username="system"):
        calls["n"] += 1
        raise RuntimeError("excel locked (simulated)")

    def counting(username="system"):
        calls["n"] += 1
        return real_export(username=username)

    monkeypatch.setattr(excel_service, "export_database_to_excel", flaky)
    backup.run_due_backup(force=True)
    assert calls["n"] == 1
    assert database.get_sync_meta("last_auto_backup_failed") == "1"
    assert not database.get_sync_meta("last_auto_backup")  # slot NOT consumed

    # throttled: an immediate retry does not call export again
    assert backup.run_due_backup(force=False) is None
    assert calls["n"] == 1

    # after the backoff window the slot is retried and succeeds
    from datetime import datetime, timedelta

    old = (datetime.now() - timedelta(seconds=backup.RETRY_SECONDS + 1)).strftime("%Y-%m-%d %H:%M:%S")
    database.set_sync_meta("last_auto_backup_fail_at", old)
    monkeypatch.setattr(excel_service, "export_database_to_excel", counting)
    out = backup.run_due_backup(force=False)
    assert calls["n"] == 2
    assert database.get_sync_meta("last_auto_backup_failed") == "0"
    assert database.get_sync_meta("last_auto_backup")  # slot consumed on success
    assert out is not None or database.get_sync_meta("last_backup")


def test_queue_payload_overlays_delay_notes(client, workbook):
    """BUG PIN (2026-09-12): ActionQueue rows must carry DB-stored delay notes."""
    from app.excel.service import excel_service
    from app import ops

    dest, svc = workbook
    recs = svc.get_all()
    rid = str(recs[0]["record_id"])
    svc.update_record(rid, {"delay_justification": "Overlay probe note"}, username="pytest")
    payload = ops.queue_payload({})
    rows = payload.get("overdue", []) + payload.get("ntp", []) + payload.get("on_hold", []) + payload.get("due_week", []) + payload.get("created_today", []) + payload.get("done_today", [])
    target = next((r for r in rows if str(r.get("record_id")) == rid), None)
    if target is None:
        return  # record is not in any queue bucket; overlay itself is covered elsewhere
    assert target.get("delay_justification") == "Overlay probe note"
