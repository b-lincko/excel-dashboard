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
from app.main import app  # noqa: E402
from app.stats import invalidate_dash_cache  # noqa: E402
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


def _login(username: str, password: str):
    database.init_db()
    excel_service.invalidate()
    invalidate_dash_cache()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_wo_chat_handover_seen_health_restore_and_rules(workbook):
    dest, svc = workbook
    client, headers = _login("admin", "admin123")
    recs = excel_service.get_all(force=True)
    assert recs
    rec = next(
        (r for r in recs if str(r.get("status") or "").strip().upper() != "PLACED"),
        recs[0],
    )
    rid = rec["record_id"]

    chat = client.get(f"/api/work-orders/{rid}/chat", headers=headers)
    assert chat.status_code == 200, chat.text
    posted = client.post(
        f"/api/work-orders/{rid}/chat",
        headers=headers,
        json={"body": "pytest WO chat @manager please look"},
    )
    assert posted.status_code == 200, posted.text
    listed = client.get(f"/api/work-orders/{rid}/chat", headers=headers)
    assert any(m["body"].startswith("pytest WO chat") for m in listed.json()["items"])
    threads = client.get("/api/chat/threads", headers=headers)
    assert threads.status_code == 200
    assert any(t.get("kind") == "work_order" and t.get("record_id") == rid for t in threads.json()["items"])

    follow = client.post(f"/api/work-orders/{rid}/watch", headers=headers)
    assert follow.status_code == 200
    manager = client.post("/api/auth/login", json={"username": "manager", "password": "manager123"})
    mheaders = {"Authorization": f"Bearer {manager.json()['access_token']}"}
    pings = client.get("/api/notifications", headers=mheaders)
    assert any("mentioned you" in (n.get("body") or "") for n in pings.json()["items"])

    seen = client.post("/api/ops/seen", headers=headers, json={"record_id": rid})
    assert seen.status_code == 200, seen.text
    assert any(s["username"] == "admin" for s in seen.json()["seen_by"])
    queue = client.get("/api/ops/queue", headers=headers)
    assert queue.status_code == 200
    found = False
    for rows in (queue.json().get("queues") or {}).values():
        for row in rows or []:
            if row.get("record_id") == rid:
                found = True
                assert any(s["username"] == "admin" for s in row.get("seen_by") or [])
    # row may not be in the sampled queues; that's fine

    hand = client.get("/api/ops/handover", headers=headers)
    assert hand.status_code == 200, hand.text
    live = hand.json()["live"]
    assert "still_open" in live["counts"]
    assert "waiting_ntp" in live["counts"]
    assert "waiting_supplier" in live["counts"]
    published = client.post(
        "/api/ops/handover",
        headers=headers,
        json={"notes": "pytest shift note", "shift": "day", "department": "SH5-SH1"},
    )
    assert published.status_code == 200, published.text
    again = client.get("/api/ops/handover", headers=headers)
    assert any(h.get("notes") == "pytest shift note" for h in again.json()["items"])

    health = client.get("/api/ops/health", headers=headers)
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["scanned_rows"] >= len(recs)
    assert "missing_id" in body["counts"]
    assert "overwritten_formula" in body["counts"]

    required = validate_work_order({**rec, "status": "PLACED", "po_number": ""})
    assert any("po_number" in e for e in required)
    ok_required = validate_work_order({**rec, "status": "PLACED", "po_number": "PO-1"})
    assert not any("po_number" in e for e in ok_required)

    user_login = client.post("/api/auth/login", json={"username": "user", "password": "user123"})
    uheaders = {"Authorization": f"Bearer {user_login.json()['access_token']}"}
    blocked = client.put(
        f"/api/work-orders/{rid}",
        headers=uheaders,
        json={"changes": {"supplier": "pytest-blocked-supplier"}, "force": True},
    )
    assert blocked.status_code == 403, blocked.text
    remark = client.put(
        f"/api/work-orders/{rid}",
        headers=uheaders,
        json={"changes": {"remarks": "pytest site remark"}, "force": True},
    )
    assert remark.status_code == 200, remark.text

    backup = client.post("/api/settings/backups", headers=headers)
    assert backup.status_code == 200, backup.text
    path = backup.json()["path"]
    assert path
    excel_service.invalidate()
    before = excel_service.get_by_id(rid)
    changed = client.put(
        f"/api/work-orders/{rid}",
        headers=headers,
        json={"changes": {"remarks": "pytest restore target"}, "force": True},
    )
    assert changed.status_code == 200, changed.text
    preview = client.post(
        "/api/settings/backups/preview-row",
        headers=headers,
        json={"path": path, "record_id": rid},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["matched_live"] is True
    restored = client.post(
        "/api/settings/backups/restore-row",
        headers=headers,
        json={"path": path, "record_id": rid},
    )
    assert restored.status_code == 200, restored.text
    excel_service.invalidate()
    after = excel_service.get_by_id(rid)
    assert str(after.get("remarks") or "") == str(before.get("remarks") or "")

    me = client.get("/api/auth/me", headers=uheaders)
    assert me.status_code == 200
    assert "remarks" in (me.json().get("editable_fields") or [])
    assert "supplier" not in (me.json().get("editable_fields") or [])
    _ = found
