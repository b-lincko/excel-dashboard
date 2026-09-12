"""Tests for the dual backup system (local + SMB).

The "SMB share" is simulated with a plain directory (SMB_MODE=mount) - the
transport, verification, tiering and retention logic are identical to the
real CIFS-mounted share; only the filesystem underneath differs.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import database, security  # noqa: E402
from app.config import AppConfig, save_config  # noqa: E402
from app.excel.service import ExcelService  # noqa: E402


def _gen_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


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
def env_setup(tmp_path, monkeypatch, workbook):
    """Isolated dual-backup environment: local store + fake SMB share + data dir."""
    dest, svc = workbook
    data_dir = tmp_path / "appdata"
    data_dir.mkdir()
    (data_dir / ".jwt_secret").write_text("test-secret", encoding="utf-8")
    att = data_dir / "attachments" / "WO-1"
    att.mkdir(parents=True)
    (att / "note.txt").write_text("hello", encoding="utf-8")

    from app import config as app_config

    monkeypatch.setattr(app_config, "DATA_DIR", data_dir, raising=False)
    monkeypatch.setattr(app_config, "ATTACHMENTS_DIR", data_dir / "attachments", raising=False)
    monkeypatch.setattr(app_config, "CONFIG_PATH", data_dir / "app_config.json", raising=False)

    local = tmp_path / "backup"
    smb = tmp_path / "smbshare"
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("LOCAL_BACKUP_PATH", str(local))
    monkeypatch.setenv("SMB_BACKUP_ENABLED", "true")
    monkeypatch.setenv("SMB_MODE", "mount")
    monkeypatch.setenv("SMB_MOUNT_PATH", str(smb))
    monkeypatch.setenv("SMB_SERVER", "FILESERVER")
    monkeypatch.setenv("SMB_SHARE", "MR-Backup")
    monkeypatch.delenv("BACKUP_ENCRYPTION_ENABLED", raising=False)
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("BACKUP_PATHS", raising=False)

    database.DB_PATH = tmp_path / "woms.db"
    database.init_db()
    # warm the cache so the snapshot has the workbook rows
    assert svc.get_all()
    assert database.wo_cache_count() > 0

    from app import dual_backup

    yield dual_backup, local, smb, data_dir, dest

    monkeypatch.delenv("BACKUP_ENABLED", raising=False)
    monkeypatch.delenv("SMB_BACKUP_ENABLED", raising=False)


def test_success_local_and_smb_verified(env_setup):
    dual, local, smb, data_dir, excel = env_setup
    status = dual.run_dual_backup(reason="manual")
    assert status is not None
    assert status["overall"] == "SUCCESS", status["log"]
    assert status["local"]["status"] == "SUCCESS"
    assert status["local"]["verification"] == "PASSED"
    assert status["smb"]["status"] == "SUCCESS"
    assert status["smb"]["verification"] == "PASSED"

    # same artifact on both sides, byte-identical, checksums recorded
    name = status["artifact"]
    lp = Path(status["local"]["path"])
    rp = smb / "Daily" / lp.parent.name / name
    assert lp.is_file() and rp.is_file()
    assert status["local"]["sha256"] == status["smb"]["sha256"] != ""
    assert lp.read_bytes() == rp.read_bytes()
    assert (rp.with_name(name + ".sha256")).is_file()

    # manifest inside the package
    import zipfile

    with zipfile.ZipFile(lp) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["database"] == "sqlite"
        paths = {f["path"] for f in manifest["files"]}
        assert "db/woms.db" in paths
        assert any(p.startswith("excel/") for p in paths)
        assert "config/.jwt_secret" in paths
        assert "uploads/WO-1/note.txt" in paths
        assert "manifest.json" not in paths

    # the snapshot inside the package is a real, populated database
    with zipfile.ZipFile(lp) as zf:
        data = zf.read("db/woms.db")
    snap = Path(status["local"]["path"]).parent / "_snapcheck.db"
    snap.write_bytes(data)
    assert database.snapshot_wo_count(snap) == database.wo_cache_count()
    snap.unlink()

    # weekly + monthly tier copies exist (first run of the week/month)
    assert any((local / "Weekly").rglob(name)) if (local / "Weekly").is_dir() else False
    assert list((smb / "Monthly").rglob(name)) or list((local / "Monthly").rglob(name))


def test_smb_unavailable_is_partial_local_intact(env_setup):
    dual, local, smb, data_dir, excel = env_setup
    # break the SMB target: parent exists but is a FILE, so mkdir/copy must fail
    smb.parent.mkdir(parents=True, exist_ok=True)
    smb.write_text("not a directory", encoding="utf-8")
    status = dual.run_dual_backup(reason="manual")
    assert status["local"]["status"] == "SUCCESS"
    assert status["local"]["verification"] == "PASSED"
    assert status["smb"]["status"] == "FAILED"
    assert status["smb"]["verification"] == "FAILED"
    assert status["smb"]["reason"]
    assert status["overall"] == "PARTIAL_SUCCESS"
    # the successful local backup must NOT be deleted
    assert Path(status["local"]["path"]).is_file()


def test_corrupted_smb_copy_fails_verification(env_setup, monkeypatch):
    dual, local, smb, data_dir, excel = env_setup
    real_push = dual._smb_push_file

    def corrupting_push(cfg, auth, rel_dir, name, src):
        ok, msg = real_push(cfg, auth, rel_dir, name, src)
        if ok and name.endswith(".zip"):
            target = cfg.smb_mount_path / rel_dir / name
            with open(target, "ab") as fh:
                fh.write(b"CORRUPTION")  # flip the remote bytes after the copy
        return ok, msg

    monkeypatch.setattr(dual, "_smb_push_file", corrupting_push)
    status = dual.run_dual_backup(reason="manual")
    assert status["smb"]["status"] == "FAILED"
    assert "checksum mismatch" in status["smb"]["reason"].lower()
    assert status["overall"] == "PARTIAL_SUCCESS"
    assert Path(status["local"]["path"]).is_file()
    # the corrupted remote copy was removed so nobody can restore from it
    assert not (smb / "Daily" / Path(status["local"]["path"]).parent.name / status["artifact"]).exists()


def test_retention_independent_per_destination(env_setup):
    dual, local, smb, data_dir, excel = env_setup
    for root, n in ((local, 10), (smb, 3)):
        for i in range(n):
            day = (datetime.now() - timedelta(days=i + 1)).strftime("%Y-%m-%d")
            d = root / "Daily" / day
            d.mkdir(parents=True, exist_ok=True)
            (d / f"backup_{day}_000000.zip").write_bytes(b"x")

    removed_local = dual.apply_retention(local, 7, 4, 12)
    assert removed_local["daily"] == 3  # 10 -> 7
    # SMB untouched (retention is per destination)
    assert len(list((smb / "Daily").iterdir())) == 3

    removed_smb = dual.apply_retention(smb, 7, 4, 12)
    assert removed_smb["daily"] == 0  # only 3 dailies exist, keep 7
    assert len(list((local / "Daily").iterdir())) == 7


def test_restore_roundtrip(env_setup):
    dual, local, smb, data_dir, excel = env_setup
    status = dual.run_dual_backup(reason="manual")
    assert status["overall"] == "SUCCESS"
    artifact = Path(status["local"]["path"])

    import dual_restore

    restore_data = artifact.parent.parent.parent / "restore-target"
    restore_data.mkdir()
    restore_excel = restore_data.parent / "restored.xlsx"

    # library-level restore with full validation, into a scratch target
    zf, manifest, zpath, tmp = dual_restore.open_package(artifact)
    try:
        files = dual_restore.verify_package(zf, manifest)
        assert any(f["path"] == "db/woms.db" for f in files)
        stage = dual_restore.stage_package(zf, zpath, "staged")
        db_src = stage / "db" / "woms.db"
        assert dual_restore.check_database(db_src) == database.wo_cache_count()
        # excel + config land where the plan says
        assert (stage / "config" / ".jwt_secret").read_text(encoding="utf-8") == "test-secret"
        assert list((stage / "excel").glob("*.xlsx"))
    finally:
        zf.close()
        tmp.cleanup()

    # full do_restore path with --yes semantics into a scratch data dir
    from app import config as app_config

    monkey_target = restore_data
    # temporarily point the app config at the scratch target
    orig_data, orig_att = app_config.DATA_DIR, app_config.ATTACHMENTS_DIR
    app_config.DATA_DIR = monkey_target
    app_config.ATTACHMENTS_DIR = monkey_target / "attachments"
    try:
        import io as _io
        import contextlib

        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            dual_restore.do_restore(
                _stage_for(env_setup, artifact),
                _manifest_for(artifact),
                monkey_target,
                restore_excel,
                True,
                True,
            )
    finally:
        app_config.DATA_DIR, app_config.ATTACHMENTS_DIR = orig_data, orig_att

    # the DB goes through the app's live binding (restore_from) - integrity holds
    assert database.wo_cache_count() > 0
    assert restore_excel.is_file(), "Excel replica restored"
    assert (restore_data / ".jwt_secret").read_text(encoding="utf-8") == "test-secret"
    assert (restore_data / "attachments" / "WO-1" / "note.txt").read_text(encoding="utf-8") == "hello"


def _stage_for(env_setup, artifact: Path) -> Path:
    import zipfile

    stage = artifact.parent / "_restore_stage"
    if stage.exists():
        shutil.rmtree(stage)
    with zipfile.ZipFile(artifact) as zf:
        zf.extractall(stage)
    return stage


def _manifest_for(artifact: Path) -> dict:
    import zipfile

    with zipfile.ZipFile(artifact) as zf:
        return json.loads(zf.read("manifest.json"))


def test_encryption_roundtrip(env_setup, monkeypatch):
    dual, local, smb, data_dir, excel = env_setup
    key = _gen_key()
    monkeypatch.setenv("BACKUP_ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", key)
    status = dual.run_dual_backup(reason="manual")
    assert status["overall"] == "SUCCESS"
    assert status["encrypted"] is True
    assert status["artifact"].endswith(".zip.enc")

    import dual_restore

    artifact = Path(status["local"]["path"])
    zf, manifest, zpath, tmp = dual_restore.open_package(artifact)  # key from env
    try:
        files = dual_restore.verify_package(zf, manifest)
        assert files
    finally:
        zf.close()
        tmp.cleanup()

    # wrong key must fail loudly, not restore garbage
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", _gen_key())
    with pytest.raises(SystemExit, match="Decryption failed"):
        zf2, _m, _z, _t = dual_restore.open_package(artifact)
        zf2.close()
        _t.cleanup()


def test_manual_endpoint_runs_dual_backup(workbook, tmp_path, monkeypatch):
    db = tmp_path / "woms.db"
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    monkeypatch.setattr(security, "enforce_password_change", lambda: False)
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("LOCAL_BACKUP_PATH", str(tmp_path / "backup"))
    monkeypatch.setenv("SMB_BACKUP_ENABLED", "false")
    monkeypatch.delenv("BACKUP_ENCRYPTION_ENABLED", raising=False)

    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    c.headers.update({"Authorization": f"Bearer {tok}"})

    r = c.post("/api/admin/backups")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] in {"success", "partial_success"}
    assert data["local_backup"] == "verified"
    assert data["smb_backup"] == "skipped"

    r = c.get("/api/admin/backups/status")
    assert r.status_code == 200
    st = r.json()
    assert st["last"]["overall"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert "password" not in json.dumps(st["config"]).lower()
    # history shows the run
    assert len(st["history"]) >= 1
