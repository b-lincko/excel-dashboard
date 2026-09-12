from __future__ import annotations

import io
import shutil
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import database, security  # noqa: E402
from app.config import AppConfig, save_config  # noqa: E402
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


def _create_mr(client, wo="ATTACH-1"):
    r = client.post(
        "/api/work-orders",
        json={
            "data": {
                "work_order_id": wo,
                "status": "OPEN",
                "description": "attachment probe",
                "created_date": "2026-09-12",
                "due_date": "2026-09-30",
            }
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["item"]


def _tiny_pdf(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in text.splitlines():
        page.insert_text((72, y), line, fontsize=11)
        y += 16
    data = doc.tobytes()
    doc.close()
    return data


def _tiny_xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Quotation"
    ws.append(["Item", "Qty", "Unit price"])
    ws.append(["Cement bag", 40, 12.5])
    ws.append(["Steel pipe", 6, 88])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _tiny_docx(text: str) -> bytes:
    xml = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in text.splitlines())
        + "</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
)


def test_upload_scans_pdf_into_copyable_text(client):
    item = _create_mr(client)
    rid = item["record_id"]
    pdf = _tiny_pdf("MATERIAL REQUEST\nSupplier: Gulf Supplies\nItem: Cement bag x 40\nTotal: 1,250 QAR")
    r = client.post(
        f"/api/work-orders/{rid}/files",
        files={"file": ("quotation.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"note": "supplier quote"},
    )
    assert r.status_code == 200, r.text
    meta = r.json()["item"]
    assert meta["has_extract"] is True
    assert meta["extract_ok"] is True
    assert meta["extract_words"] >= 8

    r = client.get(f"/api/files/{meta['id']}/content")
    assert r.status_code == 200
    data = r.json()
    assert data["item"]["filename"] == "quotation.pdf"
    assert "Gulf Supplies" in data["extract"]["text"]
    assert data["extract"]["engine"] == "pymupdf"


def test_upload_excel_becomes_table(client):
    item = _create_mr(client, wo="ATTACH-2")
    rid = item["record_id"]
    r = client.post(
        f"/api/work-orders/{rid}/files",
        files={"file": ("prices.xlsx", io.BytesIO(_tiny_xlsx()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"note": ""},
    )
    assert r.status_code == 200, r.text
    meta = r.json()["item"]
    assert meta["extract_tables"] >= 1
    r = client.get(f"/api/files/{meta['id']}/content")
    sheets = r.json()["extract"]["sheets"]
    assert sheets and sheets[0]["name"] == "Quotation"
    assert ["Item", "Qty", "Unit price"] == sheets[0]["rows"][0]
    assert "Cement bag" in sheets[0]["rows"][1]


def test_upload_docx_and_csv(client):
    item = _create_mr(client, wo="ATTACH-3")
    rid = item["record_id"]
    r = client.post(
        f"/api/work-orders/{rid}/files",
        files={"file": ("spec.docx", io.BytesIO(_tiny_docx("Scope of work\nSupply and install lighting")), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"note": ""},
    )
    assert r.status_code == 200, r.text
    meta = r.json()["item"]
    assert meta["extract_ok"] is True
    r = client.get(f"/api/files/{meta['id']}/content")
    assert "Supply and install lighting" in r.json()["extract"]["text"]

    r = client.post(
        f"/api/work-orders/{rid}/files",
        files={"file": ("items.csv", io.BytesIO(b"material,qty\nPaint,12\n"), "text/csv")},
        data={"note": ""},
    )
    assert r.status_code == 200, r.text
    meta = r.json()["item"]
    r = client.get(f"/api/files/{meta['id']}/content")
    rows = r.json()["extract"]["sheets"][0]["rows"]
    assert rows[0] == ["material", "qty"] and rows[1][0] == "Paint"


def test_image_without_ocr_engine_uploads_with_clear_message(client):
    item = _create_mr(client, wo="ATTACH-4")
    rid = item["record_id"]
    r = client.post(
        f"/api/work-orders/{rid}/files",
        files={"file": ("site.png", io.BytesIO(PNG_1PX), "image/png")},
        data={"note": ""},
    )
    assert r.status_code == 200, r.text
    meta = r.json()["item"]
    r = client.get(f"/api/files/{meta['id']}/content")
    extract = r.json()["extract"]
    assert extract["kind"] == "image"
    assert extract["ok"] is False
    assert "tesseract" in extract["message"].lower() or "ocr" in extract["message"].lower()


def test_legacy_doc_rejected_but_docx_allowed(client):
    item = _create_mr(client, wo="ATTACH-5")
    rid = item["record_id"]
    r = client.post(
        f"/api/work-orders/{rid}/files",
        files={"file": ("old.doc", io.BytesIO(b"\xd0\xcf\x11\xe0legacy"), "application/msword")},
        data={"note": ""},
    )
    assert r.status_code == 400
    r = client.get(f"/api/work-orders/{rid}/files")
    assert all(f["filename"] != "old.doc" for f in r.json()["items"])
