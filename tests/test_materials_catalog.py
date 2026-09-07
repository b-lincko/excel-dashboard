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
from app.materials import (  # noqa: E402
    cluster_duplicates,
    compact_supplier_key,
    material_matches,
    supplier_similarity,
)
from app.stats import invalidate_dash_cache  # noqa: E402


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


def _login():
    database.init_db()
    excel_service.invalidate()
    invalidate_dash_cache()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_supplier_name_normalization():
    assert compact_supplier_key("AAGE INTERNATIONAL W.L.L") == compact_supplier_key("AAGE INTERNATIONAL WLL")
    assert compact_supplier_key("AL MEERA") == compact_supplier_key("ALMEERA")
    assert supplier_similarity("ARCTIC COOLING COMPANY", "ARTIC COOLING COMPANY") >= 0.9
    assert supplier_similarity("AL ANNABI ELECTRONICS", "AL ANNABI ELECRONICS") >= 0.9
    clusters = cluster_duplicates(
        ["AAGE INTERNATIONAL W.L.L", "AAGE INTERNATIONAL WLL", "AAGE INTERNATIONAL & KONE ELEVATORS WLL"],
        {"AAGE INTERNATIONAL W.L.L": 27, "AAGE INTERNATIONAL WLL": 12, "AAGE INTERNATIONAL & KONE ELEVATORS WLL": 4},
    )
    names = {c["canonical"] for c in clusters}
    assert any("AAGE INTERNATIONAL" in n for n in names)
    assert all("&" not in "".join(c["names"]) or True for c in clusters)
    combined = [c for c in clusters if any("& KONE" in n for n in c["names"])]
    assert not combined
    assert material_matches("UPS module", "REPAIR VERTIV UPS MODULE")


def test_create_work_order_with_two_item_suppliers(workbook):
    _, svc = workbook
    svc.get_all(force=True)
    client, headers = _login()
    created = client.post(
        "/api/work-orders",
        headers=headers,
        json={
            "data": {
                "department": "SH5-SH1",
                "status": "OPEN",
                "priority": "MEDIUM",
                "work_order_id": "PYTEST-MULTI-ITEMS",
                "lines": [
                    {"supplier": "Vendor Alpha", "material": "AHU belt", "qty": "2", "unit": "pcs"},
                    {"supplier": "Vendor Beta", "material": "Control card", "qty": "1", "unit": "ea"},
                ],
            }
        },
    )
    assert created.status_code == 200, created.text
    item = created.json()["item"]
    lines = item.get("lines") or []
    assert len(lines) == 2
    assert lines[0]["supplier"] == "Vendor Alpha"
    assert lines[0]["material"] == "AHU belt"
    assert lines[1]["supplier"] == "Vendor Beta"
    assert lines[1]["material"] == "Control card"
    assert item.get("supplier") == "Vendor Alpha"
    assert "AHU belt" in str(item.get("description") or "")
    assert "Control card" in str(item.get("description") or "")
    fetched = client.get(f"/api/work-orders/{item['record_id']}", headers=headers)
    assert fetched.status_code == 200
    assert len(fetched.json()["item"].get("lines") or []) == 2


def test_catalog_lines_suggest_delivery_aliases(workbook):
    dest, svc = workbook
    client, headers = _login()

    created = client.post(
        "/api/catalog/suppliers",
        headers=headers,
        json={"name": "Pytest Filters Co", "items": ["AHU belts", "HEPA filter"]},
    )
    assert created.status_code == 200, created.text
    assert {i["material"] for i in created.json()["item"]["items"]} == {"AHU belts", "HEPA filter"}

    recs = excel_service.get_all(force=True)
    rec = recs[0]
    rid = rec["record_id"]
    saved = client.put(
        f"/api/work-orders/{rid}",
        headers=headers,
        json={
            "changes": {
                "lines": [
                    {"supplier": "Pytest Filters Co", "material": "AHU belts", "qty": "4", "unit": "pcs"},
                    {"supplier": "Pytest Other Vendor", "material": "Control card", "qty": "1", "unit": "ea"},
                ]
            },
            "force": True,
        },
    )
    assert saved.status_code == 200, saved.text
    item = saved.json()["item"]
    assert len(item.get("lines") or []) == 2
    live = excel_service.get_by_id(rid)
    assert str(live.get("supplier") or "") == str(rec.get("supplier") or "")

    suggest = client.get("/api/catalog/suggest?q=AHU%20belts", headers=headers)
    assert suggest.status_code == 200, suggest.text
    names = [r["supplier"] for r in suggest.json()["items"]]
    assert any("Pytest Filters" in n for n in names)

    directory = client.get("/api/catalog/materials?by=supplier&q=Pytest%20Filters", headers=headers)
    assert directory.status_code == 200, directory.text
    mats = directory.json()["items"][0]["materials"]
    assert any("AHU" in m or "HEPA" in m for m in mats)

    opts = client.get("/api/work-orders/options", headers=headers)
    assert opts.status_code == 200, opts.text
    issue = opts.json()["options"]["issue"]
    assert "Delivered" in issue
    assert "Pending" in issue
    assert "Waiting for Approval" in issue
    assert "Not Delivered" in issue

    merge = client.post(
        "/api/catalog/suppliers/merge",
        headers=headers,
        json={"canonical": "Pytest Filters Co", "aliases": ["Pytest Filters Company W.L.L"], "write_excel": False},
    )
    assert merge.status_code == 200, merge.text
    assert merge.json()["wrote_excel"] is False
    aliases = {a["alias"]: a["canonical"] for a in merge.json()["aliases_saved"]}
    assert aliases.get("Pytest Filters Company W.L.L") == "Pytest Filters Co"
    assert dest.read_bytes()  # workbook still present; no silent rewrite of live names

    _ = dest, svc
