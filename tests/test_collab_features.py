from __future__ import annotations

import base64
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
from app.main import app  # noqa: E402
from app.stats import employee_performance  # noqa: E402


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

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _admin(workbook):
    database.init_db()
    excel_service.invalidate()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_sqlite_cache_and_performance(workbook):
    _, svc = workbook
    recs = svc.get_all(force=True)
    assert database.wo_cache_count() == len(recs)
    cached = database.load_wo_cache()
    assert len(cached) == len(recs)
    assert cached[0]["record_id"]
    perf = employee_performance(recs)
    assert perf["kpis"]["total"] == len(recs)
    assert perf["employees"]
    client, headers = _admin(workbook)
    res = client.get("/api/dashboard/performance", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kpis"]["total"] == len(recs)
    assert body["employees"]
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["cache"] == len(recs)


def test_chat_projects_attachments_import(workbook):
    client, headers = _admin(workbook)
    threads = client.get("/api/chat/threads", headers=headers)
    assert threads.status_code == 200
    general = next(t for t in threads.json()["items"] if t["title"] == "General")
    posted = client.post(f"/api/chat/threads/{general['id']}/messages", headers=headers, json={"body": "Hello team"})
    assert posted.status_code == 200, posted.text
    msgs = client.get(f"/api/chat/threads/{general['id']}/messages", headers=headers)
    assert any(m["body"] == "Hello team" for m in msgs.json()["items"])

    dm = client.post("/api/chat/threads", headers=headers, json={"kind": "direct", "username": "manager"})
    assert dm.status_code == 200, dm.text
    assert dm.json()["item"]["kind"] == "direct"

    proj = client.post(
        "/api/projects",
        headers=headers,
        json={"name": "Gatepass catch-up", "owner": "admin", "description": "Clear NTP backlog"},
    )
    assert proj.status_code == 200, proj.text
    pid = proj.json()["item"]["id"]
    task = client.post(f"/api/projects/{pid}/tasks", headers=headers, json={"title": "Call suppliers"})
    assert task.status_code == 200
    recs = excel_service.get_all()
    rid = recs[0]["record_id"]
    linked = client.post(f"/api/projects/{pid}/links", headers=headers, json={"record_id": rid})
    assert linked.status_code == 200
    assert any(l["record_id"] == rid for l in linked.json()["item"]["links"])

    attach = client.post(
        f"/api/work-orders/{rid}/files",
        headers=headers,
        files={"file": ("shot.png", PNG, "image/png")},
        data={"note": "Delay screenshot"},
    )
    assert attach.status_code == 200, attach.text
    listed = client.get(f"/api/work-orders/{rid}/files", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["filename"] == "shot.png"
    aid = listed.json()["items"][0]["id"]
    dl = client.get(f"/api/files/{aid}", headers=headers)
    assert dl.status_code == 200
    assert dl.content[:8] == b"\x89PNG\r\n\x1a\n"

    before = len(excel_service.get_all())
    csv_body = "IM Work Order #,STATUS,Assign to,Required Material Details,REMARKS / NOTES\nCSV-TEST-001,OPEN,pytest,Imported gasket set,From CSV\n"
    imported = client.post(
        "/api/transfer/import",
        headers=headers,
        files={"file": ("rows.csv", csv_body.encode("utf-8"), "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["created"] == 1
    assert body["updated"] == 0
    assert len(excel_service.get_all(force=True)) == before + 1
    exported = client.get("/api/transfer/export.csv", headers=headers)
    assert exported.status_code == 200
    assert b"CSV-TEST-001" in exported.content
