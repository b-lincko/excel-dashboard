#!/usr/bin/env python3
"""Restore a dual-backup package (.zip / .zip.enc) into the application.

Usage (from the backend folder, venv active):
    python dual_restore.py <backup.zip | backup.zip.enc> [--list] [--yes]
                           [--data-dir DIR] [--excel FILE] [--no-config]

Validation BEFORE anything is overwritten:
  * artifact checksum verified against the .sha256 sidecar when present
  * decryption (AES-256-GCM, authenticated) when the package is encrypted
  * every manifest entry re-hashed after extraction
  * SQLite integrity_check + row count on the restored database

A pre-restore safety pair (excel + db) is taken via the existing backup core
before anything is touched. The application should be stopped for a full
restore; the database itself is written through the safe backup-API path.

Examples:
  python dual_restore.py /backup/Daily/2026-09-12/backup_2026-09-12_020000.zip --list
  python dual_restore.py backup_2026-09-12_020000.zip.enc --yes
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

APP_ROOT = ROOT.parent


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _decrypt(data: bytes) -> bytes:
    key_b64 = os.environ.get("BACKUP_ENCRYPTION_KEY", "")
    if not key_b64:
        raise SystemExit("This package is encrypted - set BACKUP_ENCRYPTION_KEY (same key as the server).")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.urlsafe_b64decode(key_b64.encode())
    if len(key) != 32:
        raise SystemExit("BACKUP_ENCRYPTION_KEY must decode to 32 bytes.")
    nonce, ct = data[:12], data[12:]
    try:
        return AESGCM(key).decrypt(nonce, ct, None)
    except Exception as exc:
        raise SystemExit(f"Decryption failed (wrong key or corrupted file): {exc}") from exc


def _verify_sidecar(artifact: Path) -> str:
    """Return the expected sha256 (empty when no sidecar exists)."""
    sidecar = artifact.with_name(artifact.name + ".sha256")
    if sidecar.is_file():
        expected = sidecar.read_text(encoding="utf-8").split()[0].strip().lower()
        actual = _sha256_file(artifact)
        if actual != expected:
            raise SystemExit(f"CHECKSUM MISMATCH: artifact is corrupted.\n  expected {expected}\n  actual   {actual}")
        print(f"[OK] artifact checksum verified ({actual[:16]}…)")
        return expected
    print("[WARN] no .sha256 sidecar next to the artifact - skipping outer check")
    return ""


def open_package(artifact: Path) -> tuple[zipfile.ZipFile, dict, Path, tempfile.TemporaryDirectory]:
    if not artifact.is_file():
        raise SystemExit(f"Backup not found: {artifact}")
    _verify_sidecar(artifact)
    raw = artifact.read_bytes()
    if artifact.name.endswith(".enc"):
        raw = _decrypt(raw)
    tmp = tempfile.TemporaryDirectory(prefix="dual-restore-")
    zpath = Path(tmp.name) / "package.zip"
    zpath.write_bytes(raw)
    try:
        zf = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile:
        tmp.cleanup()
        raise SystemExit("This file is not a valid backup package (zip).")
    try:
        manifest = json.loads(zf.read("manifest.json"))
    except KeyError:
        zf.close()
        tmp.cleanup()
        raise SystemExit("Not a dual-backup package (manifest.json missing).")
    return zf, manifest, zpath, tmp


def verify_package(zf: zipfile.ZipFile, manifest: dict) -> list[dict]:
    """Re-hash every manifest entry. Returns the verified file list."""
    bad = []
    verified = []
    for entry in manifest.get("files", []):
        rel = entry["path"]
        try:
            data = zf.read(rel)
        except KeyError:
            bad.append((rel, "missing from the package"))
            continue
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            bad.append((rel, "checksum mismatch"))
            continue
        verified.append(entry)
    if bad:
        for rel, why in bad:
            print(f"[FAIL] {rel}: {why}")
        raise SystemExit("Package verification FAILED - nothing was changed.")
    print(f"[OK] {len(verified)} files verified against the manifest")
    return verified


def check_database(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise SystemExit(f"Restored database failed integrity_check: {ok}")
        try:
            count = conn.execute("SELECT COUNT(*) FROM wo_cache").fetchone()[0]
        except sqlite3.OperationalError:
            count = -1
        return int(count)
    finally:
        conn.close()


def stage_package(zf: zipfile.ZipFile, zpath: Path, tmpname: str) -> Path:
    stage = zpath.parent / tmpname
    zf.extractall(stage)
    return stage


def do_restore(stage: Path, manifest: dict, data_dir: Path, excel_path: Path, restore_config: bool, assume_yes: bool) -> None:
    db_src = stage / "db" / "woms.db"
    count = check_database(db_src)

    excel_src = next((stage / "excel").glob("*.xlsx"), None) if (stage / "excel").is_dir() else None
    att_count = len(list((stage / "uploads").rglob("*"))) if (stage / "uploads").is_dir() else 0
    cfg_files = [p.name for p in (stage / "config").iterdir()] if (stage / "config").is_dir() else []

    print("=" * 62)
    print("RESTORE PLAN")
    print(f"  backup_id     : {manifest.get('backup_id')}")
    print(f"  created       : {manifest.get('created_at')} on {manifest.get('source')}")
    print(f"  database      : sqlite, integrity ok, {count} work orders")
    print(f"  excel replica : {excel_src.name if excel_src else '(not in package)'}")
    print(f"  uploads       : {att_count} files")
    print(f"  config files  : {', '.join(cfg_files) if cfg_files else '(none)'}")
    print(f"  target        : {data_dir} (+ {excel_path})")
    print("=" * 62)
    if not assume_yes:
        answer = input("Type RESTORE to overwrite the live data: ").strip()
        if answer != "RESTORE":
            raise SystemExit("Aborted - nothing was changed.")

    # pre-restore safety snapshot via the existing core (best effort, offline safe)
    try:
        from app.excel.service import excel_service

        made = excel_service.create_backup(reason="pre_restore")
        if made:
            print(f"[OK] pre-restore safety pair: {made}")
    except Exception as exc:
        print(f"[WARN] could not take a pre-restore snapshot: {exc}")

    data_dir.mkdir(parents=True, exist_ok=True)

    # database through the safe backup-API path (consistent even if live)
    from app import database as db_mod

    db_mod.restore_from(db_src)
    print("[OK] database restored")

    if excel_src is not None:
        tmp = excel_path.with_suffix(".xlsx.restore-tmp")
        shutil.copy2(excel_src, tmp)
        os.replace(tmp, excel_path)
        print(f"[OK] Excel replica restored ({excel_path.name})")

    att_src = stage / "uploads"
    if att_src.is_dir():
        from app.config import ATTACHMENTS_DIR

        for f in att_src.rglob("*"):
            if f.is_file():
                dest = ATTACHMENTS_DIR / f.relative_to(att_src)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
        print(f"[OK] uploads restored ({att_count} files)")

    if restore_config:
        cfg_src = stage / "config"
        if cfg_src.is_dir():
            for f in cfg_src.iterdir():
                dest = data_dir / f.name
                tmp = dest.with_suffix(dest.suffix + ".restore-tmp")
                shutil.copy2(f, tmp)
                os.replace(tmp, dest)
                print(f"[OK] config restored: {f.name}")

    print("RESTORE COMPLETE - start the application and verify a few material requests.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Restore a dual-backup package (.zip / .zip.enc).")
    ap.add_argument("artifact", help="path to backup_....zip or .zip.enc")
    ap.add_argument("--list", action="store_true", help="show the manifest and exit (no changes)")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--data-dir", default=str(APP_ROOT / "data"), help="application data dir (default ./data)")
    ap.add_argument("--excel", default=str(APP_ROOT / "file.xlsx"), help="Excel replica path (default ./file.xlsx)")
    ap.add_argument("--no-config", action="store_true", help="do not restore config files")
    args = ap.parse_args()

    artifact = Path(args.artifact).expanduser()
    zf, manifest, zpath, tmp = open_package(artifact)
    try:
        if args.list:
            print(json.dumps(manifest, indent=2))
            return
        verify_package(zf, manifest)
        stage = stage_package(zf, zpath, "staged")
        do_restore(stage, manifest, Path(args.data_dir).expanduser(), Path(args.excel).expanduser(), not args.no_config, args.yes)
    finally:
        zf.close()
        tmp.cleanup()


if __name__ == "__main__":
    main()
