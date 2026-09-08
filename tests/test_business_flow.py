from __future__ import annotations

import shutil
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import database  # noqa: E402
from app.config import AppConfig, save_config  # noqa: E402
from app.excel.service import ExcelService, excel_service  # noqa: E402
from app.main import app  # noqa: E402
from app.stats import invalidate_dash_cache  # noqa: E402


def _workbook(tmp_path):
    src = ROOT / "file.xlsx"
    dest = tmp_path / "file.xlsx"
    shutil.copy2(src, dest)
    cfg = AppConfig()
    cfg.excel_path = str(dest)
    cfg.backup_dir = str(tmp_path / "backups")
    save_config(cfg)
    svc = ExcelService()
    svc.invalidate()
    return dest, svc


def _restore():
    cfg = AppConfig()
    cfg.excel_path = str(ROOT / "file.xlsx")
    cfg.backup_dir = str(ROOT / "backups")
    save_config(cfg)


def _admin():
    database.init_db()
    excel_service.invalidate()
    invalidate_dash_cache()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_multi_item_mr_chat_suppliers_backup(tmp_path):
    dest, _svc = _workbook(tmp_path)
    try:
        client, headers = _admin()
        tag = uuid4().hex[:8]
        ping_user = f"ping_{tag}"
        created_user = client.post(
            "/api/users",
            headers=headers,
            json={
                "username": ping_user,
                "password": "pingpass99",
                "full_name": "Ping Dummy",
                "email": f"{ping_user}@woms.local",
                "role": "user",
            },
        )
        assert created_user.status_code == 200, created_user.text

        a = client.post(
            "/api/catalog/suppliers",
            headers=headers,
            json={"name": f"Audit Vendor A {tag}", "items": ["Gasket set", "AHU belt"]},
        )
        b = client.post(
            "/api/catalog/suppliers",
            headers=headers,
            json={"name": f"Audit Vendor B {tag}", "items": ["UPS module"]},
        )
        assert a.status_code == 200, a.text
        assert b.status_code == 200, b.text
        sid_a = a.json()["item"]["id"]
        sid_b = b.json()["item"]["id"]

        wo = f"AUDIT-FLOW-{tag}"
        created = client.post(
            "/api/work-orders",
            headers=headers,
            json={
                "data": {
                    "work_order_id": wo,
                    "status": "OPEN",
                    "priority": "MEDIUM",
                    "department": "SH5-SH1",
                    "description": "Dummy multi-vendor MR",
                    "lines": [
                        {
                            "supplier": f"Audit Vendor A {tag}",
                            "material": "Gasket set",
                            "qty": "2",
                            "unit": "pcs",
                            "needed_date": "2026-09-15",
                        },
                        {
                            "supplier": f"Audit Vendor B {tag}",
                            "material": "UPS module",
                            "qty": "1",
                            "unit": "ea",
                            "needed_date": "2026-09-20",
                        },
                    ],
                }
            },
        )
        assert created.status_code == 200, created.text
        item = created.json()["item"]
        rid = item["record_id"]
        lines = item.get("lines") or []
        useful = [x for x in lines if x.get("supplier") or x.get("material")]
        assert len(useful) >= 2
        suppliers = {x.get("supplier") for x in useful}
        assert f"Audit Vendor A {tag}" in suppliers
        assert f"Audit Vendor B {tag}" in suppliers

        peek = client.get(f"/api/work-orders/{rid}/chat", headers=headers)
        assert peek.status_code == 200, peek.text
        assert peek.json().get("thread") in (None, {})
        assert peek.json().get("items") == []

        listed = client.get("/api/chat/threads", headers=headers)
        assert listed.status_code == 200
        assert not any(
            t.get("kind") == "work_order" and t.get("record_id") == rid for t in listed.json().get("items") or []
        )

        remark = client.put(
            f"/api/work-orders/{rid}",
            headers=headers,
            json={"changes": {"remarks": f"Please check @ {ping_user} stock"}, "force": True},
        )
        assert remark.status_code == 200, remark.text

        chat = client.post(
            f"/api/work-orders/{rid}/chat",
            headers=headers,
            json={"body": f"Need a hand @{ping_user} on the dummy order"},
        )
        assert chat.status_code == 200, chat.text
        msg = chat.json()["item"]
        thread = chat.json()["thread"]
        assert thread and thread.get("id")
        tid = int(thread["id"])

        after = client.get(f"/api/work-orders/{rid}/chat", headers=headers)
        assert after.json().get("thread", {}).get("id") == tid
        assert any(m["id"] == msg["id"] for m in after.json()["items"])

        ping_login = client.post("/api/auth/login", json={"username": ping_user, "password": "pingpass99"})
        assert ping_login.status_code == 200, ping_login.text
        ping_headers = {"Authorization": f"Bearer {ping_login.json()['access_token']}"}
        inbox = client.get("/api/notifications", headers=ping_headers)
        assert inbox.status_code == 200, inbox.text
        bodies = " ".join(n.get("body") or "" for n in inbox.json().get("items") or [])
        assert ping_user in bodies or "mentioned" in bodies.lower() or "dummy" in bodies.lower()

        deleted_msg = client.delete(f"/api/chat/threads/{tid}/messages/{msg['id']}", headers=headers)
        assert deleted_msg.status_code == 200, deleted_msg.text
        gone = client.get(f"/api/chat/threads/{tid}/messages", headers=headers)
        assert not any(m["id"] == msg["id"] for m in gone.json()["items"])

        again = client.post(f"/api/work-orders/{rid}/chat", headers=headers, json={"body": "follow-up after delete"})
        assert again.status_code == 200, again.text
        cleared = client.delete(f"/api/chat/threads/{tid}/messages", headers=headers)
        assert cleared.status_code == 200, cleared.text
        assert client.get(f"/api/chat/threads/{tid}/messages", headers=headers).json()["items"] == []

        removed_thread = client.delete(f"/api/chat/threads/{tid}", headers=headers)
        assert removed_thread.status_code == 200, removed_thread.text
        assert client.get(f"/api/work-orders/{rid}/chat", headers=headers).json().get("thread") in (None, {})

        general = next(t for t in client.get("/api/chat/threads", headers=headers).json()["items"] if t["title"] == "General")
        blocked = client.delete(f"/api/chat/threads/{general['id']}", headers=headers)
        assert blocked.status_code == 403

        snap = client.post("/api/settings/backups", headers=headers)
        assert snap.status_code == 200, snap.text
        body = snap.json()
        assert body.get("path")
        health = body.get("health") or {}
        listed_b = client.get("/api/settings/backups", headers=headers)
        assert listed_b.status_code == 200
        items = listed_b.json().get("items") or []
        assert health.get("has_db") is True or any(i.get("has_db") for i in items)

        gone_wo = client.delete(f"/api/work-orders/{rid}", headers=headers)
        assert gone_wo.status_code == 200, gone_wo.text
        missing = client.get(f"/api/work-orders/{rid}", headers=headers)
        assert missing.status_code == 404

        del_a = client.delete(f"/api/catalog/suppliers/{sid_a}", headers=headers)
        del_b = client.delete(f"/api/catalog/suppliers/{sid_b}", headers=headers)
        assert del_a.status_code == 200, del_a.text
        assert del_b.status_code == 200, del_b.text
        names = [s.get("name") for s in client.get("/api/catalog/suppliers", headers=headers).json().get("items") or []]
        assert f"Audit Vendor A {tag}" not in names
        assert f"Audit Vendor B {tag}" not in names
    finally:
        _restore()
        dest  # keep fixture path used
