from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import database, security  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "woms.db")
    database.init_db()
    monkeypatch.setattr(security, "enforce_password_change", lambda: False)
    drive = tmp_path / "drive"
    monkeypatch.setenv("NETDRIVE_PATH", str(drive))
    # reset the preview cache between tests
    from app.routers import netdrive

    netdrive._cache.clear()

    from app.main import app

    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    c.headers.update({"Authorization": f"Bearer {tok}"})
    yield c, drive


def test_upload_list_download_roundtrip(client):
    c, drive = client
    r = c.post("/api/netdrive/upload", data={"dir": ""}, files={"file": ("quote.txt", io.BytesIO(b"hello drive"), "text/plain")})
    assert r.status_code == 200, r.text
    assert r.json()["item"]["name"] == "quote.txt"

    r = c.get("/api/netdrive")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [it["name"] for it in items] == ["quote.txt"]
    assert items[0]["size"] == 11

    r = c.get("/api/netdrive/download", params={"path": "quote.txt"})
    assert r.status_code == 200
    assert r.content == b"hello drive"


def test_upload_never_overwrites(client):
    c, drive = client
    for _ in range(2):
        r = c.post("/api/netdrive/upload", data={"dir": ""}, files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")})
        assert r.status_code == 200
    r = c.get("/api/netdrive")
    names = sorted(it["name"] for it in r.json()["items"])
    assert names == sorted(["a.txt", "a (1).txt"])
    assert len(names) == 2


def test_preview_extracts_txt_and_blocks_traversal(client):
    c, drive = client
    c.post("/api/netdrive/upload", data={"dir": ""}, files={"file": ("note.txt", io.BytesIO("Scope: supply cement".encode()), "text/plain")})

    r = c.get("/api/netdrive/preview", params={"path": "note.txt"})
    assert r.status_code == 200
    assert r.json()["extract"]["ok"] is True
    assert "cement" in r.json()["extract"]["text"]

    # traversal is blocked in every endpoint
    for params in ({"path": "../secret.txt"}, {"path": "sub/../../x"}, {"dir": "../etc"}, {"path": "/etc/passwd"}):
        r = c.get("/api/netdrive/download", params=params)
        assert r.status_code in {400, 404}, params

    r = c.get("/api/netdrive", params={"dir": ".."})
    assert r.status_code == 400


def test_mkdir_navigate_and_delete(client):
    c, drive = client
    r = c.post("/api/netdrive/mkdir", json={"path": "Projects/2026"})
    assert r.status_code == 200

    r = c.post("/api/netdrive/upload", data={"dir": "Projects/2026"}, files={"file": ("p.pdf", io.BytesIO(b"%PDF-not-really"), "application/pdf")})
    assert r.status_code == 200

    r = c.get("/api/netdrive")
    assert any(it["name"] == "Projects" and it["dir"] for it in r.json()["items"])

    r = c.get("/api/netdrive", params={"dir": "Projects/2026"})
    assert [it["name"] for it in r.json()["items"]] == ["p.pdf"]

    # non-empty folder refuses deletion, file deletes, then empty folder deletes
    r = c.request("DELETE", "/api/netdrive", params={"path": "Projects/2026"})
    assert r.status_code == 400
    r = c.request("DELETE", "/api/netdrive", params={"path": "Projects/2026/p.pdf"})
    assert r.status_code == 200
    r = c.request("DELETE", "/api/netdrive", params={"path": "Projects/2026"})
    assert r.status_code == 200
    r = c.request("DELETE", "/api/netdrive", params={"path": "Projects"})
    assert r.status_code == 200


def test_blocked_executable_upload(client):
    c, drive = client
    r = c.post("/api/netdrive/upload", data={"dir": ""}, files={"file": ("tool.exe", io.BytesIO(b"MZ"), "application/x-msdownload")})
    assert r.status_code == 400
    assert "not allowed" in r.json()["detail"].lower()


def test_unauthenticated_is_401(client):
    c, drive = client
    anon = TestClient(c.app)
    r = anon.get("/api/netdrive")
    assert r.status_code == 401
    r = anon.post("/api/netdrive/upload", data={"dir": ""}, files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")})
    assert r.status_code == 401


def test_workorderdetail_viewer_is_in_the_right_component():
    """BUG PIN (2026-09-12): the FileViewer render must live in WorkOrderDetail
    (which owns the `viewing` state), not in LineItemsCard -> crash on open."""
    src = (ROOT / "frontend" / "src" / "pages" / "WorkOrderDetail.jsx").read_text(encoding="utf-8")
    main_end = src.index("function emptyLine()")
    body = src[:main_end]
    assert "const [viewing, setViewing] = useState(null);" in body
    assert body.count("{viewing && <FileViewer") == 1
    # and nowhere else in the file (LineItemsCard etc.)
    assert src.count("{viewing && <FileViewer") == 1
