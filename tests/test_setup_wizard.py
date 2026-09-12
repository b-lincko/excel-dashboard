"""Tests for the first-run setup wizard (backend/setup_wizard.py)."""
from __future__ import annotations

import importlib.util
import os
import stat
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "backend"


def _load():
    spec = importlib.util.spec_from_file_location("setup_wizard_test_mod", BACKEND / "setup_wizard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def wiz(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)  # artifacts (incl. commands file) stay in tmp
    monkeypatch.setattr(mod, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(mod, "COMMANDS_PATH", tmp_path / "setup-commands.sh")
    monkeypatch.setattr(mod, "ENV_BACKUP_DIR", tmp_path / "backups" / "env")
    return mod


BASE_VALUES = {
    "WOMS_PORT": "",
    "LOCAL_BACKUP_PATH": "",
    "SMB_BACKUP_ENABLED": "false",
    "BACKUP_ENABLED": "true",
    "NETDRIVE_PATH": "",
}


def _values(wiz, **over):
    values = dict(wiz.DEFAULTS)
    values.update(BASE_VALUES)
    values.update({k: v for k, v in over.items()})
    return values


def test_render_env_two_accounts_and_no_files_password(wiz):
    values = _values(
        wiz,
        SMB_SERVER="192.168.100.5",
        SMB_SHARE="mr.backup",
        SMB_USERNAME="svc_mr_backup",
        SMB_PASSWORD="bk-secret",
        FILES_SMB_SERVER="192.168.100.5",
        FILES_SMB_SHARE="mr.files",
        FILES_SMB_USERNAME="svc_mr_files",
        FILES_SMB_PASSWORD="files-secret",
        NETDRIVE_PATH="/mnt/mr-files",
        FILES_SMB_MOUNT_PATH="/mnt/mr-files",
    )
    text = wiz.render_env(values)
    # both accounts documented, backup password stored, files password NOT in .env
    assert "SMB_USERNAME=svc_mr_backup" in text
    assert "SMB_PASSWORD=bk-secret" in text
    assert "svc_mr_files" in text
    assert "files-secret" not in text
    assert "NETDRIVE_PATH=/mnt/mr-files" in text

    text_local = wiz.render_env(_values(wiz, NETDRIVE_PATH=""))
    assert text_local.rstrip().endswith("NETDRIVE_PATH=")


def test_save_env_chmod_backup_and_commands(wiz, tmp_path):
    wiz.ENV_PATH.write_text("OLD=value\n", encoding="utf-8")
    values = _values(
        wiz,
        LOCAL_BACKUP_PATH=str(tmp_path / "bk"),
        SMB_PASSWORD="bk-secret",
        NETDRIVE_PATH="",
        SMB_BACKUP_ENABLED="true",
        SMB_SERVER="192.168.100.5",
        SMB_SHARE="mr.backup",
    )
    path = wiz.save_env(values)
    assert Path(path) == wiz.ENV_PATH
    assert "NETDRIVE_PATH=" in path.read_text(encoding="utf-8")
    assert "OLD=value" not in path.read_text(encoding="utf-8")
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    # previous .env backed up, secrets never world-readable
    backups = list(wiz.ENV_BACKUP_DIR.iterdir())
    assert len(backups) == 1 and "OLD=value" in backups[0].read_text(encoding="utf-8")
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600
    cmd = wiz.ROOT / wiz._commands_filename()
    assert cmd.exists() and stat.S_IMODE(cmd.stat().st_mode) == 0o700
    assert "mr.backup" in cmd.read_text(encoding="utf-8")


def test_check_folder_created_ok_and_unwritable(wiz, tmp_path):
    r = wiz.check_folder(str(tmp_path / "newdir" / "sub"), "L")
    assert r["status"] == "created" and (tmp_path / "newdir" / "sub").is_dir()

    r = wiz.check_folder(str(tmp_path), "L")
    assert r["status"] == "ok"

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("running as root: unwritable-dir case not reproducible")
    locked = tmp_path / "locked"
    locked.mkdir()
    os.chmod(locked, 0o555)
    try:
        r = wiz.check_folder(str(locked / "child"), "L")
        assert r["status"] == "error"
    finally:
        os.chmod(locked, 0o755)


def test_overlap_guard_matrix(wiz, tmp_path):
    guard = wiz.check_overlap
    backup_dir = tmp_path / "mr-backup"
    backup_dir.mkdir()
    files_same = guard(_values(wiz, NETDRIVE_PATH=str(backup_dir), LOCAL_BACKUP_PATH=str(backup_dir), SMB_MOUNT_PATH=""))
    assert files_same["status"] == "error"

    files_inside = guard(_values(wiz, NETDRIVE_PATH=str(backup_dir / "team"), LOCAL_BACKUP_PATH=str(backup_dir), SMB_MOUNT_PATH=""))
    assert files_inside["status"] == "error"

    backup_inside_files = guard(_values(wiz, NETDRIVE_PATH=str(tmp_path / "root-files"), SMB_MOUNT_PATH=str(tmp_path / "root-files" / "Daily"), LOCAL_BACKUP_PATH=""))
    assert backup_inside_files["status"] == "error"

    separate = guard(_values(wiz, NETDRIVE_PATH=str(tmp_path / "files"), SMB_MOUNT_PATH=str(backup_dir), LOCAL_BACKUP_PATH=str(tmp_path / "bk")))
    assert separate["status"] == "ok"


def test_mount_state_check(wiz, tmp_path, monkeypatch):
    target = tmp_path / "mnt"
    target.mkdir()
    r = wiz.check_mounted(str(target), "L")
    assert r["status"] == "manual" and "not a mount" in r["detail"]

    real_ismount = os.path.ismount
    monkeypatch.setattr(os.path, "ismount", lambda p: True if str(p) == str(target) else real_ismount(p))
    r = wiz.check_mounted(str(target), "L")
    assert r["status"] == "ok"


def test_smb_probe_without_smbclient_is_manual(wiz, monkeypatch):
    monkeypatch.setattr(wiz.shutil, "which", lambda name: None)
    r = wiz.check_smb_credentials("srv", "share", "DOM", "user", "pw", "backup", probe_share=True)
    assert r["status"] == "manual"

    r = wiz.check_smb_credentials("srv", "share", "DOM", "user", "", "backup", probe_share=True)
    assert r["status"] == "warn"


def test_wizard_api_endpoints(wiz, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    client = TestClient(wiz.app)

    page = client.get("/")
    assert page.status_code == 200 and "first-run setup" in page.text
    assert client.get("/api/defaults").status_code == 200

    values = _values(
        wiz,
        LOCAL_BACKUP_PATH=str(tmp_path / "bk"),
        NETDRIVE_PATH=str(tmp_path / "nd"),
        FILES_SMB_MOUNT_PATH=str(tmp_path / "mnt-files"),
        SMB_MOUNT_PATH=str(tmp_path / "mnt-bk"),
        SMB_PASSWORD="pw",
        FILES_SMB_PASSWORD="pw2",
    )
    r = client.post("/api/validate", json={"values": values})
    assert r.status_code == 200
    assert any(x["id"] == "guard:overlap" for x in r.json()["results"])

    r = client.post("/api/save", json={"values": values})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert wiz.ENV_PATH.exists()

    # save is blocked while a hard error exists
    bad = dict(values)
    bad["WOMS_PORT"] = str(wiz.WIZARD_PORT)  # wizard's own port
    r = client.post("/api/save", json={"values": bad})
    assert r.status_code == 400

    # finish requires .env and triggers shutdown callback
    assert client.post("/api/finish").status_code in {200, 400}
    called = []
    monkeypatch.setattr(wiz, "REQUEST_SHUTDOWN", lambda: called.append(1))
    r = client.post("/api/finish")
    assert r.status_code == 200
    deadline = time.time() + 5
    while not called and time.time() < deadline:
        time.sleep(0.05)
    assert called, "finish must request wizard shutdown"


def test_parse_env_defaults_roundtrip(wiz, tmp_path):
    wiz.ENV_PATH.write_text("SMB_SERVER=10.0.0.9\n# comment\nBogus=1\n", encoding="utf-8")
    values = wiz.current_values()
    assert values["SMB_SERVER"] == "10.0.0.9"
    assert values["SMB_SHARE"] == wiz.DEFAULTS["SMB_SHARE"]
    assert "Bogus" not in values


def test_windows_bat_commands_and_guidance(wiz, monkeypatch):
    """Windows app servers: .bat with net use (passwords never embedded),
    UNC guidance in the mount/account checks, .bat filename."""
    monkeypatch.setattr(wiz.os, "name", "nt")
    values = _values(
        wiz,
        SMB_BACKUP_ENABLED="true",
        SMB_SERVER="192.168.100.5",
        SMB_SHARE="mr.backup",
        SMB_USERNAME="svc_mr_backup",
        SMB_DOMAIN="LINKCO",
        SMB_PASSWORD="bk-secret",
        NETDRIVE_PATH="\\\\192.168.100.5\\mr.files",
        FILES_SMB_SERVER="192.168.100.5",
        FILES_SMB_SHARE="mr.files",
        FILES_SMB_USERNAME="svc_mr_files",
        FILES_SMB_DOMAIN="LINKCO",
        FILES_SMB_PASSWORD="f-secret",
    )
    assert wiz._commands_filename() == "setup-commands.bat"
    text = wiz.render_commands(values)
    assert "net use \\\\192.168.100.5\\mr.backup /user:LINKCO\\svc_mr_backup * /persistent:yes" in text
    assert "net use \\\\192.168.100.5\\mr.files /user:LINKCO\\svc_mr_files * /persistent:yes" in text
    assert "bk-secret" not in text and "f-secret" not in text

    r = wiz.check_mounted("C:/mnt/mr-backup", "L")
    assert r["status"] == "manual" and "UNC" in r["detail"]

    monkeypatch.setattr(wiz.shutil, "which", lambda name: None)
    r = wiz.check_smb_credentials("srv", "share", "DOM", "user", "pw", "backup", probe_share=True)
    assert r["status"] == "manual" and "net use" in r["detail"]


def test_share_name_typed_as_account_is_caught(wiz):
    """Same-named account/share is the CONFIRMED Linkco layout: warn only."""
    values = _values(
        wiz,
        SMB_BACKUP_ENABLED="true",
        SMB_SERVER="192.168.100.5",
        SMB_SHARE="mr.backup",
        SMB_USERNAME="mr.backup",  # real layout: account named like the share
        SMB_PASSWORD="pw",
    )
    out = wiz.check_account_names(values)
    assert out and out[0]["status"] == "warn" and "correct" in out[0]["detail"]

    ok = _values(
        wiz,
        SMB_BACKUP_ENABLED="true",
        SMB_USERNAME="svc_mr_backup",
        SMB_SHARE="mr.backup",
        FILES_SMB_USERNAME="svc_mr_files",
        FILES_SMB_SHARE="mr.files",
        NETDRIVE_PATH="",
    )
    assert wiz.check_account_names(ok) == []


def test_mount_error_13_hint_names_the_real_causes(wiz):
    hint = wiz._mount_error_hint(13, "mount error(13): Permission denied")
    assert "ACCOUNT name" in hint and "share" in hint and "DOMAIN" in hint
    assert wiz._mount_error_hint(2, "No such file or directory")[:5] == "share"
    assert "firewall" in wiz._mount_error_hint(101, "Connection refused")


def test_generated_script_uses_noperm_and_normal_user_hint(wiz):
    values = _values(
        wiz,
        SMB_BACKUP_ENABLED="true",
        SMB_SERVER="192.168.100.5",
        SMB_SHARE="mr.backup",
        SMB_USERNAME="svc_mr_backup",
        SMB_PASSWORD="pw",
        NETDRIVE_PATH="",
    )
    text = wiz.render_commands(values)
    assert "noperm" in text and "vers=3.0" in text
    assert "Run as your NORMAL user" in text


def test_linkco_defaults_are_baked_in(wiz):
    """Confirmed production values (2026-09-13): shares, accounts, domain, vers."""
    d = wiz.DEFAULTS
    assert d["SMB_SHARE"] == "mr.backup" and d["SMB_USERNAME"] == "mr.backup"
    assert d["FILES_SMB_SHARE"] == "mr.drive" and d["FILES_SMB_USERNAME"] == "drive.mr"
    assert d["SMB_DOMAIN"] == "LINKCO.COM" == d["FILES_SMB_DOMAIN"]
    assert d["FILES_SMB_MOUNT_PATH"] == "/mnt/mr.drive"
