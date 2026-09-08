from __future__ import annotations

import time
from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.jobs import create_job, get_job, public_job, run_job  # noqa: E402
from app.main import app  # noqa: E402
from app import database  # noqa: E402


def test_job_lifecycle_marks_done():
    jid = create_job("test", "admin")
    assert get_job(jid)["status"] == "queued"

    def work(report):
        report(40, "halfway", "apply")
        return {"ok": True, "n": 3}

    run_job(jid, work)
    deadline = time.time() + 5
    job = get_job(jid)
    while job and job["status"] in {"queued", "running"}:
        if time.time() > deadline:
            break
        time.sleep(0.05)
        job = get_job(jid)
    assert job["status"] == "done"
    assert job["progress"] == 100
    assert job["result"]["n"] == 3
    pub = public_job(job)
    assert pub["id"] == jid
    assert pub["phase"] == "done"


def test_job_lifecycle_captures_error():
    jid = create_job("test-err", "admin")

    def work(_report):
        raise ValueError("boom")

    run_job(jid, work)
    deadline = time.time() + 5
    job = get_job(jid)
    while job and job["status"] in {"queued", "running"}:
        if time.time() > deadline:
            break
        time.sleep(0.05)
        job = get_job(jid)
    assert job["status"] == "error"
    assert "boom" in (job.get("error") or "")


def _admin():
    database.init_db()
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_job_status_requires_login_and_404():
    client = TestClient(app)
    assert client.get("/api/settings/jobs/missing").status_code in {401, 403}
    client, headers = _admin()
    missing = client.get("/api/settings/jobs/missing", headers=headers)
    assert missing.status_code == 404


def test_excel_job_rejects_non_excel():
    client, headers = _admin()
    res = client.post(
        "/api/settings/jobs/excel-upload",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 400
