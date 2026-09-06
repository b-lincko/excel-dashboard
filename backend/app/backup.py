from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from . import database
from .config import ROOT, AppConfig, load_config

_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_run_lock = threading.Lock()

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_hhmm(value: str) -> tuple[int, int]:
    text = (value or "02:00").strip()
    parts = text.replace(".", ":").split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return 2, 0
    return max(0, min(23, hour)), max(0, min(59, minute))


def scheduled_days(cfg: AppConfig) -> set[int]:
    days = getattr(cfg, "backup_days", None) or []
    if not days:
        return set(range(7))
    out: set[int] = set()
    for day in days:
        try:
            out.add(int(day) % 7)
        except (TypeError, ValueError):
            continue
    return out or set(range(7))


def parse_last(last_iso: Optional[str]) -> Optional[datetime]:
    if not last_iso:
        return None
    text = str(last_iso).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if len(text) >= 19 else text, fmt)
        except ValueError:
            continue
    return None


def _start_date(cfg: AppConfig):
    text = str(getattr(cfg, "backup_start_date", "") or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def is_due(now: datetime, cfg: AppConfig, last_iso: Optional[str]) -> bool:
    if not getattr(cfg, "backup_auto_enabled", False):
        return False
    start = _start_date(cfg)
    if start and now.date() < start:
        return False
    if now.weekday() not in scheduled_days(cfg):
        return False
    hour, minute = parse_hhmm(getattr(cfg, "backup_time", "02:00"))
    scheduled = datetime(now.year, now.month, now.day, hour, minute, 0)
    if now < scheduled:
        return False
    last = parse_last(last_iso)
    if last and last >= scheduled:
        return False
    return True


def next_run(now: datetime, cfg: AppConfig) -> Optional[datetime]:
    if not getattr(cfg, "backup_auto_enabled", False):
        return None
    hour, minute = parse_hhmm(getattr(cfg, "backup_time", "02:00"))
    days = scheduled_days(cfg)
    start = _start_date(cfg)
    for offset in range(0, 15):
        day = now.date() + timedelta(days=offset)
        if start and day < start:
            continue
        if day.weekday() not in days:
            continue
        candidate = datetime(day.year, day.month, day.day, hour, minute, 0)
        if candidate >= now:
            return candidate
    return None


def schedule_status(cfg: Optional[AppConfig] = None, now: Optional[datetime] = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    now = now or datetime.now()
    nxt = next_run(now, cfg)
    last = database.get_sync_meta("last_auto_backup")
    last_any = database.get_sync_meta("last_backup")
    return {
        "enabled": bool(getattr(cfg, "backup_auto_enabled", False)),
        "folder": str(cfg.backup_dir),
        "time": getattr(cfg, "backup_time", "02:00"),
        "days": sorted(scheduled_days(cfg)),
        "start_date": getattr(cfg, "backup_start_date", "") or "",
        "ratio": int(getattr(cfg, "backup_ratio", 14) or 0),
        "last_auto_backup": last,
        "last_backup": last_any,
        "next_run": nxt.strftime("%Y-%m-%d %H:%M") if nxt else None,
        "due_now": is_due(now, cfg, last),
    }


def run_due_backup(force: bool = False) -> Optional[Path]:
    from .excel.service import excel_service

    cfg = load_config()
    if not force and not is_due(datetime.now(), cfg, database.get_sync_meta("last_auto_backup")):
        return None
    if not excel_service.available():
        return None
    with _run_lock:
        if not force and not is_due(datetime.now(), cfg, database.get_sync_meta("last_auto_backup")):
            return None
        dest = excel_service.create_backup(reason="auto")
        keep = int(getattr(cfg, "backup_ratio", 14) or 0)
        pruned = excel_service.prune_backups(keep, reasons=("auto", "manual"))
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        database.set_sync_meta("last_auto_backup", stamp)
        database.add_audit(
            "system",
            "backup",
            details=f"Automatic backup {dest or ''} (pruned {pruned})",
        )
        return dest


def _loop() -> None:
    while True:
        if _stop.wait(timeout=20):
            break
        try:
            run_due_backup()
        except Exception as exc:
            print(f"[WOMS] autobackup: {exc}")


def start_scheduler() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="woms-autobackup", daemon=True)
    _thread.start()


def stop_scheduler() -> None:
    _stop.set()
    thread = _thread
    if thread and thread.is_alive():
        thread.join(timeout=2)


def _safe_path(raw: str) -> Path:
    text = str(raw or "").strip() or str(load_config().backup_dir)
    path = Path(text).expanduser()
    try:
        return path.resolve()
    except OSError:
        return path


def list_folders(raw: Optional[str] = None) -> dict[str, Any]:
    cfg = load_config()
    if not raw:
        current = _safe_path(cfg.backup_dir)
    else:
        current = _safe_path(raw)
    blocked = {Path("/proc"), Path("/sys"), Path("/dev")}
    if current in blocked or any(current == b or b in current.parents for b in blocked if b.exists()):
        raise ValueError("That folder cannot be listed.")
    exists = current.exists() and current.is_dir()
    parent = str(current.parent) if current.parent != current else None
    folders: list[dict[str, str]] = []
    error = None
    if exists:
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
            for entry in entries:
                if len(folders) >= 400:
                    break
                try:
                    if entry.is_dir() and not entry.name.startswith("."):
                        folders.append({"name": entry.name, "path": str(entry)})
                except OSError:
                    continue
        except OSError as exc:
            error = str(exc)
    writable = bool(exists and os.access(current, os.W_OK))
    roots = _roots()
    return {
        "path": str(current),
        "parent": parent,
        "exists": exists,
        "writable": writable,
        "folders": folders,
        "roots": roots,
        "error": error,
    }


def _roots() -> list[dict[str, str]]:
    items: list[Path] = [ROOT, Path.home(), Path(load_config().backup_dir)]
    if os.name == "nt":
        import string

        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:/")
            if drive.exists():
                items.append(drive)
    else:
        items.append(Path("/"))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in items:
        try:
            resolved = str(path.expanduser().resolve())
        except OSError:
            resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append({"name": path.name or resolved, "path": resolved})
    return out


def ensure_folder(raw: str) -> Path:
    path = _safe_path(raw)
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError("That path is not a folder.")
    probe = path / ".woms-backup-write"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise ValueError(f"Folder is not writable: {exc}") from exc
    return path
