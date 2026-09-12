"""First-run setup wizard (web form) for the Linkco MR app.

Runs BEFORE the main server on port 8081. Collects every .env value as a
form (app core, where files are created, backup destination, SMB backup
share account, Files-page share account), validates what it can
(folders create/write, smbclient credential probe, CIFS mount state),
creates missing folders, then writes:

    .env                 <- the main server is configured from this
    setup-commands.sh    <- copy/paste shell steps (cred files, mounts, fstab)

and (on "Finish & start main server") shuts itself down so the launcher
(`backend/launch.py`) can start the real server from the new .env.

Run it explicitly at any time to reconfigure:

    python backend/launch.py --setup

Security notes: the wizard binds 0.0.0.0:8081 so it is reachable from a
laptop during setup - run it only on a trusted network and close it when
done. Secrets are only stored in .env (chmod 600) and setup-commands.sh
(chmod 700); they are never logged.
"""
from __future__ import annotations

import base64
import html
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
ENV_PATH = ROOT / ".env"
COMMANDS_PATH = ROOT / "setup-commands.sh"
ENV_BACKUP_DIR = ROOT / "backups" / "env"

WIZARD_PORT = 8081

# Set by launch.py so "Finish" can stop uvicorn cleanly. Falls back to a hard
# exit if the launcher did not register anything (e.g. running the file
# directly).
REQUEST_SHUTDOWN: Callable[[], None] | None = None

app = FastAPI(title="Linkco MR setup wizard", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def _same_origin_header(request, call_next):  # noqa: ANN001
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# value handling
# ---------------------------------------------------------------------------

BOOL_KEYS = {
    "BACKUP_ENABLED": "true",
    "SMB_BACKUP_ENABLED": "true",
    "BACKUP_ENCRYPTION_ENABLED": "false",
}

DEFAULTS: dict[str, str] = {
    "WOMS_PORT": "",
    "WOMS_JWT_SECRET": "",
    "WOMS_CORS_ORIGINS": "",
    "BACKUP_ENABLED": "true",
    "LOCAL_BACKUP_PATH": "/backup",
    "BACKUP_DAILY_RETENTION": "7",
    "BACKUP_WEEKLY_RETENTION": "4",
    "BACKUP_MONTHLY_RETENTION": "12",
    "BACKUP_ENCRYPTION_ENABLED": "false",
    "BACKUP_ENCRYPTION_KEY": "",
    "BACKUP_PATHS": "",
    "SMB_BACKUP_ENABLED": "true",
    "SMB_MODE": "mount",
    "SMB_MOUNT_PATH": "/mnt/mr-backup",
    "SMB_SERVER": "192.168.100.5",
    "SMB_SHARE": "mr.backup",
    "SMB_DOMAIN": "LINKCO",
    "SMB_USERNAME": "svc_mr_backup",
    "SMB_PASSWORD": "",
    "FILES_SMB_SERVER": "192.168.100.5",
    "FILES_SMB_SHARE": "mr.files",
    "FILES_SMB_DOMAIN": "LINKCO",
    "FILES_SMB_USERNAME": "svc_mr_files",
    "FILES_SMB_PASSWORD": "",
    "FILES_SMB_MOUNT_PATH": "/mnt/mr-files",
    "NETDRIVE_PATH": "",
}


def parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _commands_filename() -> str:
    """Shell steps for Linux/macOS, a .bat for Windows app servers."""
    return "setup-commands.bat" if os.name == "nt" else "setup-commands.sh"


def current_values() -> dict[str, str]:
    values = dict(DEFAULTS)
    if ENV_PATH.is_file():
        try:
            values.update({k: v for k, v in parse_env_text(ENV_PATH.read_text(encoding="utf-8")).items() if k in values})
        except OSError:
            pass
    return values


def _as_bool(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _generate_jwt_secret() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(48)).decode()


def _generate_enc_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

def check_folder(raw: str, label: str) -> dict[str, Any]:
    path = Path(str(raw or "").strip()).expanduser()
    if not str(path):
        return {"id": f"folder:{label}", "label": label, "status": "skipped", "detail": "not set"}
    try:
        if path.is_dir():
            probe = path / f".wiz-write-test-{int(time.time())}"
            try:
                probe.write_text("x", encoding="utf-8")
                probe.unlink()
                return {"id": f"folder:{label}", "label": label, "status": "ok", "detail": f"exists and writable: {path}"}
            except OSError:
                return {"id": f"folder:{label}", "label": label, "status": "error", "detail": f"{path} exists but is NOT writable by this user"}
        path.mkdir(parents=True, exist_ok=True)
        return {"id": f"folder:{label}", "label": label, "status": "created", "detail": f"created: {path}"}
    except OSError as exc:
        return {"id": f"folder:{label}", "label": label, "status": "error", "detail": f"could not create {path}: {exc}"}


def check_mounted(path_raw: str, label: str) -> dict[str, Any]:
    path = str(path_raw or "").strip()
    if not path:
        return {"id": f"mount:{label}", "label": label, "status": "skipped", "detail": "not set"}
    if os.path.ismount(path):
        return {"id": f"mount:{label}", "label": label, "status": "ok", "detail": f"{path} is a mounted filesystem"}
    if os.name == "nt":
        return {
            "id": f"mount:{label}",
            "label": label,
            "status": "manual",
            "detail": f"{path} is a plain local folder (not a share). On Windows set this field to the UNC share path (e.g. \\\\SERVER\\share) or a mapped drive letter - Windows reports both as mounted. To add the account once: net use \\\\SERVER\\share /user:DOMAIN\\user * /persistent:yes",
        }
    return {
        "id": f"mount:{label}",
        "label": label,
        "status": "manual",
        "detail": f"{path} is a plain local folder (not a mount). Use 'Mount now' or run the commands from {_commands_filename()}",
    }


def check_overlap(values: dict[str, str]) -> dict[str, Any]:
    net = Path(values.get("NETDRIVE_PATH", "").strip()).expanduser() if values.get("NETDRIVE_PATH", "").strip() else None
    if net is None:
        return {"id": "guard:overlap", "label": "Files share isolated from backups", "status": "ok", "detail": "files folder is app-managed (no share)"}
    try:
        net = net.resolve()
    except OSError:
        pass
    zones = []
    for key in ("LOCAL_BACKUP_PATH", "SMB_MOUNT_PATH", "FILES_SMB_MOUNT_PATH"):
        raw = values.get(key, "").strip()
        if not raw:
            continue
        try:
            zones.append((key, Path(raw).expanduser().resolve()))
        except OSError:
            continue
    for name, zone in zones:
        if net == zone or zone in net.parents or net in zone.parents:
            return {
                "id": "guard:overlap",
                "label": "Files share isolated from backups",
                "status": "error",
                "detail": f"NETDRIVE_PATH overlaps {name} ({zone}) - Files users must never reach backups",
            }
    return {"id": "guard:overlap", "label": "Files share isolated from backups", "status": "ok", "detail": "no overlap with backup destinations"}


def check_smb_credentials(server: str, share: str, domain: str, username: str, password: str, label: str, probe_share: bool) -> dict[str, Any]:
    if not (server.strip() and username.strip() and password.strip()):
        return {
            "id": f"smb:{label}",
            "label": f"SMB account ({label})",
            "status": "warn",
            "detail": "server/username/password not fully filled in - the OS mount (or smbclient) will need them later",
        }
    exe = shutil.which("smbclient")
    if not exe:
        if os.name == "nt":
            return {
                "id": f"smb:{label}",
                "label": f"SMB account ({label})",
                "status": "manual",
                "detail": "smbclient is not available on Windows - the account is exercised the first time the app copies to the share. Make sure the share exists and this account has rights on it (test once with: net use \\\\SERVER\\share /user:DOMAIN\\user * /persistent:yes). Save will continue.",
            }
        return {
            "id": f"smb:{label}",
            "label": f"SMB account ({label})",
            "status": "manual",
            "detail": "smbclient is not installed here, so credentials cannot be auto-verified (sudo apt install smbclient). Save will continue.",
        }
    auth = tempfile.NamedTemporaryFile("w", suffix=".auth", delete=False)
    auth.write(f"username = {username.strip()}\n")
    auth.write(f"password = {password}\n")
    if domain.strip():
        auth.write(f"domain = {domain.strip()}\n")
    auth.close()
    os.chmod(auth.name, stat.S_IRUSR | stat.S_IWUSR)
    try:
        if probe_share and share.strip():
            target = f"//{server.strip()}/{share.strip()}"
            cmd = [exe, target, "-A", auth.name, "-m", "SMB3", "-c", "ls"]
        else:
            cmd = [exe, "-L", server.strip(), "-A", auth.name, "-m", "SMB3"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            detail = f"credentials accepted by {server.strip()}" + (f", share {share.strip()} readable" if probe_share and share.strip() else "")
            return {"id": f"smb:{label}", "label": f"SMB account ({label})", "status": "ok", "detail": detail}
        if "NT_STATUS_LOGON_FAILURE" in out:
            return {"id": f"smb:{label}", "label": f"SMB account ({label})", "status": "error", "detail": "server reachable but the username/password was REJECTED (NT_STATUS_LOGON_FAILURE)"}
        if "NT_STATUS_BAD_NETWORK_NAME" in out:
            return {"id": f"smb:{label}", "label": f"SMB account ({label})", "status": "error", "detail": f"share name not found on {server.strip()} (NT_STATUS_BAD_NETWORK_NAME)"}
        if "NT_STATUS_ACCESS_DENIED" in out:
            return {"id": f"smb:{label}", "label": f"SMB account ({label})", "status": "error", "detail": "account has no permission on this share (NT_STATUS_ACCESS_DENIED)"}
        if "CONNECTION_REFUSED" in out or "HOST_UNREACHABLE" in out or "timed out" in out.lower():
            return {"id": f"smb:{label}", "label": f"SMB account ({label})", "status": "error", "detail": f"could not reach {server.strip()} (firewall/offline/wrong IP)"}
        tail = " ".join(out.split())[:180]
        return {"id": f"smb:{label}", "label": f"SMB account ({label})", "status": "error", "detail": tail or f"smbclient exited {proc.returncode}"}
    except subprocess.TimeoutExpired:
        return {"id": f"smb:{label}", "label": f"SMB account ({label})", "status": "error", "detail": f"{server.strip()} did not answer within 25 s"}
    except OSError as exc:
        return {"id": f"smb:{label}", "label": f"SMB account ({label})", "status": "manual", "detail": f"could not run smbclient: {exc}"}
    finally:
        try:
            os.unlink(auth.name)
        except OSError:
            pass


def check_encryption(values: dict[str, str]) -> dict[str, Any]:
    if not _as_bool(values.get("BACKUP_ENCRYPTION_ENABLED")):
        return {"id": "backup:encryption", "label": "Backup encryption", "status": "skipped", "detail": "disabled"}
    key = values.get("BACKUP_ENCRYPTION_KEY", "").strip()
    if not key:
        return {"id": "backup:encryption", "label": "Backup encryption", "status": "error", "detail": "enabled but no key - use the Generate key button"}
    try:
        raw = base64.urlsafe_b64decode(key.encode())
    except Exception:
        return {"id": "backup:encryption", "label": "Backup encryption", "status": "error", "detail": "key is not valid URL-safe base64"}
    if len(raw) != 32:
        return {"id": "backup:encryption", "label": "Backup encryption", "status": "error", "detail": f"key must decode to 32 bytes (got {len(raw)}) - use Generate key"}
    return {"id": "backup:encryption", "label": "Backup encryption", "status": "ok", "detail": "key valid (AES-256). Store a copy OFF the server - losing it means backups cannot be restored"}


def check_retention(values: dict[str, str]) -> dict[str, Any]:
    for key in ("BACKUP_DAILY_RETENTION", "BACKUP_WEEKLY_RETENTION", "BACKUP_MONTHLY_RETENTION"):
        raw = values.get(key, "").strip() or "0"
        if not re.fullmatch(r"\d+", raw):
            return {"id": "backup:retention", "label": "Retention numbers", "status": "error", "detail": f"{key}={raw!r} is not a whole number"}
    return {"id": "backup:retention", "label": "Retention numbers", "status": "ok", "detail": "daily/weekly/monthly counts valid"}


def check_app_port(values: dict[str, str]) -> dict[str, Any]:
    raw = values.get("WOMS_PORT", "").strip()
    if not raw:
        return {"id": "app:port", "label": "Main server port", "status": "ok", "detail": "default (bare metal: backend 8001 behind nginx; Docker: publishes 8000)"}
    if not re.fullmatch(r"\d{1,5}", raw) or not (0 < int(raw) < 65536):
        return {"id": "app:port", "label": "Main server port", "status": "error", "detail": f"{raw!r} is not a valid port"}
    if int(raw) == WIZARD_PORT:
        return {"id": "app:port", "label": "Main server port", "status": "error", "detail": f"{raw} is the wizard's own port - leave empty or pick another"}
    return {"id": "app:port", "label": "Main server port", "status": "ok", "detail": f"port {raw}"}


def run_all_checks(values: dict[str, str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = [check_app_port(values)]

    if _as_bool(values.get("BACKUP_ENABLED")):
        results.append(check_folder(values.get("LOCAL_BACKUP_PATH"), "Local backup folder (where backup files are created)"))
    else:
        results.append({"id": "folder:local", "label": "Local backup folder", "status": "skipped", "detail": "backups disabled"})
    results.append(check_retention(values))
    results.append(check_encryption(values))

    if _as_bool(values.get("SMB_BACKUP_ENABLED")):
        results.append(check_folder(values.get("SMB_MOUNT_PATH"), "Backup share mount point"))
        if values.get("SMB_MODE", "mount") == "mount":
            results.append(check_mounted(values.get("SMB_MOUNT_PATH"), "Backup share mount state"))
            results.append(check_smb_credentials(values.get("SMB_SERVER", ""), values.get("SMB_SHARE", ""), values.get("SMB_DOMAIN", ""), values.get("SMB_USERNAME", ""), values.get("SMB_PASSWORD", ""), "backup", probe_share=False))
        else:
            results.append(check_smb_credentials(values.get("SMB_SERVER", ""), values.get("SMB_SHARE", ""), values.get("SMB_DOMAIN", ""), values.get("SMB_USERNAME", ""), values.get("SMB_PASSWORD", ""), "backup", probe_share=True))
    else:
        results.append({"id": "smb:backup", "label": "SMB backup share", "status": "skipped", "detail": "SMB backup disabled"})

    files_share_used = bool(values.get("NETDRIVE_PATH", "").strip())
    if files_share_used:
        results.append(check_folder(values.get("NETDRIVE_PATH"), "Files-drive folder (where user files are created)"))
        results.append(check_folder(values.get("FILES_SMB_MOUNT_PATH"), "Files share mount point"))
        results.append(check_mounted(values.get("FILES_SMB_MOUNT_PATH"), "Files share mount state"))
        results.append(check_smb_credentials(values.get("FILES_SMB_SERVER", ""), values.get("FILES_SMB_SHARE", ""), values.get("FILES_SMB_DOMAIN", ""), values.get("FILES_SMB_USERNAME", ""), values.get("FILES_SMB_PASSWORD", ""), "files", probe_share=True))
    else:
        results.append({"id": "folder:netdrive", "label": "Files-drive folder", "status": "skipped", "detail": "empty = app-managed folder data/netdrive"})

    results.append(check_overlap(values))
    return results


# ---------------------------------------------------------------------------
# artifact writers
# ---------------------------------------------------------------------------

def render_env(v: dict[str, str]) -> str:
    def g(key: str) -> str:
        return str(v.get(key, "") or "")

    def b(key: str) -> str:
        return "true" if _as_bool(v.get(key, DEFAULTS[key])) else "false"

    files_used = bool(g("NETDRIVE_PATH").strip())
    lines = [
        "# ==========================================================================",
        "# Linkco MR - generated by the setup wizard. Keep this file on the server.",
        "# Git-ignored on purpose (it holds secrets). Regenerate any time:",
        "#   python3 backend/launch.py --setup",
        "# ==========================================================================",
        "",
        "# --- Core app ---------------------------------------------------------------",
        "# Bare metal: leave empty (backend binds 8001 behind nginx, which publishes 8000).",
        "# Docker: leave empty - compose publishes 8000.",
        f"WOMS_PORT={g('WOMS_PORT')}",
        f"WOMS_JWT_SECRET={g('WOMS_JWT_SECRET')}",
        f"WOMS_CORS_ORIGINS={g('WOMS_CORS_ORIGINS')}",
        "",
        "# TWO SEPARATE SERVICE ACCOUNTS (never share one, never a person's AD account):",
        f"#   {g('SMB_DOMAIN') + chr(92) if g('SMB_DOMAIN') else ''}{g('SMB_USERNAME')} -> \\\\{g('SMB_SERVER')}\\{g('SMB_SHARE')}  (backups only; no user access)",
        f"#   {g('FILES_SMB_DOMAIN') + chr(92) if g('FILES_SMB_DOMAIN') else ''}{g('FILES_SMB_USERNAME')} -> \\\\{g('FILES_SMB_SERVER')}\\{g('FILES_SMB_SHARE')}  (Files page only)",
        "",
        "# --- Dual backup system -----------------------------------------------------",
        f"BACKUP_ENABLED={b('BACKUP_ENABLED')}",
        f"LOCAL_BACKUP_PATH={g('LOCAL_BACKUP_PATH')}",
        "",
        "# Mode: mount = this app copies into SMB_MOUNT_PATH (mounted with account 1).",
        "#       smbclient = the app pushes directly with the credentials below.",
        f"SMB_BACKUP_ENABLED={b('SMB_BACKUP_ENABLED')}",
        f"SMB_MODE={g('SMB_MODE') or 'mount'}",
        f"SMB_MOUNT_PATH={g('SMB_MOUNT_PATH')}",
        f"SMB_SERVER={g('SMB_SERVER')}",
        f"SMB_SHARE={g('SMB_SHARE')}",
        f"SMB_DOMAIN={g('SMB_DOMAIN')}",
        f"SMB_USERNAME={g('SMB_USERNAME')}",
        f"SMB_PASSWORD={g('SMB_PASSWORD')}",
        "",
        f"BACKUP_DAILY_RETENTION={g('BACKUP_DAILY_RETENTION') or '7'}",
        f"BACKUP_WEEKLY_RETENTION={g('BACKUP_WEEKLY_RETENTION') or '4'}",
        f"BACKUP_MONTHLY_RETENTION={g('BACKUP_MONTHLY_RETENTION') or '12'}",
        f"BACKUP_ENCRYPTION_ENABLED={b('BACKUP_ENCRYPTION_ENABLED')}",
        f"BACKUP_ENCRYPTION_KEY={g('BACKUP_ENCRYPTION_KEY')}",
        f"BACKUP_PATHS={g('BACKUP_PATHS')}",
        "",
        "# --- Network drive / Files page (account 2) ---------------------------------",
        "# Folder users browse at /files. Empty = app-managed data/netdrive folder.",
    ]
    if files_used:
        lines += [
            f"# Backed by \\\\{g('FILES_SMB_SERVER')}\\{g('FILES_SMB_SHARE')} mounted at {g('FILES_SMB_MOUNT_PATH')} (credentials in the OS mount).",
            "# Wizard-only reference values (the mount itself uses /etc/mr-files.cred):",
            f"# FILES_SMB_SERVER={g('FILES_SMB_SERVER')}",
            f"# FILES_SMB_SHARE={g('FILES_SMB_SHARE')}",
            f"# FILES_SMB_DOMAIN={g('FILES_SMB_DOMAIN')}",
            f"# FILES_SMB_USERNAME={g('FILES_SMB_USERNAME')}",
            "# FILES_SMB_PASSWORD=***stored-in-the-mount-cred-file***",
            f"NETDRIVE_PATH={g('NETDRIVE_PATH')}",
        ]
    else:
        lines.append("NETDRIVE_PATH=")
    lines.append("")
    return "\n".join(lines)


def _render_commands_bat(v: dict[str, str]) -> str:
    """Windows variant: net use with a secure password prompt (never echoed)."""
    def g(key: str) -> str:
        return str(v.get(key, "") or "")

    bs = chr(92)
    out = [
        "@echo off",
        "REM Generated by the Linkco MR setup wizard.",
        "REM Registers the service accounts with Windows (password prompt is secure),",
        "REM and keeps the mappings persistent across reboots.",
        "REM Run this once in a normal (admin not required) command prompt.",
        "",
    ]
    if _as_bool(v.get("SMB_BACKUP_ENABLED")) and g("SMB_SERVER"):
        unc = f"{bs*2}{g('SMB_SERVER')}{bs}{g('SMB_SHARE')}"
        dom = f"{g('SMB_DOMAIN')}{bs}" if g("SMB_DOMAIN") else ""
        out += [
            f"REM --- Account 1: backup share {unc} ---",
            f"net use {unc} /user:{dom}{g('SMB_USERNAME')} * /persistent:yes",
            "",
        ]
    if g("NETDRIVE_PATH").strip() and g("FILES_SMB_SERVER"):
        unc = f"{bs*2}{g('FILES_SMB_SERVER')}{bs}{g('FILES_SMB_SHARE')}"
        dom = f"{g('FILES_SMB_DOMAIN')}{bs}" if g("FILES_SMB_DOMAIN") else ""
        out += [
            f"REM --- Account 2: files share {unc} ---",
            f"net use {unc} /user:{dom}{g('FILES_SMB_USERNAME')} * /persistent:yes",
            "",
        ]
    out += [
        "echo Done. The dashboard can reach the shares by UNC path now.",
        "echo Set the wizard path fields to the UNC form (",
        f"echo   {chr(92)}{chr(92)}SERVER{chr(92)}SHARE ) and re-run Validate to confirm.",
        "pause",
        "",
    ]
    return "\r\n".join(out)


def render_commands(v: dict[str, str]) -> str:
    if os.name == "nt":
        return _render_commands_bat(v)

    def g(key: str) -> str:
        return str(v.get(key, "") or "")

    out = ["#!/bin/sh", "# Generated by the Linkco MR setup wizard.", "# Run the steps that apply to this machine (most need sudo).", "set -x", ""]

    if _as_bool(v.get("SMB_BACKUP_ENABLED")) and g("SMB_SERVER"):
        cred = "/etc/mr-backup.cred"
        out += [
            "# --- Account 1: backup share ------------------------------------------",
            f"printf 'username = {g('SMB_USERNAME')}\npassword = {g('SMB_PASSWORD')}\ndomain = {g('SMB_DOMAIN')}\n' | sudo tee {cred} >/dev/null",
            f"sudo chmod 600 {cred}",
            f"sudo mkdir -p {g('SMB_MOUNT_PATH')}",
            f"sudo mount -t cifs //{g('SMB_SERVER')}/{g('SMB_SHARE')} {g('SMB_MOUNT_PATH')} -o credentials={cred},uid=$(id -u),gid=$(id -g),iocharset=utf8",
            f"# fstab line to survive reboots:",
            f"# //{g('SMB_SERVER')}/{g('SMB_SHARE')}  {g('SMB_MOUNT_PATH')}  cifs  credentials={cred},uid=1000,gid=1000,iocharset=utf8,_netdev  0  0",
            "",
        ]

    if g("NETDRIVE_PATH").strip() and g("FILES_SMB_SERVER"):
        cred = "/etc/mr-files.cred"
        out += [
            "# --- Account 2: files share -------------------------------------------",
            f"printf 'username = {g('FILES_SMB_USERNAME')}\npassword = {g('FILES_SMB_PASSWORD')}\ndomain = {g('FILES_SMB_DOMAIN')}\n' | sudo tee {cred} >/dev/null",
            f"sudo chmod 600 {cred}",
            f"sudo mkdir -p {g('FILES_SMB_MOUNT_PATH')}",
            f"sudo mount -t cifs //{g('FILES_SMB_SERVER')}/{g('FILES_SMB_SHARE')} {g('FILES_SMB_MOUNT_PATH')} -o credentials={cred},uid=$(id -u),gid=$(id -g),iocharset=utf8",
            f"# fstab line to survive reboots:",
            f"# //{g('FILES_SMB_SERVER')}/{g('FILES_SMB_SHARE')}  {g('FILES_SMB_MOUNT_PATH')}  cifs  credentials={cred},uid=1000,gid=1000,iocharset=utf8,_netdev  0  0",
            "",
        ]

    out += ["echo 'Done. Start the main server with:  python3 backend/launch.py'", "exit 0", ""]
    return "\n".join(out)


def save_env(v: dict[str, str]) -> Path:
    ENV_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if ENV_PATH.is_file():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = ENV_BACKUP_DIR / f".env.bak-{stamp}"
        try:
            backup.write_text(ENV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            os.chmod(backup, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    text = render_env(v)
    ENV_PATH.write_text(text, encoding="utf-8")
    try:
        os.chmod(ENV_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    cmd_path = ROOT / _commands_filename()
    cmd_path.write_text(render_commands(v), encoding="utf-8")
    try:
        os.chmod(cmd_path, stat.S_IRWXU)
    except OSError:
        pass
    return ENV_PATH


def try_mount(which: str, v: dict[str, str]) -> dict[str, Any]:
    """Best-effort real mount; otherwise return exact commands."""
    label = "backup" if which == "backup" else "files"
    if which == "backup":
        server, share, domain = v.get("SMB_SERVER", ""), v.get("SMB_SHARE", ""), v.get("SMB_DOMAIN", "")
        username, password, target = v.get("SMB_USERNAME", ""), v.get("SMB_PASSWORD", ""), v.get("SMB_MOUNT_PATH", "")
    else:
        server, share, domain = v.get("FILES_SMB_SERVER", ""), v.get("FILES_SMB_SHARE", ""), v.get("FILES_SMB_DOMAIN", "")
        username, password, target = v.get("FILES_SMB_USERNAME", ""), v.get("FILES_SMB_PASSWORD", ""), v.get("FILES_SMB_MOUNT_PATH", "")
    target = target.strip()
    unc = f"//{server.strip()}/{share.strip()}"
    if not (server.strip() and share.strip() and target):
        return {"id": f"mount:{label}", "label": f"Mount {label} share", "status": "error", "detail": "server/share/mount path must be filled in first"}

    folder = check_folder(target, f"Mount point {target}")
    if folder["status"] == "error":
        return {"id": f"mount:{label}", "label": f"Mount {label} share", "status": "error", "detail": folder["detail"]}
    if os.path.ismount(target):
        return {"id": f"mount:{label}", "label": f"Mount {label} share", "status": "ok", "detail": f"{target} is already mounted"}

    if os.name == "nt":
        dom = f"{domain.strip()}{chr(92)}" if domain.strip() else ""
        return {
            "id": f"mount:{label}",
            "label": f"Mount {label} share",
            "status": "manual",
            "detail": f"Windows uses shares directly - set this field to {chr(92)}{chr(92)}{server.strip()}{chr(92)}{share.strip()} (UNC). To register the account once, run:  net use {chr(92)}{chr(92)}{server.strip()}{chr(92)}{share.strip()} /user:{dom}{username.strip()} * /persistent:yes",
        }
    if not shutil.which("mount.cifs"):
        return {"id": f"mount:{label}", "label": f"Mount {label} share", "status": "manual", "detail": "mount.cifs missing (sudo apt install cifs-utils) - then run setup-commands.sh"}
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        return {"id": f"mount:{label}", "label": f"Mount {label} share", "status": "manual", "detail": "mounting needs root: re-run the wizard with sudo, or run setup-commands.sh"}

    cred = Path(f"/etc/mr-{label}.cred")
    try:
        content = f"username = {username.strip()}\npassword = {password}\n" + (f"domain = {domain.strip()}\n" if domain.strip() else "")
        cred.write_text(content, encoding="utf-8")
        os.chmod(cred, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        return {"id": f"mount:{label}", "label": f"Mount {label} share", "status": "manual", "detail": f"could not write {cred} ({exc}) - run setup-commands.sh with sudo"}
    # noperm: the client does not enforce local perms (server ACLs still apply),
    # so the app user can use a mount created by root.
    opts = f"credentials={cred},uid=0,gid=0,iocharset=utf8,noperm"
    try:
        proc = subprocess.run(["mount", "-t", "cifs", unc, target, "-o", opts], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"id": f"mount:{label}", "label": f"Mount {label} share", "status": "manual", "detail": f"mount failed to run ({exc}) - use setup-commands.sh"}
    if proc.returncode == 0 and os.path.ismount(target):
        return {"id": f"mount:{label}", "label": f"Mount {label} share", "status": "ok", "detail": f"mounted {unc} at {target} (add the fstab line from setup-commands.sh to survive reboots)"}
    tail = " ".join(((proc.stderr or "") + (proc.stdout or "")).split())[:200]
    return {"id": f"mount:{label}", "label": f"Mount {label} share", "status": "error", "detail": tail or f"mount exited {proc.returncode}"}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class ValuesBody(BaseModel):
    values: dict[str, str] = {}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(PAGE_HTML)


@app.get("/api/defaults")
def api_defaults() -> JSONResponse:
    values = current_values()
    return JSONResponse({"values": values, "env_exists": ENV_PATH.is_file(), "wizard_port": WIZARD_PORT})


@app.get("/api/generate")
def api_generate() -> JSONResponse:
    return JSONResponse({"jwt_secret": _generate_jwt_secret(), "enc_key": _generate_enc_key()})


@app.post("/api/validate")
def api_validate(body: ValuesBody) -> JSONResponse:
    results = run_all_checks(_clean(body.values))
    return JSONResponse({"results": results, "ok": not any(r["status"] == "error" for r in results)})


@app.post("/api/mount")
def api_mount(body: dict) -> JSONResponse:
    which = str(body.get("which", "")).strip()
    if which not in {"backup", "files"}:
        return JSONResponse({"detail": "which must be 'backup' or 'files'"}, status_code=400)
    values = _clean(body.get("values", {}))
    return JSONResponse({"result": try_mount(which, values)})


@app.post("/api/save")
def api_save(body: ValuesBody) -> JSONResponse:
    values = _clean(body.values)
    results = run_all_checks(values)
    errors = [r for r in results if r["status"] == "error"]
    if errors:
        return JSONResponse({"ok": False, "results": results, "detail": "Fix the errors before saving."}, status_code=400)
    path = save_env(values)
    return JSONResponse({
        "ok": True,
        "results": results,
        "env_path": str(path),
        "commands_path": str(ROOT / _commands_filename()),
        "detail": f".env written ({path}). Next: mount the shares (if not already), then Finish.",
    })


@app.post("/api/finish")
def api_finish() -> JSONResponse:
    if not ENV_PATH.is_file():
        return JSONResponse({"detail": "Save the form first - no .env exists yet."}, status_code=400)

    def _stop() -> None:
        try:
            if REQUEST_SHUTDOWN is not None:
                REQUEST_SHUTDOWN()
                return
        except Exception:
            pass
        time.sleep(0.5)
        os._exit(0)

    threading.Timer(0.2, _stop).start()
    return JSONResponse({"ok": True, "detail": "Wizard is closing - the main server is starting from the new .env."})


def _clean(values: dict[str, str]) -> dict[str, str]:
    cleaned = dict(DEFAULTS)
    for key, value in (values or {}).items():
        if key in cleaned and isinstance(value, str):
            cleaned[key] = value
    return cleaned


# ---------------------------------------------------------------------------
# page
# ---------------------------------------------------------------------------

PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Linkco MR - first-run setup</title>
<style>
  :root { --bg:#0f172a; --card:#1e293b; --line:#334155; --text:#e2e8f0; --mut:#94a3b8;
          --acc:#0ea5e9; --ok:#22c55e; --warn:#f59e0b; --err:#ef4444; --man:#a78bfa; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width:880px; margin:0 auto; padding:28px 18px 80px; }
  h1 { font-size:22px; margin:0 0 4px; }
  .sub { color:var(--mut); margin:0 0 22px; font-size:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px;
          padding:18px 20px; margin-bottom:18px; }
  .card h2 { font-size:15px; margin:0 0 12px; color:var(--acc); text-transform:uppercase; letter-spacing:.06em; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:12px 16px; }
  .grid3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px 16px; }
  @media (max-width:640px){ .grid,.grid3{grid-template-columns:1fr;} }
  label { display:block; font-size:12px; color:var(--mut); margin-bottom:4px; }
  input,select { width:100%; background:#0b1220; color:var(--text); border:1px solid var(--line);
          border-radius:8px; padding:8px 10px; font-size:14px; }
  input:focus,select:focus { outline:2px solid var(--acc); border-color:transparent; }
  input[type=password] { font-family:monospace; }
  .hint { font-size:11.5px; color:var(--mut); margin-top:3px; }
  .row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:14px; }
  button { border:0; border-radius:9px; padding:10px 18px; font-size:14px; font-weight:600; cursor:pointer; }
  .b-val { background:var(--acc); color:#04121d; }
  .b-save { background:var(--ok); color:#031a0b; }
  .b-fin { background:#475569; color:#fff; }
  .b-fin.ready { background:var(--ok); color:#031a0b; }
  .b-mini { background:#0b1220; color:var(--text); border:1px solid var(--line);
            padding:6px 10px; font-size:12px; font-weight:500; }
  .b-mount { background:var(--man); color:#160f2e; }
  #results { margin-top:6px; }
  .res { display:flex; gap:10px; padding:7px 4px; border-bottom:1px dashed var(--line);
         font-size:13.5px; align-items:baseline; }
  .res .tag { min-width:76px; text-align:center; border-radius:6px; font-size:11px;
              font-weight:700; padding:2px 6px; text-transform:uppercase; flex:none; }
  .ok .tag { background:#052e16; color:var(--ok); } .created .tag { background:#052e16; color:#4ade80; }
  .warn .tag { background:#301c04; color:var(--warn); } .error .tag { background:#2a0808; color:var(--err); }
  .manual .tag { background:#1e1633; color:var(--man); } .skipped .tag { background:#1e293b; color:var(--mut); }
  .res .det { color:var(--mut); }
  #banner { display:none; margin-top:16px; padding:12px 14px; border-radius:10px;
            background:#052e16; color:#bbf7d0; font-size:14px; }
  .badge { display:inline-block; background:#7c2d12; color:#fed7aa; font-size:11px;
           border-radius:6px; padding:2px 8px; margin-left:8px; vertical-align:middle; }
  .mono { font-family:ui-monospace,Menlo,Consolas,monospace; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Linkco MR &mdash; first-run setup <span class="badge">wizard :8081</span></h1>
  <p class="sub">This form collects everything in <span class="mono">.env</span>, validates the SMB accounts and folders, creates what is missing, then writes <span class="mono">.env</span> and hands over to the main server. Run on a trusted network only &mdash; close it when done.</p>

  <div class="card">
    <h2>1 &middot; Application</h2>
    <div class="grid3">
      <div><label>Main server port</label><input id="WOMS_PORT" placeholder="(recommended: empty)">
        <div class="hint">Empty = backend 8001 behind nginx :8000. Do not use 8081.</div></div>
      <div><label>CORS origins (optional)</label><input id="WOMS_CORS_ORIGINS" placeholder="(empty)"></div>
      <div><label>JWT secret</label>
        <div style="display:flex;gap:8px"><input id="WOMS_JWT_SECRET" placeholder="(auto-generated if empty)"><button class="b-mini" onclick="genSecret()" type="button">Generate</button></div>
        <div class="hint">Random string so logins survive container recreation.</div></div>
    </div>
  </div>

  <div class="card">
    <h2>2 &middot; Where files are created</h2>
    <div class="grid3">
      <div><label>Local backup folder</label><input id="LOCAL_BACKUP_PATH"><div class="hint">Daily/ Weekly/ Monthly/ are created inside.</div></div>
      <div><label>Backup share mount point</label><input id="SMB_MOUNT_PATH"><div class="hint">Folder the Windows backup share is mounted on.</div></div>
      <div><label>Files-share mount point</label><input id="FILES_SMB_MOUNT_PATH"><div class="hint">Folder the user-files share is mounted on.</div></div>
      <div><label>Files-drive folder (NETDRIVE_PATH)</label><input id="NETDRIVE_PATH" placeholder="(empty = app-managed data/netdrive)">
        <div class="hint">Where user files for the dashboard Files page live. Point it at the files-share mount to serve the share.</div></div>
      <div><label>Extra backup paths (optional)</label><input id="BACKUP_PATHS" placeholder="/app/secrets:/srv/export"></div>
    </div>
  </div>

  <div class="card">
    <h2>3 &middot; Backup options</h2>
    <div class="grid3">
      <div><label>Backups enabled</label><select id="BACKUP_ENABLED"><option value="true">true</option><option value="false">false</option></select></div>
      <div><label>Daily copies to keep</label><input id="BACKUP_DAILY_RETENTION"></div>
      <div><label>Weekly copies to keep</label><input id="BACKUP_WEEKLY_RETENTION"></div>
      <div><label>Monthly copies to keep</label><input id="BACKUP_MONTHLY_RETENTION"></div>
      <div><label>Encrypt backup package (AES-256)</label><select id="BACKUP_ENCRYPTION_ENABLED" onchange="encChanged()"><option value="false">false</option><option value="true">true</option></select></div>
      <div><label>Encryption key</label>
        <div style="display:flex;gap:8px"><input id="BACKUP_ENCRYPTION_KEY" class="mono" placeholder="(required if enabled)"><button class="b-mini" id="genkey" type="button" style="display:none" onclick="genKey()">Generate</button></div>
        <div class="hint">Store a copy OFF the server &mdash; a lost key means lost backups.</div></div>
      <div><label>SMB backup enabled</label><select id="SMB_BACKUP_ENABLED"><option value="true">true</option><option value="false">false</option></select></div>
      <div><label>SMB transport</label><select id="SMB_MODE"><option value="mount">mount (share mounted on this server)</option><option value="smbclient">smbclient (direct push)</option></select></div>
    </div>
  </div>

  <div class="card">
    <h2>4 &middot; SMB account 1 &mdash; backup share</h2>
    <div class="grid3">
      <div><label>Server (bare IP/host)</label><input id="SMB_SERVER"></div>
      <div><label>Share name</label><input id="SMB_SHARE"></div>
      <div><label>Domain</label><input id="SMB_DOMAIN"></div>
      <div><label>Username</label><input id="SMB_USERNAME"><div class="hint">Service account for backups only.</div></div>
      <div><label>Password</label><input id="SMB_PASSWORD" type="password"></div>
      <div><label>Mounted at</label><input id="SMB_MOUNT_PATH_BACKUP_DISPLAY" disabled></div>
    </div>
    <div class="row"><button class="b-mount" type="button" onclick="doMount('backup')">Mount backup share now</button>
      <span class="hint">Linux: needs root (run the wizard with sudo). Windows: no mounting - the share is used directly by UNC path; see the manual result.</span></div>
  </div>

  <div class="card">
    <h2>5 &middot; SMB account 2 &mdash; files share (dashboard Files page)</h2>
    <div class="grid3">
      <div><label>Server (bare IP/host)</label><input id="FILES_SMB_SERVER"></div>
      <div><label>Share name</label><input id="FILES_SMB_SHARE"></div>
      <div><label>Domain</label><input id="FILES_SMB_DOMAIN"></div>
      <div><label>Username</label><input id="FILES_SMB_USERNAME"><div class="hint">Separate account from the backup one.</div></div>
      <div><label>Password</label><input id="FILES_SMB_PASSWORD" type="password"></div>
      <div><label>Mounted at</label><input id="FILES_SMB_MOUNT_PATH"></div>
    </div>
    <div class="row"><button class="b-mount" type="button" onclick="doMount('files')">Mount files share now</button>
      <span class="hint">Tip: point field 2 &middot; NETDRIVE_PATH at this mount point so the Files page serves the share.</span></div>
  </div>

  <div class="card">
    <h2>6 &middot; Validate, save, start</h2>
    <div class="row" style="margin-top:2px">
      <button class="b-val" type="button" onclick="doValidate()">Validate credentials &amp; folders</button>
      <button class="b-save" type="button" onclick="doSave()">Save .env</button>
      <button class="b-fin" id="b-fin" type="button" onclick="doFinish()" disabled>Finish &amp; start main server</button>
    </div>
    <div id="results"></div>
    <div id="banner"></div>
  </div>
</div>

<script>
let saved = false;
const FIELDS = ["WOMS_PORT","WOMS_JWT_SECRET","WOMS_CORS_ORIGINS","BACKUP_ENABLED","LOCAL_BACKUP_PATH",
 "BACKUP_DAILY_RETENTION","BACKUP_WEEKLY_RETENTION","BACKUP_MONTHLY_RETENTION","BACKUP_ENCRYPTION_ENABLED",
 "BACKUP_ENCRYPTION_KEY","BACKUP_PATHS","SMB_BACKUP_ENABLED","SMB_MODE","SMB_MOUNT_PATH","SMB_SERVER",
 "SMB_SHARE","SMB_DOMAIN","SMB_USERNAME","SMB_PASSWORD","FILES_SMB_SERVER","FILES_SMB_SHARE","FILES_SMB_DOMAIN",
 "FILES_SMB_USERNAME","FILES_SMB_PASSWORD","FILES_SMB_MOUNT_PATH","NETDRIVE_PATH"];

function collect(){ const v={}; for (const f of FIELDS) v[f]=document.getElementById(f).value; return v; }
function fill(values){ for (const f of FIELDS){ const el=document.getElementById(f); if(el && values[f]!==undefined && values[f]!==null) el.value=values[f]; } mirrorMount(); }
function mirrorMount(){ document.getElementById("SMB_MOUNT_PATH_BACKUP_DISPLAY").value = document.getElementById("SMB_MOUNT_PATH").value; }
function encChanged(){ document.getElementById("genkey").style.display = document.getElementById("BACKUP_ENCRYPTION_ENABLED").value==="true" ? "inline-block":"none"; }
async function genSecret(){ const d=await (await fetch("/api/generate")).json(); document.getElementById("WOMS_JWT_SECRET").value=d.jwt_secret; }
async function genKey(){ const d=await (await fetch("/api/generate")).json(); document.getElementById("BACKUP_ENCRYPTION_KEY").value=d.enc_key; }

function esc(s){ const d=document.createElement("div"); d.textContent=s??""; return d.innerHTML; }
function render(results){
  const box=document.getElementById("results"); box.innerHTML="";
  for (const r of results){
    const div=document.createElement("div"); div.className="res "+r.status;
    div.innerHTML = '<span class="tag">'+esc(r.status)+'</span><span><b>'+esc(r.label)+'</b></span><span class="det">'+esc(r.detail)+'</span>';
    box.appendChild(div);
  }
}
async function doValidate(){
  const r=await (await fetch("/api/validate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({values:collect()})})).json();
  render(r.results);
}
async function doSave(){
  const resp=await fetch("/api/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({values:collect()})});
  const r=await resp.json(); render(r.results||[]);
  const b=document.getElementById("banner"); b.style.display="block";
  if (r.ok){ saved=true; document.getElementById("b-fin").disabled=false; document.getElementById("b-fin").classList.add("ready");
    b.innerHTML="&#10003; "+esc(r.detail)+"<br>Mount both shares above (or run <span class='mono'>"+esc(r.commands_path)+"</span>), then press <b>Finish</b>."; }
  else { b.style.background="#2a0808"; b.style.color="#fecaca"; b.textContent="Not saved: "+(r.detail||"fix the errors below"); }
}
async function doFinish(){
  if(!saved){ const ok=confirm("Save .env first?"); if(ok) return doSave(); return; }
  const r=await (await fetch("/api/finish",{method:"POST"})).json();
  if(r.ok){ const b=document.getElementById("banner"); b.style.display="block"; b.style.background="#052e16"; b.style.color="#bbf7d0";
    b.innerHTML="&#10003; Wizard closed. The main server is starting from the new .env &mdash; you can close this tab. Dashboard: <span class='mono'>http://&lt;server&gt;:8000</span>";
    document.getElementById("b-fin").disabled=true; }
  else { alert(r.detail||"Could not finish"); }
}
async function doMount(which){
  const r=await (await fetch("/api/mount",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({which,values:collect()})})).json();
  const box=document.getElementById("results");
  const div=document.createElement("div"); div.className="res "+r.result.status;
  div.innerHTML='<span class="tag">'+esc(r.result.status)+'</span><span><b>'+esc(r.result.label)+'</b></span><span class="det">'+esc(r.result.detail)+'</span>';
  box.prepend(div);
}
window.addEventListener("DOMContentLoaded", async () => {
  const d=await (await fetch("/api/defaults")).json(); fill(d.values||{}); encChanged(); mirrorMount();
  document.getElementById("SMB_MOUNT_PATH").addEventListener("input", mirrorMount);
});
</script>
</body>
</html>
"""


def main() -> None:  # pragma: no cover - manual run helper
    import uvicorn

    print(f"[setup-wizard] form: http://0.0.0.0:{WIZARD_PORT}  (Ctrl+C when done)")
    uvicorn.run(app, host="0.0.0.0", port=WIZARD_PORT, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
