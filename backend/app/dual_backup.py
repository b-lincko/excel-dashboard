from __future__ import annotations

"""Dual backup: one verified package -> LOCAL copy + SMB network copy.

Added 2026-09-12 on top of the existing pair-based backup core
(excel_service.create_backup + database.snapshot_to, which already do the
SQLite backup-API snapshot with WAL checkpointing and row-count health).

Flow (see docs/backup.md):
  1. collect      - sqlite snapshot + Excel replica + uploads + configs
  2. package      - one zip with manifest.json (per-file sha256)
  3. checksum     - SHA-256 of the (optionally encrypted) artifact
  4. LOCAL        - write Daily/ (plus Weekly/ + Monthly/ tier copies), verify
  5. SMB          - copy to the MR-Backup share (CIFS mount or smbclient),
                    verify by re-reading and hashing the remote copy
  6. record       - status JSON + audit log (no secrets)
  7. retention    - independent Daily/Weekly/Monthly pruning per destination

Destinations are independent: a failed SMB push never deletes or disqualifies
the local copy. Overall result: SUCCESS | PARTIAL_SUCCESS | FAILED.

Configuration comes from environment variables only (secrets never enter
app_config.json, which is itself backed up) - see .env.example.
"""

import base64
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import database
from .config import ROOT

APP_NAME = "Linkco MR"
APP_VERSION = "1.0.0"

RETENTION_DEFAULTS = {"daily": 7, "weekly": 4, "monthly": 12}
EXTRACT_CAP = 40  # max additional BACKUP_PATHS entries honored


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


class DualConfig:
    """Snapshot of the environment configuration for one run."""

    def __init__(self) -> None:
        self.enabled = _env_bool("BACKUP_ENABLED", True)
        self.local_path = Path(_env("LOCAL_BACKUP_PATH", str(ROOT / "backup"))).expanduser()
        self.smb_enabled = _env_bool("SMB_BACKUP_ENABLED", False)
        self.smb_mode = _env("SMB_MODE", "mount").lower()  # mount | smbclient
        self.smb_mount_path = Path(_env("SMB_MOUNT_PATH", "/mnt/mr-backup")).expanduser()
        self.smb_server = _env("SMB_SERVER")
        self.smb_share = _env("SMB_SHARE", "MR-Backup")
        self.smb_username = _env("SMB_USERNAME")
        self.smb_password = _env("SMB_PASSWORD")
        self.smb_domain = _env("SMB_DOMAIN")
        self.daily_keep = _env_int("BACKUP_DAILY_RETENTION", RETENTION_DEFAULTS["daily"])
        self.weekly_keep = _env_int("BACKUP_WEEKLY_RETENTION", RETENTION_DEFAULTS["weekly"])
        self.monthly_keep = _env_int("BACKUP_MONTHLY_RETENTION", RETENTION_DEFAULTS["monthly"])
        self.encrypt = _env_bool("BACKUP_ENCRYPTION_ENABLED", False)
        self.encrypt_key_b64 = _env("BACKUP_ENCRYPTION_KEY")
        self.extra_paths = [
            p
            for p in re_split_paths(_env("BACKUP_PATHS"))
            if p
        ][:EXTRACT_CAP]

    def describe(self) -> dict[str, Any]:
        """Status-safe description (never includes the password or key)."""
        target = f"mount:{self.smb_mount_path}" if self.smb_mode == "mount" else f"//{self.smb_server}/{self.smb_share}"
        return {
            "enabled": self.enabled,
            "local_path": str(self.local_path),
            "smb_enabled": self.smb_enabled,
            "smb_mode": self.smb_mode,
            "smb_target": target if self.smb_enabled else "",
            "smb_username": self.smb_username if self.smb_enabled else "",
            "retention": {"daily": self.daily_keep, "weekly": self.weekly_keep, "monthly": self.monthly_keep},
            "encryption": self.encrypt,
            "extra_paths": len(self.extra_paths),
        }


def re_split_paths(raw: str) -> list[str]:
    if not raw:
        return []
    parts = raw.replace(";", ":").split(":") if os.name != "nt" else raw.split(";")
    return [p.strip() for p in parts if p.strip()]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _aesgcm(key_b64: str):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError("BACKUP_ENCRYPTION_ENABLED but the 'cryptography' package is not installed") from exc
    key = base64.urlsafe_b64decode(key_b64.encode())
    if len(key) != 32:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY must decode to 32 bytes (AES-256). Generate with: python -c \"import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())\"")
    return AESGCM(key)


def _encrypt_bytes(data: bytes, key_b64: str) -> bytes:
    aes = _aesgcm(key_b64)
    nonce = os.urandom(12)
    return nonce + aes.encrypt(nonce, data, None)


def _decrypt_bytes(data: bytes, key_b64: str) -> bytes:
    aes = _aesgcm(key_b64)
    nonce, ct = data[:12], data[12:]
    return aes.decrypt(nonce, ct, None)


def _log(events: list[dict[str, Any]], event: str, detail: str = "") -> None:
    events.append({"event": event, "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "detail": detail})
    print(f"[DUAL-BACKUP] {event}" + (f" {detail}" if detail else ""), flush=True)


def _safe_tree_size(root: Path) -> tuple[int, int]:
    files = 0
    total = 0
    for p in root.rglob("*"):
        if p.is_file():
            files += 1
            total += p.stat().st_size
    return files, total


# --------------------------------------------------------------------------- #
# package collection
# --------------------------------------------------------------------------- #

def _collect_package(stage: Path, pair_excel: Optional[Path], pair_db: Optional[Path], cfg: DualConfig, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stage the payload files; return the manifest file list."""
    from . import config as app_config

    files: list[dict[str, Any]] = []

    def add(src: Path, rel: str) -> None:
        dest = stage / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        files.append({"path": rel, "size": src.stat().st_size, "sha256": _sha256_file(src)})

    # database: consistent snapshot through the SQLite backup API (never a raw copy)
    db_dest = stage / "db" / "woms.db"
    db_dest.parent.mkdir(parents=True, exist_ok=True)
    database.snapshot_to(db_dest)
    files.append({"path": "db/woms.db", "size": db_dest.stat().st_size, "sha256": _sha256_file(db_dest)})

    # Excel replica from the SAME verified pair moment
    if pair_excel and Path(pair_excel).is_file():
        add(Path(pair_excel), "excel/" + Path(pair_excel).name)

    # configuration required to restore
    cfg_json = Path(app_config.CONFIG_PATH)
    if cfg_json.is_file():
        add(cfg_json, "config/app_config.json")
    jwt = app_config.DATA_DIR / ".jwt_secret"
    if jwt.is_file():
        add(jwt, "config/.jwt_secret")

    # uploads / attachments
    att = Path(app_config.ATTACHMENTS_DIR)
    if att.is_dir():
        n = 0
        for p in sorted(att.rglob("*")):
            if p.is_file():
                add(p, "uploads/" + str(p.relative_to(att)))
                n += 1
                if n >= 5000:
                    break

    # any extra operator-configured paths (BACKUP_PATHS)
    for i, raw in enumerate(cfg.extra_paths):
        p = Path(raw).expanduser()
        if p.is_dir():
            base = "extra/" + (p.name or f"extra{i}")
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    add(f, f"{base}/{f.relative_to(p)}")
        elif p.is_file():
            add(p, f"extra/{p.name}")

    _log(events, "BACKUP_COLLECTED", f"files={len(files)}")
    return files


def _build_manifest(backup_id: str, files: list[dict[str, Any]], cfg: DualConfig) -> dict[str, Any]:
    return {
        "backup_id": backup_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "application": APP_NAME,
        "version": APP_VERSION,
        "database": "sqlite",
        "source": socket.gethostname(),
        "files": files,
        "encryption": bool(cfg.encrypt),
        "retention": {"daily": cfg.daily_keep, "weekly": cfg.weekly_keep, "monthly": cfg.monthly_keep},
    }


# --------------------------------------------------------------------------- #
# SMB transport
# --------------------------------------------------------------------------- #

def _smb_unc(cfg: DualConfig, rel: str = "") -> str:
    unc = f"//{cfg.smb_server}/{cfg.smb_share}"
    return f"{unc}/{rel}" if rel else unc


def _smbclient_conn(cfg: DualConfig, tmpdir: Path) -> Path:
    """Write a temporary smbclient auth file (0600, deleted by caller cleanup)."""
    auth = tmpdir / "smb-auth"
    lines = [f"username = {cfg.smb_username}", f"password = {cfg.smb_password}"]
    if cfg.smb_domain:
        lines.append(f"domain = {cfg.smb_domain}")
    auth.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(auth, 0o600)
    return auth


def _smbclient_run(cfg: DualConfig, auth: Path, command: str, timeout: int = 120) -> tuple[bool, str]:
    if not shutil.which("smbclient"):
        return False, "smbclient binary is not installed on this host"
    try:
        proc = subprocess.run(
            ["smbclient", _smb_unc(cfg), "-A", str(auth), "-c", command, "-t", str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 30,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0 and "NT_STATUS" not in out
        return ok, out.strip()[-400:]
    except subprocess.TimeoutExpired:
        return False, "smbclient timed out"
    except OSError as exc:
        return False, f"smbclient failed to start: {exc}"


def _smb_mkdirs(cfg: DualConfig, auth: Path, rel_dir: str) -> tuple[bool, str]:
    if cfg.smb_mode == "mount":
        try:
            (cfg.smb_mount_path / rel_dir).mkdir(parents=True, exist_ok=True)
            return True, ""
        except OSError as exc:
            return False, f"SMB target not writable ({cfg.smb_mount_path}): {exc}"
    parts = Path(rel_dir).parts
    path = ""
    for part in parts:
        path = f"{path}\\{part}" if path else part
        ok, msg = _smbclient_run(cfg, auth, f'mkdir "{path}"')
        if not ok and "NT_STATUS_OBJECT_NAME_COLLISION" not in msg and "exists" not in msg.lower():
            return False, msg
    return True, ""


def _smb_push_file(cfg: DualConfig, auth: Path, rel_dir: str, name: str, src: Path) -> tuple[bool, str]:
    if cfg.smb_mode == "mount":
        try:
            dest_dir = cfg.smb_mount_path / rel_dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_dir / name)
            return True, ""
        except OSError as exc:
            return False, f"SMB copy failed: {exc}"
    remote_rel = rel_dir.replace("/", "\\")
    remote = f"{remote_rel}\\{name}"
    return _smbclient_run(cfg, auth, f'put "{src}" "{remote}"')


def _smb_fetch_file(cfg: DualConfig, auth: Path, tmpdir: Path, rel_dir: str, name: str) -> tuple[Optional[bytes], str]:
    """Read a remote file back for verification."""
    if cfg.smb_mode == "mount":
        try:
            p = cfg.smb_mount_path / rel_dir / name
            if not p.is_file():
                return None, "remote file is missing"
            return p.read_bytes(), ""
        except OSError as exc:
            return None, f"could not read the SMB copy back: {exc}"
    remote_rel = rel_dir.replace("/", "\\")
    remote = f"{remote_rel}\\{name}"
    dest = tmpdir / "smb-verify-download"
    ok, msg = _smbclient_run(cfg, auth, f'get "{remote}" "{dest}"')
    if not ok or not dest.is_file():
        return None, msg or "could not read the remote copy back"
    return dest.read_bytes(), ""


# --------------------------------------------------------------------------- #
# retention
# --------------------------------------------------------------------------- #

def _tier_dirs(root: Path, tier: str) -> list[Path]:
    base = root / tier.title()
    if not base.is_dir():
        return []
    return sorted([d for d in base.iterdir() if d.is_dir()], key=lambda d: d.name, reverse=True)


def apply_retention(root: Path, daily: int, weekly: int, monthly: int) -> dict[str, int]:
    """Prune Daily/Weekly/Monthly independently. Returns removed counts."""
    removed = {"daily": 0, "weekly": 0, "monthly": 0}
    for tier, keep in (("daily", daily), ("weekly", weekly), ("monthly", monthly)):
        if keep <= 0:
            continue
        for d in _tier_dirs(root, tier.title())[keep:]:
            try:
                shutil.rmtree(d)
                removed[tier] += 1
            except OSError:
                continue
    return removed


# --------------------------------------------------------------------------- #
# main entry
# --------------------------------------------------------------------------- #

def run_dual_backup(pair: Optional[Path] = None, reason: str = "manual") -> Optional[dict[str, Any]]:
    """Create one package and store it locally + on SMB. Never raises."""
    cfg = DualConfig()
    if not cfg.enabled:
        return None

    started = datetime.now()
    backup_id = started.strftime("%Y-%m-%d_%H%M%S")
    events: list[dict[str, Any]] = []
    status: dict[str, Any] = {
        "backup_id": backup_id,
        "reason": reason,
        "started": started.strftime("%Y-%m-%d %H:%M:%S"),
        "overall": "FAILED",
        "local": {"status": "PENDING", "verification": "", "path": "", "size": 0, "sha256": ""},
        "smb": {"status": "SKIPPED", "verification": "", "path": "", "size": 0, "sha256": "", "reason": "disabled"},
        "encrypted": cfg.encrypt,
        "artifact": "",
        "config": cfg.describe(),
        "log": events,
    }

    tmpdir = Path(tempfile.mkdtemp(prefix="dual-backup-"))
    try:
        _log(events, "BACKUP_STARTED", f"id={backup_id} reason={reason}")
        if cfg.encrypt and not cfg.encrypt_key_b64:
            raise RuntimeError("BACKUP_ENCRYPTION_ENABLED is set but BACKUP_ENCRYPTION_KEY is missing")

        # -- source pair: reuse the auto pair, or create a fresh manual one ----
        pair_excel: Optional[Path] = None
        pair_db: Optional[Path] = None
        if pair is not None:
            p = Path(pair)
            if p.suffix.lower() == ".xlsx":
                pair_excel = p
                pair_db = p.with_suffix(".db") if p.with_suffix(".db").is_file() else None
            else:
                pair_db = p
        else:
            from .excel.service import excel_service

            try:
                excel_service.export_database_to_excel(username="system")
            except Exception as exc:
                _log(events, "EXCEL_EXPORT_SKIPPED", str(exc)[:200])
            made = excel_service.create_backup(reason="manual")
            if made is not None:
                if made.suffix.lower() == ".xlsx":
                    pair_excel = made
                    pair_db = made.with_suffix(".db") if made.with_suffix(".db").is_file() else None
                else:
                    pair_db = made

        # -- collect + package -------------------------------------------------
        stage = tmpdir / "package"
        files = _collect_package(stage, pair_excel, pair_db, cfg, events)
        manifest = _build_manifest(backup_id, files, cfg)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        _log(events, "BACKUP_ARCHIVE_STARTED", f"files={len(files) + 1}")

        import zipfile

        zip_path = tmpdir / f"backup_{backup_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(stage.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(stage).as_posix())
        _log(events, "BACKUP_ARCHIVE_CREATED", f"size={zip_path.stat().st_size}")

        payload = zip_path.read_bytes()
        if cfg.encrypt:
            payload = _encrypt_bytes(payload, cfg.encrypt_key_b64)
        ext = ".zip.enc" if cfg.encrypt else ".zip"
        artifact_name = f"backup_{backup_id}{ext}"
        artifact = tmpdir / artifact_name
        artifact.write_bytes(payload)
        artifact_sha = _sha256_bytes(payload)
        status["artifact"] = artifact_name
        status["sha256"] = artifact_sha

        # sidecars written next to every copy
        meta = {
            "backup_id": backup_id,
            "created_at": started.isoformat(timespec="seconds"),
            "artifact": artifact_name,
            "size": len(payload),
            "sha256": artifact_sha,
            "encrypted": cfg.encrypt,
            "application": APP_NAME,
        }
        meta_blob = json.dumps(meta, indent=2)
        sha_blob = f"{artifact_sha}  {artifact_name}\n"
        (tmpdir / f"{artifact_name}.sha256").write_text(sha_blob, encoding="utf-8")
        (tmpdir / f"{artifact_name}.meta.json").write_text(meta_blob, encoding="utf-8")

        date_dir = started.strftime("%Y-%m-%d")
        week_dir = started.strftime("%G-W%V")
        month_dir = started.strftime("%Y-%m")

        # -- LOCAL --------------------------------------------------------------
        _log(events, "LOCAL_BACKUP_STARTED")
        local_daily = cfg.local_path / "Daily" / date_dir
        local_daily.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact, local_daily / artifact_name)
        (local_daily / f"{artifact_name}.sha256").write_text(sha_blob, encoding="utf-8")
        (local_daily / f"{artifact_name}.meta.json").write_text(meta_blob, encoding="utf-8")
        stored = local_daily / artifact_name
        local_ok = _sha256_file(stored) == artifact_sha
        status["local"] = {
            "status": "SUCCESS" if local_ok else "FAILED",
            "verification": "PASSED" if local_ok else "FAILED",
            "path": str(stored),
            "size": stored.stat().st_size,
            "sha256": artifact_sha,
        }
        _log(events, "LOCAL_BACKUP_VERIFIED" if local_ok else "LOCAL_BACKUP_FAILED", str(stored))

        # weekly + monthly tier copies (same artifact, separate folders)
        if local_ok:
            for tier, tier_dir_name in (("Weekly", week_dir), ("Monthly", month_dir)):
                tier_base = cfg.local_path / tier
                tier_dir = tier_base / tier_dir_name
                if not any(tier_dir.glob("backup_*")):
                    tier_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(artifact, tier_dir / artifact_name)
                    (tier_dir / f"{artifact_name}.sha256").write_text(sha_blob, encoding="utf-8")

        # -- SMB ----------------------------------------------------------------
        if not cfg.smb_enabled:
            status["smb"] = {"status": "SKIPPED", "verification": "", "path": "", "size": 0, "sha256": "", "reason": "SMB backup is disabled", "mount_warning": ""}
            _log(events, "SMB_BACKUP_SKIPPED", "disabled")
        else:
            _log(events, "SMB_CONNECTION_STARTED", f"mode={cfg.smb_mode} target={status['config']['smb_target']}")
            mount_warning = ""
            if cfg.smb_mode == "mount" and not os.path.ismount(str(cfg.smb_mount_path)):
                # A plain folder at SMB_MOUNT_PATH means the share was never
                # mounted: backups "succeed" into a local directory and never
                # reach the file server. Warn instead of failing (bind mounts
                # and CIFS both report as mounts).
                mount_warning = (
                    f"{cfg.smb_mount_path} is a plain folder on the app server, not a mounted share - "
                    f"copies are NOT reaching the file server. Mount //{cfg.smb_server or '<server>'}/{cfg.smb_share} "
                    f"at {cfg.smb_mount_path} (docs/backup.md section 4) or set SMB_MODE=smbclient."
                )
                _log(events, "SMB_TARGET_NOT_MOUNTED", mount_warning)
            auth = _smbclient_conn(cfg, tmpdir) if cfg.smb_mode == "smbclient" else None
            try:
                pushed = True
                push_msg = ""
                targets = [("Daily", date_dir)]
                for tier, tier_dir_name in (("Weekly", week_dir), ("Monthly", month_dir)):
                    existing = cfg.smb_mount_path / tier / tier_dir_name if cfg.smb_mode == "mount" else None
                    already = bool(existing and any(existing.glob("backup_*"))) if existing is not None else False
                    if not already:
                        targets.append((tier, tier_dir_name))
                for tier, tier_dir_name in targets:
                    if not pushed:
                        break
                    ok, msg = _smb_mkdirs(cfg, auth, f"{tier}/{tier_dir_name}")
                    if not ok:
                        pushed, push_msg = False, msg or f"could not create {tier} folder on the SMB share"
                        break
                    ok, msg = _smb_push_file(cfg, auth, f"{tier}/{tier_dir_name}", artifact_name, artifact)
                    if not ok:
                        pushed, push_msg = False, msg or "copy to the SMB share failed"
                        break
                    _smb_push_file(cfg, auth, f"{tier}/{tier_dir_name}", f"{artifact_name}.sha256", tmpdir / f"{artifact_name}.sha256")

                smb_status = "FAILED"
                smb_ver = "FAILED"
                smb_reason = push_msg
                remote_path = f"{status['config']['smb_target']}/Daily/{date_dir}/{artifact_name}"
                if pushed:
                    _log(events, "SMB_BACKUP_STARTED", artifact_name)
                    data, msg = _smb_fetch_file(cfg, auth, tmpdir, f"Daily/{date_dir}", artifact_name)
                    if data is None:
                        smb_reason = msg or "could not read the SMB copy back"
                    elif _sha256_bytes(data) != artifact_sha:
                        smb_reason = "SMB BACKUP VERIFICATION FAILED - checksum mismatch on the SMB copy"
                        # remove the bad copy so nobody restores from it
                        try:
                            if cfg.smb_mode == "mount":
                                (cfg.smb_mount_path / "Daily" / date_dir / artifact_name).unlink(missing_ok=True)
                        except OSError:
                            pass
                    else:
                        smb_status = "SUCCESS"
                        smb_ver = "PASSED"
                        smb_reason = ""
                        _log(events, "SMB_BACKUP_VERIFIED", remote_path)
                if smb_status != "SUCCESS":
                    _log(events, "SMB_BACKUP_FAILED", smb_reason[:200])
                size = 0
                if smb_status == "SUCCESS" and cfg.smb_mode == "mount":
                    size = (cfg.smb_mount_path / "Daily" / date_dir / artifact_name).stat().st_size
                status["smb"] = {
                    "status": smb_status,
                    "verification": smb_ver,
                    "path": remote_path if smb_status == "SUCCESS" else "",
                    "size": size,
                    "sha256": artifact_sha if smb_status == "SUCCESS" else "",
                    "reason": smb_reason or mount_warning,
                    "mount_warning": mount_warning,
                }
            finally:
                if auth is not None:
                    try:
                        auth.unlink(missing_ok=True)
                    except OSError:
                        pass

        # -- overall ------------------------------------------------------------
        local_s = status["local"]["status"]
        smb_s = status["smb"]["status"]
        if local_s == "SUCCESS" and smb_s in {"SUCCESS", "SKIPPED"}:
            status["overall"] = "SUCCESS"
        elif local_s == "SUCCESS" or smb_s == "SUCCESS":
            status["overall"] = "PARTIAL_SUCCESS"
        else:
            status["overall"] = "FAILED"

        finished = datetime.now()
        status["finished"] = finished.strftime("%Y-%m-%d %H:%M:%S")
        status["duration_s"] = round((finished - started).total_seconds(), 1)

        # -- record -------------------------------------------------------------
        record_dir = cfg.local_path / "status"
        try:
            record_dir.mkdir(parents=True, exist_ok=True)
            (record_dir / f"backup_{backup_id}.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        except OSError:
            pass
        try:
            database.set_sync_meta("last_dual_backup", json.dumps({k: status[k] for k in ("backup_id", "started", "finished", "overall", "duration_s")}, default=str))
        except Exception:
            pass
        try:
            database.add_audit(
                "system",
                "dual_backup",
                details=f"id={backup_id} overall={status['overall']} local={local_s} smb={smb_s}"
                + (f" smb_reason={status['smb']['reason'][:120]}" if status["smb"].get("reason") and smb_s == "FAILED" else ""),
            )
        except Exception:
            pass

        # -- retention (independent per destination) ----------------------------
        _log(events, "RETENTION_STARTED")
        try:
            removed_local = apply_retention(cfg.local_path, cfg.daily_keep, cfg.weekly_keep, cfg.monthly_keep)
            _log(events, "RETENTION_LOCAL_DONE", json.dumps(removed_local))
        except Exception as exc:
            _log(events, "RETENTION_LOCAL_FAILED", str(exc)[:200])
        if cfg.smb_enabled and status["smb"]["status"] == "SUCCESS":
            try:
                if cfg.smb_mode == "mount":
                    removed_smb = apply_retention(cfg.smb_mount_path, cfg.daily_keep, cfg.weekly_keep, cfg.monthly_keep)
                    _log(events, "RETENTION_SMB_DONE", json.dumps(removed_smb))
                # smbclient mode: pruning happens server-side; documented in docs/backup.md
            except Exception as exc:
                _log(events, "RETENTION_SMB_FAILED", str(exc)[:200])

        _log(events, "BACKUP_COMPLETED", f"overall={status['overall']}")
        return status
    except Exception as exc:
        _log(events, "BACKUP_FAILED", str(exc)[:300])
        status["overall"] = "FAILED"
        status["error"] = str(exc)[:300]
        status["finished"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status["log"] = events
        try:
            record_dir = cfg.local_path / "status"
            record_dir.mkdir(parents=True, exist_ok=True)
            (record_dir / f"backup_{backup_id}.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        except Exception:
            pass
        return status
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def read_status_history(limit: int = 10) -> list[dict[str, Any]]:
    """Recent dual-backup status records (newest first)."""
    cfg = DualConfig()
    base = cfg.local_path / "status"
    if not base.is_dir():
        return []
    out = []
    for p in sorted(base.glob("backup_*.json"), reverse=True)[: max(1, limit)]:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def last_status() -> Optional[dict[str, Any]]:
    history = read_status_history(limit=1)
    return history[0] if history else None
