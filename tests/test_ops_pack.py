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
from app.validation import (  # noqa: E402
    status_change_remark_error,
    status_transition_needs_remark,
    validate_work_order,
)


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


def test_status_remark_rules_unit():
    cfg = AppConfig()
    cfg.status_change_remarks = ["*->ON HOLD", "*->CLOSED"]
    assert status_transition_needs_remark("OPEN", "ON HOLD", cfg)
    assert status_transition_needs_remark("OPEN", "CLOSED", cfg)
    assert not status_transition_needs_remark("OPEN", "OPEN", cfg)
    assert not status_transition_needs_remark("OPEN", "PLACED", cfg)
    assert status_change_remark_error("OPEN", "ON HOLD", "", cfg)
    assert status_change_remark_error("OPEN", "ON HOLD", "waiting site", cfg) is None


def test_claim_digest_timeline_mapping_similar_cards_backup(workbook):
    dest, svc = workbook
    client, headers = _login("admin", "admin123")
    recs = excel_service.get_all(force=True)
    assert recs
    rec = recs[0]
    for row in recs:
        status = str(row.get("status") or "").strip().upper()
        if status in {"ON HOLD", "CLOSED", "CLOSE"}:
            continue
        probe = {**row, "status": "ON HOLD", "remarks": "pytest hold remark"}
        if not validate_work_order(probe, partial=False):
            rec = row
            break
    rid = rec["record_id"]

    scan = client.get("/api/settings/mapping-scan", headers=headers)
    assert scan.status_code == 200, scan.text
    body = scan.json()
    assert body["headers"]
    assert "work_order_id" in body["mapping"]
    assert "suggestions" in body

    similar = client.get("/api/ops/similar", headers=headers)
    assert similar.status_code == 200, similar.text
    assert "items" in similar.json()

    digest = client.get("/api/ops/digest", headers=headers)
    assert digest.status_code == 200, digest.text
    djson = digest.json()
    assert "overdue" in djson["counts"]
    assert "ntp" in djson["counts"]
    assert "due_soon" in djson["counts"]
    assert len(djson["sections"]) == 3

    pdf = client.get("/api/ops/digest?fmt=pdf", headers=headers)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content[:4] == b"%PDF"

    blocked = client.put(
        f"/api/work-orders/{rid}",
        headers=headers,
        json={"changes": {"status": "ON HOLD"}, "force": True},
    )
    assert blocked.status_code == 422, blocked.text
    detail = blocked.json().get("detail")
    text = " ".join(detail) if isinstance(detail, list) else str(detail)
    assert "remark" in text.lower()

    held = client.put(
        f"/api/work-orders/{rid}",
        headers=headers,
        json={"changes": {"status": "ON HOLD", "remarks": "pytest hold remark"}, "force": True},
    )
    assert held.status_code == 200, held.text
    assert str(held.json()["item"].get("status") or "").upper() == "ON HOLD"

    claimed = client.post(f"/api/work-orders/{rid}/claim?force=true", headers=headers)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["item"]["assigned_to"]
    excel_service.invalidate()
    live = excel_service.get_by_id(rid)
    assert str(live.get("assigned_to") or "").strip()

    chat = client.post(f"/api/work-orders/{rid}/chat", headers=headers, json={"body": "pytest timeline chat"})
    assert chat.status_code == 200, chat.text
    feed = client.get(f"/api/work-orders/{rid}/timeline", headers=headers)
    assert feed.status_code == 200, feed.text
    kinds = {e.get("kind") for e in feed.json()["items"]}
    assert "chat" in kinds
    assert "field" in kinds or "seen" in kinds

    created = client.post("/api/catalog/suppliers", headers=headers, json={"name": "pytest-card-supplier"})
    assert created.status_code == 200, created.text
    sid = created.json()["item"]["id"]
    saved = client.put(
        f"/api/catalog/suppliers/{sid}",
        headers=headers,
        json={"phone": "555-0100", "lead_time_days": 7, "notes": "card notes", "contact": "Sam"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["item"]["phone"] == "555-0100"
    assert saved.json()["item"]["lead_time_days"] == 7

    backup = client.post("/api/settings/backups", headers=headers)
    assert backup.status_code == 200, backup.text
    path = backup.json()["path"]
    health = backup.json().get("health") or client.post(
        "/api/settings/backups/check", headers=headers, json={"path": path}
    ).json()
    assert health["ok"] is True
    assert health["backup_count"] == health["live_count"] or health["backup_count"] >= 1

    _ = dest, svc
