"""Material request form: the 9-column line table (2026-09-13).

Columns: S/N (row number), part model number, material description,
technical specification, unit model number/details, brand, required
quantity, UOM, remarks/notes — plus supplier and date needed (kept for
vendor flows). New fields must survive normalize -> persist -> list.
"""
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
from app.materials import normalize_lines, persist_work_order_lines  # noqa: E402
from app.stats import invalidate_dash_cache  # noqa: E402


@pytest.fixture()
def env(tmp_path):
    src = ROOT / "file.xlsx"
    dest = tmp_path / "file.xlsx"
    shutil.copy2(src, dest)
    cfg = AppConfig()
    cfg.excel_path = str(dest)
    cfg.backup_dir = str(tmp_path / "backups")
    save_config(cfg)
    database.init_db()  # runs the column migration for part_model/tech_spec/unit_model/brand
    excel_service.invalidate()
    invalidate_dash_cache()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    yield client, {"Authorization": f"Bearer {token}"}
    cfg = AppConfig()
    cfg.excel_path = str(ROOT / "file.xlsx")
    cfg.backup_dir = str(ROOT / "backups")
    save_config(cfg)


LINE = {
    "supplier": "Vendor One",
    "part_model": "A123-45",
    "material": "Gate valve",
    "tech_spec": "DN50 PN16 flanged",
    "unit_model": "A123/50",
    "brand": "BrandsX",
    "qty": "12",
    "unit": "pcs",
    "notes": "for line 2",
}


def test_normalize_lines_carries_new_fields():
    out = normalize_lines([dict(LINE)])
    assert out[0]["part_model"] == "A123-45"
    assert out[0]["tech_spec"] == "DN50 PN16 flanged"
    assert out[0]["unit_model"] == "A123/50"
    assert out[0]["brand"] == "BrandsX"
    # unknown keys are still dropped
    out2 = normalize_lines([dict(LINE, evil="x")])
    assert "evil" not in out2[0]


def test_persist_and_list_roundtrip():
    cleaned = persist_work_order_lines("MR-LINE-1", "WO-LINE-1", [dict(LINE)], username="admin")
    assert cleaned[0]["brand"] == "BrandsX"
    rows = database.list_mr_lines("MR-LINE-1")
    assert rows[0]["part_model"] == "A123-45"
    assert rows[0]["tech_spec"] == "DN50 PN16 flanged"
    assert rows[0]["unit_model"] == "A123/50"
    assert rows[0]["brand"] == "BrandsX"


def test_api_save_and_fetch_new_line_fields(env):
    client, headers = env
    r = client.post(
        "/api/work-orders",
        json={"data": {"lines": [dict(LINE)], "description": "valve package", "status": "Pending"}, "confirm_duplicate": True},
        headers=headers,
    )
    assert r.status_code in {200, 201}, r.text
    rid = (r.json().get("item") or {}).get("record_id")
    assert rid
    got = client.get(f"/api/work-orders/{rid}", headers=headers).json()
    lines = got["item"]["lines"] if "item" in got else got["lines"]
    assert lines[0]["part_model"] == "A123-45"
    assert lines[0]["unit_model"] == "A123/50"
    assert lines[0]["brand"] == "BrandsX"


def test_legacy_lines_without_new_fields_still_work(env):
    client, headers = env
    legacy = {"supplier": "Vendor Two", "material": "Gasket", "qty": "5", "unit": "box"}
    r = client.post("/api/work-orders", json={"data": {"lines": [legacy], "description": "gasket set", "status": "Pending"}, "confirm_duplicate": True}, headers=headers)
    assert r.status_code in {200, 201}, r.text
    rid = (r.json().get("item") or {}).get("record_id")
    got = client.get(f"/api/work-orders/{rid}", headers=headers).json()
    lines = got["item"]["lines"] if "item" in got else got["lines"]
    assert lines[0]["material"] == "Gasket"
    assert lines[0]["part_model"] == ""
