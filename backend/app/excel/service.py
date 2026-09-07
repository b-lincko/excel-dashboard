from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from filelock import FileLock, Timeout
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.workbook import Workbook
from openpyxl.worksheet.formula import ArrayFormula

from .. import database
from ..config import AppConfig, load_config, norm_header
from ..dates import format_date, parse_date

DUE_OFFSETS = {
    "direct cash": 3,
    "local po": 5,
    "international": 10,
    "service": 10,
    "consumable": 2,
    "emergency": 0,
    "alternative": 10,
    "under warranty": 10,
}

DELAY_FIELDS = ("delay_kind", "delay_source", "delay_justification")


def resolve_data_sheet(site: str, available: list[str], labels: Optional[dict[str, str]] = None) -> str:
    """Map a site label to an existing worksheet. Never silently write to another site."""
    site = str(site or "").strip()
    labels = labels or {}
    mapped = None
    for sn, lab in labels.items():
        if site in {sn, str(lab)}:
            mapped = sn
            break
    if mapped and mapped in available:
        return mapped
    if site in available:
        return site
    if site:
        shown = ", ".join(available) or "none"
        raise ValueError(f'There is no Excel sheet for site "{site}". Available: {shown}.')
    if not available:
        raise ValueError("The workbook has no data sheets.")
    return available[0]


def _temp_xlsx(directory: Path) -> Path:
    fd, name = tempfile.mkstemp(suffix=".xlsx", dir=directory)
    os.close(fd)
    return Path(name)


def _is_formula(value: Any) -> bool:
    if isinstance(value, ArrayFormula):
        return True
    return isinstance(value, str) and value.startswith("=")


def _cell_plain(value: Any) -> Any:
    if _is_formula(value):
        return None
    return value


class ExcelUnavailable(Exception):
    pass


class ExcelLocked(Exception):
    pass


class SyncConflict(Exception):
    def __init__(self, message: str, current: Optional[dict] = None):
        super().__init__(message)
        self.current = current


class ExcelService:
    def __init__(self) -> None:
        self._cache: Optional[list[dict[str, Any]]] = None
        self._headers: list[str] = []
        self._mtime: Optional[float] = None
        self._fingerprint: str = ""
        self._stale: bool = False
        self._last_error: Optional[str] = None
        self._delay_columns_ready: bool = False
        self._lock = threading.RLock()

    def cfg(self) -> AppConfig:
        return load_config()

    def excel_path(self) -> Path:
        return Path(self.cfg().excel_path)

    def lock_path(self) -> Path:
        p = self.excel_path()
        return p.with_suffix(p.suffix + ".lock")

    def backup_dir(self) -> Path:
        d = Path(self.cfg().backup_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def available(self) -> bool:
        p = self.excel_path()
        return p.exists() and p.is_file()

    def mtime(self) -> Optional[float]:
        p = self.excel_path()
        if not p.exists():
            return None
        return p.stat().st_mtime

    def mtime_iso(self) -> Optional[str]:
        mt = self.mtime()
        if mt is None:
            return None
        return datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S")

    def fingerprint(self) -> str:
        p = self.excel_path()
        if not p.exists():
            return ""
        h = hashlib.sha256()
        h.update(str(p.stat().st_mtime_ns).encode())
        h.update(str(p.stat().st_size).encode())
        return h.hexdigest()[:16]

    def sync_token(self) -> str:
        return database.get_sync_meta("token") or self._fingerprint or self.fingerprint() or f"db:{database.wo_cache_count()}"

    def data_sheets(self, wb: Workbook) -> list[str]:
        cfg = self.cfg()
        names = [n for n in (cfg.worksheets or []) if n in wb.sheetnames]
        if names:
            return names
        if cfg.worksheet_name in wb.sheetnames:
            return [cfg.worksheet_name]
        return [wb.sheetnames[0]] if wb.sheetnames else []

    def site_label(self, sheet_name: str) -> str:
        return self.cfg().worksheet_labels.get(sheet_name) or sheet_name

    def record_id(self, sheet_name: str, row_number: int) -> str:
        return f"{self.site_label(sheet_name)}:{row_number}"

    def map_row(
        self,
        raw: dict[str, Any],
        row_number: int,
        sheet_name: str,
        cfg: Optional[AppConfig] = None,
        mapping: Optional[dict[str, str]] = None,
        fields: Optional[list[str]] = None,
        site: Optional[str] = None,
    ) -> dict[str, Any]:
        cfg = cfg or self.cfg()
        mapping = mapping or cfg.mapping.excel_to_internal()
        fields = fields or list(cfg.mapping.model_dump().keys())
        site = site or self.site_label(sheet_name)
        internal: dict[str, Any] = {}
        for excel_col, value in raw.items():
            field = mapping.get(norm_header(excel_col))
            if field:
                internal[field] = self._normalize_value(field, value)
        internal["_row"] = row_number
        internal["_sheet"] = sheet_name
        internal["_site"] = site
        internal["record_id"] = f"{site}:{row_number}"
        if not internal.get("department"):
            internal["department"] = site
        for field in fields:
            internal.setdefault(field, "")
        self._apply_due_date(internal)
        return internal

    def _due_offsets(self) -> dict[str, int]:
        cfg = self.cfg()
        offsets = dict(DUE_OFFSETS)
        extra = getattr(cfg, "due_offsets", None) or {}
        for key, days in extra.items():
            try:
                offsets[str(key).strip().lower()] = int(days)
            except (TypeError, ValueError):
                continue
        return offsets

    def _apply_due_date(self, rec: dict[str, Any]) -> None:
        created = parse_date(rec.get("created_date"))
        ptype = str(rec.get("work_type") or "").strip().lower()
        offsets = self._due_offsets()
        default_days = int(getattr(self.cfg(), "due_offset_default_days", 14) or 14)
        if ptype in offsets:
            days = offsets[ptype]
        else:
            days = default_days
        rec["_due_offset_days"] = days
        rec["_due_purchase_type"] = ptype
        if not created:
            stored = parse_date(rec.get("due_date"))
            rec["due_date"] = format_date(stored, with_time=False) if stored else ""
            return
        rec["due_date"] = (created + timedelta(days=days)).strftime("%Y-%m-%d")
        rec["_due_computed"] = True

    def _normalize_value(self, field: str, value: Any) -> Any:
        value = _cell_plain(value)
        if value is None:
            return ""
        if field.endswith("_date") or field in {
            "created_date",
            "scheduled_date",
            "due_date",
            "completion_date",
            "closed_date",
            "last_updated",
        }:
            dt = parse_date(value)
            return format_date(dt) if dt else ""
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        if isinstance(value, int) and field == "work_order_id":
            return str(value)
        return str(value).strip() if isinstance(value, str) else value

    def _load_workbook(self, data_only: bool = False, read_only: bool = False):
        path = self.excel_path()
        if not path.exists():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        try:
            return load_workbook(
                path,
                data_only=data_only,
                read_only=read_only,
                keep_vba=(path.suffix == ".xlsm" and not read_only),
            )
        except PermissionError as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        except Exception as exc:
            raise ExcelUnavailable(f"Excel file could not be opened: {exc}") from exc

    def _sheet(self, wb: Workbook, name: Optional[str] = None):
        name = name or self.cfg().worksheet_name
        if name in wb.sheetnames:
            return wb[name]
        sheets = self.data_sheets(wb)
        return wb[sheets[0]]

    def _read_headers(self, ws) -> list[str]:
        header_row = self.cfg().header_row
        headers: list[str] = []
        for cell in next(ws.iter_rows(min_row=header_row, max_row=header_row)):
            if cell.value is None:
                headers.append(f"Column{cell.column}")
            else:
                headers.append(str(cell.value))
        while headers and headers[-1].startswith("Column"):
            headers.pop()
        return headers

    def _read_sheet_records(self, ws, sheet_name: str) -> tuple[list[str], list[dict[str, Any]]]:
        cfg = self.cfg()
        header_row = cfg.header_row
        start = cfg.data_start_row
        mapping = cfg.mapping.excel_to_internal()
        fields = list(cfg.mapping.model_dump().keys())
        site = self.site_label(sheet_name)
        headers: list[str] = []
        id_field_header = None
        records: list[dict[str, Any]] = []
        empty_streak = 0
        max_col = 40
        for idx, row in enumerate(ws.iter_rows(min_row=header_row, max_col=max_col), start=header_row):
            if idx == header_row:
                headers = []
                for col_i, cell in enumerate(row, start=1):
                    if cell.value is None:
                        headers.append(f"Column{col_i}")
                    else:
                        headers.append(str(cell.value))
                while headers and headers[-1].startswith("Column"):
                    headers.pop()
                max_col = max(len(headers), 1)
                for h in headers:
                    if mapping.get(norm_header(h)) == "work_order_id":
                        id_field_header = h
                        break
                continue
            if idx < start:
                continue
            raw: dict[str, Any] = {}
            empty = True
            for header, cell in zip(headers, row):
                raw[header] = cell.value
                if _cell_plain(cell.value) not in (None, ""):
                    empty = False
            if empty:
                empty_streak += 1
                if empty_streak > 80:
                    break
                continue
            empty_streak = 0
            wo_val = raw.get(id_field_header) if id_field_header else None
            if wo_val in (None, ""):
                continue
            records.append(
                self.map_row(raw, idx, sheet_name, cfg=cfg, mapping=mapping, fields=fields, site=site)
            )
        return headers, records

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None
            self._mtime = None
            self._fingerprint = ""
            self._stale = False
            self._last_error = None
            self._delay_columns_ready = False

    def _serve_cache(self, err: Optional[str] = None) -> list[dict[str, Any]]:
        if self._cache is None:
            try:
                cached = database.load_wo_cache()
            except Exception:
                cached = []
            if cached:
                self._cache = cached
                self._stale = True
                self._last_error = err
                return self._cache
            raise ExcelUnavailable(err or "Excel file is currently unavailable.")
        self._stale = True
        self._last_error = err
        return self._cache

    def _attach_backup(self, rec: dict[str, Any], error: Optional[BaseException] = None) -> dict[str, Any]:
        out = dict(rec or {})
        out.pop("_excel_backup_error", None)
        if error is None:
            out["_excel_backup_ok"] = True
        else:
            out["_excel_backup_ok"] = False
            out["_excel_backup_error"] = str(error)
        return out

    def _merge_mapped(self, current: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
        target = dict(current)
        allowed = set(self.cfg().mapping.model_dump().keys())
        for k, v in (changes or {}).items():
            if str(k).startswith("_") or k in {"record_id", "department"}:
                continue
            if k in allowed:
                target[k] = v if v is not None else ""
        self._apply_due_date(target)
        return target

    def read_workbook(self) -> list[dict[str, Any]]:
        """Read live Excel into mapped records. Does not write SQLite."""
        mt = self.mtime()
        if not self.available():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        wb = self._load_workbook(data_only=False, read_only=True)
        try:
            all_records: list[dict[str, Any]] = []
            headers: list[str] = []
            mapping_exc = self.cfg().mapping.internal_to_excel()
            needed = [norm_header(mapping_exc.get(f, "")) for f in DELAY_FIELDS]
            delay_ready_all = True
            for sheet_name in self.data_sheets(wb):
                ws = wb[sheet_name]
                hdrs, recs = self._read_sheet_records(ws, sheet_name)
                if hdrs:
                    headers = hdrs
                present = {norm_header(h) for h in hdrs}
                if not all(n in present for n in needed if n):
                    delay_ready_all = False
                all_records.extend(recs)
        finally:
            wb.close()
        self._headers = [norm_header(h) for h in headers]
        self._delay_columns_ready = delay_ready_all and bool(headers)
        self._mtime = mt
        self._fingerprint = self.fingerprint()
        return all_records

    def seed_from_excel(self, username: str = "seed", replace_lines: bool = False) -> dict[str, Any]:
        try:
            records = self.read_workbook()
        except (ExcelLocked, ExcelUnavailable, PermissionError, OSError) as exc:
            return {"ok": False, "error": str(exc), "count": database.wo_cache_count()}
        except Exception as exc:
            return {"ok": False, "error": f"Could not read Excel: {exc}", "count": database.wo_cache_count()}
        try:
            n = database.replace_wo_cache(records, self._fingerprint or self.fingerprint())
        except Exception as exc:
            return {"ok": False, "error": f"Database seed failed: {exc}", "count": 0}
        self._cache = records
        self._stale = False
        self._last_error = None
        try:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            database.set_sync_meta("last_seed", stamp)
            database.set_sync_meta("last_read", stamp)
            database.set_sync_meta("mtime", self.mtime_iso() or "")
            database.set_sync_meta("token", self._fingerprint or stamp)
            database.set_sync_meta("count", str(n))
            database.add_audit(username, "seed", details=f"Seeded {n} material requests from Excel")
        except Exception:
            pass
        if replace_lines:
            try:
                self._seed_catalog(records, username)
            except Exception as exc:
                return {"ok": True, "count": n, "error": None, "warning": f"Catalog seed skipped: {exc}"}
        return {"ok": True, "count": n, "error": None}

    def _seed_catalog(self, records: list[dict[str, Any]], username: str) -> None:
        known = {s["name"].lower() for s in database.list_suppliers() if s.get("name")}
        for rec in records:
            name = str(rec.get("supplier") or "").strip()
            if name and name.lower() not in known:
                try:
                    database.add_supplier(name, created_by=username)
                    known.add(name.lower())
                except Exception:
                    continue
            rid = str(rec.get("record_id") or "")
            if not rid:
                continue
            desc = str(rec.get("description") or "").strip()
            if name or desc:
                try:
                    database.replace_mr_lines(
                        rid,
                        [{"supplier": name, "material": desc}],
                        created_by=username,
                        work_order_id=str(rec.get("work_order_id") or ""),
                    )
                except Exception:
                    continue

    def load(self, force: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            if force:
                result = self.seed_from_excel(username="refresh")
                if result.get("ok"):
                    return list(self._cache or [])
                recs = database.load_wo_cache()
                if recs:
                    self._cache = recs
                    self._stale = True
                    self._last_error = result.get("error")
                    return recs
                if self._cache is not None:
                    self._stale = True
                    self._last_error = result.get("error")
                    return self._cache
                raise ExcelUnavailable(result.get("error") or "Excel file is currently unavailable.")
            recs = database.load_wo_cache()
            if recs:
                self._cache = recs
                self._stale = False
                self._last_error = None
                return recs
            if self._cache is not None:
                return self._cache
            result = self.seed_from_excel(username="boot")
            if result.get("ok"):
                return list(self._cache or [])
            raise ExcelUnavailable(result.get("error") or "No work orders in the database yet.")

    def headers(self) -> list[str]:
        if self._headers:
            return list(self._headers)
        try:
            self.load()
        except (ExcelUnavailable, ExcelLocked):
            pass
        if self._headers:
            return list(self._headers)
        return [str(v) for v in self.cfg().mapping.model_dump().values() if v]

    def delay_columns_ready(self) -> bool:
        if self._cache is None:
            try:
                self.load()
            except (ExcelUnavailable, ExcelLocked):
                return False
        return bool(self._delay_columns_ready)

    def get_all(self, force: bool = False) -> list[dict[str, Any]]:
        return list(self.load(force=force))

    def get_by_id(self, wo_id: str) -> Optional[dict[str, Any]]:
        rec = database.get_wo_record(wo_id)
        if rec:
            return rec
        wo_id = str(wo_id)
        recs = self.load()
        for item in recs:
            if str(item.get("record_id")) == wo_id:
                return item
        for item in recs:
            if str(item.get("work_order_id")) == wo_id:
                return item
        return None

    def unique_values(self, field: str) -> list[str]:
        values = set()
        for rec in self.load():
            v = rec.get(field)
            if v not in (None, ""):
                values.add(str(v))
        return sorted(values, key=lambda s: s.lower())

    def lists(self) -> dict[str, list[str]]:
        return {}

    SNAPSHOT_REASONS = ("auto", "manual", "pre_restore")

    def create_backup(self, reason: str = "write") -> Optional[Path]:
        src = self.excel_path()
        day = datetime.now().strftime("%Y-%m-%d")
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        dest_dir = self.backup_dir() / day
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest: Optional[Path] = None
        stem = src.stem if src.exists() else "woms"
        if src.exists():
            dest = dest_dir / f"{stem}_{ts}_{reason}{src.suffix}"
            shutil.copy2(src, dest)
            database.set_sync_meta("last_backup", str(dest))
        db_dest = dest_dir / f"{stem}_{ts}_{reason}.db"
        try:
            database.snapshot_to(db_dest)
            if dest is None:
                dest = db_dest
                database.set_sync_meta("last_backup", str(dest))
        except Exception:
            if db_dest.exists():
                db_dest.unlink(missing_ok=True)
        return dest

    def store_uploaded_backup(self, content: bytes, filename: str = "backup.xlsx") -> dict[str, Any]:
        """Save an uploaded snapshot into the backup folder. Does not replace live Excel/DB."""
        if not content or len(content) < 16:
            raise ValueError("The uploaded file is empty or too small.")
        raw_name = Path(filename or "backup.xlsx").name
        lower = raw_name.lower()
        day = datetime.now().strftime("%Y-%m-%d")
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        dest_dir = self.backup_dir() / day
        dest_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(raw_name).stem).strip("._") or "backup"
        stem = stem[:60]
        excel_path: Optional[Path] = None
        db_path: Optional[Path] = None

        def _safe_write(dest: Path, data: bytes) -> None:
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)

        if lower.endswith(".zip"):
            try:
                zf = zipfile.ZipFile(io.BytesIO(content))
            except zipfile.BadZipFile as exc:
                raise ValueError("That zip could not be opened.") from exc
            with zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    parts = Path(info.filename).parts
                    if any(part in {os.pardir, ""} for part in parts):
                        continue
                    name = Path(info.filename).name.lower()
                    data = zf.read(info)
                    if name.endswith((".xlsx", ".xlsm")) and excel_path is None:
                        ext = ".xlsm" if name.endswith(".xlsm") else ".xlsx"
                        excel_path = dest_dir / f"{stem}_{ts}_upload{ext}"
                        _safe_write(excel_path, data)
                        try:
                            self._validate_saved(excel_path)
                        except Exception as exc:
                            excel_path.unlink(missing_ok=True)
                            raise ValueError(f"The Excel file in the zip is not a valid workbook: {exc}") from exc
                    elif name.endswith(".db") and db_path is None:
                        db_path = dest_dir / f"{stem}_{ts}_upload.db"
                        _safe_write(db_path, data)
                        self._validate_db(db_path)
            if excel_path is None and db_path is None:
                raise ValueError("The zip must contain an Excel workbook (.xlsx/.xlsm) and/or a .db snapshot.")
        elif lower.endswith((".xlsx", ".xlsm")):
            ext = ".xlsm" if lower.endswith(".xlsm") else ".xlsx"
            excel_path = dest_dir / f"{stem}_{ts}_upload{ext}"
            _safe_write(excel_path, content)
            try:
                self._validate_saved(excel_path)
            except Exception as exc:
                excel_path.unlink(missing_ok=True)
                raise ValueError(f"That file could not be opened as Excel: {exc}") from exc
        elif lower.endswith(".db"):
            db_path = dest_dir / f"{stem}_{ts}_upload.db"
            _safe_write(db_path, content)
            self._validate_db(db_path)
        else:
            raise ValueError("Upload an Excel workbook (.xlsx/.xlsm), a SQLite snapshot (.db), or a zip of both.")

        dest = excel_path or db_path
        assert dest is not None
        if excel_path is not None and db_path is not None and db_path != excel_path.with_suffix(".db"):
            paired = excel_path.with_suffix(".db")
            if paired != db_path:
                shutil.copy2(db_path, paired)
                if db_path.exists() and db_path != paired:
                    db_path.unlink(missing_ok=True)
                db_path = paired
        database.set_sync_meta("last_backup", str(dest))
        health = None
        try:
            health = self.check_backup(str(dest))
        except Exception as exc:
            health = {"ok": False, "error": str(exc), "path": str(dest)}
        return self._uploaded_meta(dest, health)

    def _validate_db(self, path: Path) -> None:
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            finally:
                con.close()
        except sqlite3.Error as exc:
            path.unlink(missing_ok=True)
            raise ValueError(f"That file is not a readable SQLite database: {exc}") from exc
        if "wo_cache" not in tables and "users" not in tables:
            path.unlink(missing_ok=True)
            raise ValueError("That database does not look like a WOMS snapshot (missing wo_cache/users).")

    def _uploaded_meta(self, dest: Path, health: Optional[dict[str, Any]]) -> dict[str, Any]:
        db_pair = dest if dest.suffix.lower() == ".db" else dest.with_suffix(".db")
        has_db = db_pair.is_file()
        return {
            "path": str(dest),
            "name": dest.name,
            "size": dest.stat().st_size,
            "reason": "upload",
            "health": health,
            "has_db": has_db,
            "db_path": str(db_pair) if has_db else None,
        }

    def backup_files_for_download(self, backup_path: str) -> list[Path]:
        src = self._resolve_backup(backup_path)
        files = [src]
        if src.suffix.lower() in {".xlsx", ".xlsm"}:
            sibling = src.with_suffix(".db")
            if sibling.is_file():
                files.append(sibling)
        elif src.suffix.lower() == ".db":
            for ext in (".xlsx", ".xlsm"):
                sibling = src.with_suffix(ext)
                if sibling.is_file():
                    files.insert(0, sibling)
                    break
        return files

    def list_backups(self, limit: int = 50) -> list[dict[str, Any]]:
        items = []
        root = self.backup_dir()
        if not root.exists():
            return items
        files: list[Path] = []
        for pattern in ("*.xlsx", "*.xlsm"):
            files.extend(root.rglob(pattern))
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        seen: set[str] = set()
        paired_db: set[str] = set()
        for p in files:
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            reason = p.stem.rsplit("_", 1)[-1] if "_" in p.stem else ""
            db_pair = p.with_suffix(".db")
            has_db = db_pair.is_file()
            if has_db:
                try:
                    paired_db.add(str(db_pair.resolve()))
                except OSError:
                    paired_db.add(str(db_pair))
            items.append(
                {
                    "path": str(p),
                    "name": p.name,
                    "size": p.stat().st_size,
                    "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "reason": reason,
                    "folder": str(p.parent),
                    "has_db": has_db,
                    "db_path": str(db_pair) if has_db else None,
                    "db_size": db_pair.stat().st_size if has_db else 0,
                }
            )
            if len(items) >= limit:
                break
        if len(items) < limit:
            db_files = [p for p in root.rglob("*.db") if p.is_file() and not p.name.endswith(".tmp")]
            db_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for p in db_files:
                try:
                    resolved = str(p.resolve())
                except OSError:
                    resolved = str(p)
                if resolved in paired_db:
                    continue
                reason = p.stem.rsplit("_", 1)[-1] if "_" in p.stem else ""
                items.append(
                    {
                        "path": str(p),
                        "name": p.name,
                        "size": p.stat().st_size,
                        "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "reason": reason,
                        "folder": str(p.parent),
                        "has_db": True,
                        "db_path": str(p),
                        "db_size": p.stat().st_size,
                    }
                )
                if len(items) >= limit:
                    break
        return items

    def prune_backups(self, keep: int, reasons: tuple[str, ...] = ("auto", "manual")) -> int:
        keep_n = int(keep or 0)
        if keep_n <= 0:
            return 0
        root = self.backup_dir()
        if not root.exists():
            return 0
        matched: list[Path] = []
        want = {str(r).lower() for r in reasons}
        for p in root.rglob("*.xlsx"):
            tag = p.stem.rsplit("_", 1)[-1].lower() if "_" in p.stem else ""
            if tag in want:
                matched.append(p)
        matched.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        removed = 0
        for p in matched[keep_n:]:
            parent = p.parent
            try:
                sibling = p.with_suffix(".db")
                p.unlink()
                if sibling.is_file():
                    sibling.unlink()
                removed += 1
                if parent != root and parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                continue
        return removed

    def restore_backup(self, backup_path: str) -> dict[str, Any]:
        src = self._resolve_backup(backup_path)
        self.create_backup(reason="pre_restore")
        restored_excel = False
        restored_db = False
        suffix = src.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            dest = self.excel_path()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with self._file_lock():
                shutil.copy2(src, dest)
            restored_excel = True
            db_src = src.with_suffix(".db")
        elif suffix == ".db":
            db_src = src
        else:
            raise ValueError("Backup must be an Excel workbook or a .db snapshot")
        if db_src.is_file():
            database.restore_from(db_src)
            restored_db = True
        self.invalidate()
        return {"excel": restored_excel, "database": restored_db, "path": str(src)}

    def _resolve_backup(self, backup_path: str) -> Path:
        src = Path(backup_path).expanduser().resolve()
        root = self.backup_dir().resolve()
        try:
            inside = src.is_relative_to(root)
        except AttributeError:
            inside = str(src).startswith(str(root))
        if not inside or not src.is_file():
            raise FileNotFoundError("Backup file not found")
        return src

    def records_from_path(self, path: Path) -> list[dict[str, Any]]:
        wb = load_workbook(path, data_only=False, read_only=True)
        try:
            recs: list[dict[str, Any]] = []
            for sheet_name in self.data_sheets(wb):
                _, rows = self._read_sheet_records(wb[sheet_name], sheet_name)
                recs.extend(rows)
            return recs
        finally:
            wb.close()

    def match_record(
        self,
        recs: list[dict[str, Any]],
        record_id: str = "",
        work_order_id: str = "",
        site: str = "",
    ) -> Optional[dict[str, Any]]:
        rid = str(record_id or "").strip()
        if rid:
            hit = next((r for r in recs if str(r.get("record_id") or "") == rid), None)
            if hit:
                return hit
        wo = str(work_order_id or "").strip()
        site_key = str(site or "").strip()
        if wo and site_key:
            hits = [
                r
                for r in recs
                if str(r.get("work_order_id") or "").strip() == wo
                and str(r.get("department") or r.get("_site") or "").strip() == site_key
            ]
            if len(hits) == 1:
                return hits[0]
        if wo:
            hits = [r for r in recs if str(r.get("work_order_id") or "").strip() == wo]
            if len(hits) == 1:
                return hits[0]
        return None

    def preview_restore_row(
        self,
        backup_path: str,
        record_id: str = "",
        work_order_id: str = "",
        site: str = "",
    ) -> dict[str, Any]:
        src = self._resolve_backup(backup_path)
        backup_recs = self.records_from_path(src)
        backup = self.match_record(backup_recs, record_id, work_order_id, site)
        if not backup:
            raise KeyError("That row was not found in the backup workbook.")
        live = self.match_record(
            self.get_all(),
            str(backup.get("record_id") or record_id or ""),
            str(backup.get("work_order_id") or work_order_id or ""),
            str(backup.get("department") or backup.get("_site") or site or ""),
        )
        fields = [k for k in self.cfg().mapping.model_dump().keys() if k != "due_date"]
        diffs = []
        for field in fields:
            current = "" if not live else ("" if live.get(field) is None else str(live.get(field)))
            previous = "" if backup.get(field) is None else str(backup.get(field))
            if current != previous:
                diffs.append({"field": field, "current": current, "backup": previous})
        keys = ["record_id", "work_order_id", "department", "_site", "_sheet", "_row", *fields]
        slim = lambda rec: {k: rec.get(k) for k in keys} if rec else None
        return {
            "backup": slim(backup),
            "current": slim(live),
            "diffs": diffs,
            "matched_live": bool(live),
        }

    def restore_row_from_backup(
        self,
        backup_path: str,
        username: str,
        record_id: str = "",
        work_order_id: str = "",
        site: str = "",
    ) -> dict[str, Any]:
        preview = self.preview_restore_row(backup_path, record_id, work_order_id, site)
        live = preview.get("current")
        if not live:
            raise KeyError("That work order is not in the live workbook, so a single row cannot be restored.")
        changes = {d["field"]: d["backup"] for d in preview.get("diffs") or []}
        if not changes:
            return {"item": self.get_by_id(str(live.get("record_id"))), "unchanged": True, "preview": preview}
        updated = self.update_record(str(live.get("record_id")), changes, username=username, force=True)
        return {"item": updated, "unchanged": False, "preview": preview, "restored_fields": list(changes)}

    def health_scan(self, sample: int = 40) -> dict[str, Any]:
        """Raw sheet scan — includes blank WO IDs that the normal reader skips."""
        from ..domain import is_open

        cfg = self.cfg()
        sample = max(1, min(int(sample or 40), 200))
        formula_headers = self._formula_header_set()
        mapping = cfg.mapping.excel_to_internal()
        missing_id: list[dict[str, Any]] = []
        blank_assign: list[dict[str, Any]] = []
        blank_status: list[dict[str, Any]] = []
        overwritten: list[dict[str, Any]] = []
        missing_formula: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        counts = {
            "missing_id": 0,
            "blank_assign": 0,
            "blank_status": 0,
            "overwritten_formula": 0,
            "missing_formula": 0,
            "duplicate_id": 0,
        }
        seen_ids: dict[tuple[str, str], int] = {}
        scanned = 0
        sheets = 0
        if not self.available():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        wb = self._load_workbook(data_only=False, read_only=True)
        try:
            for sheet_name in self.data_sheets(wb):
                sheets += 1
                ws = wb[sheet_name]
                site = self.site_label(sheet_name)
                header_row = cfg.header_row
                start = cfg.data_start_row
                headers: list[str] = []
                id_header = None
                assign_header = None
                status_header = None
                empty_streak = 0
                max_col = 40
                for idx, row in enumerate(ws.iter_rows(min_row=header_row, max_col=max_col), start=header_row):
                    if idx == header_row:
                        headers = []
                        for col_i, cell in enumerate(row, start=1):
                            headers.append(str(cell.value) if cell.value is not None else f"Column{col_i}")
                        while headers and headers[-1].startswith("Column"):
                            headers.pop()
                        max_col = max(len(headers), 1)
                        for h in headers:
                            field = mapping.get(norm_header(h))
                            if field == "work_order_id":
                                id_header = h
                            elif field == "assigned_to":
                                assign_header = h
                            elif field == "status":
                                status_header = h
                        continue
                    if idx < start:
                        continue
                    raw: dict[str, Any] = {}
                    empty = True
                    for header, cell in zip(headers, row):
                        raw[header] = cell.value
                        if _cell_plain(cell.value) not in (None, ""):
                            empty = False
                    if empty:
                        empty_streak += 1
                        if empty_streak > 80:
                            break
                        continue
                    empty_streak = 0
                    scanned += 1
                    wo_plain = _cell_plain(raw.get(id_header)) if id_header else None
                    wo_text = "" if wo_plain in (None, "") else str(wo_plain).strip()
                    rec_id = f"{site}:{idx}"
                    if not wo_text:
                        counts["missing_id"] += 1
                        if len(missing_id) < sample:
                            missing_id.append({"record_id": rec_id, "sheet": sheet_name, "site": site, "row": idx})
                    else:
                        key = (sheet_name, wo_text)
                        if key in seen_ids:
                            counts["duplicate_id"] += 1
                            if len(duplicates) < sample:
                                duplicates.append(
                                    {
                                        "work_order_id": wo_text,
                                        "sheet": sheet_name,
                                        "site": site,
                                        "rows": [seen_ids[key], idx],
                                    }
                                )
                        else:
                            seen_ids[key] = idx
                        status_plain = _cell_plain(raw.get(status_header)) if status_header else None
                        status_text = "" if status_plain in (None, "") else str(status_plain).strip()
                        if not status_text:
                            counts["blank_status"] += 1
                            if len(blank_status) < sample:
                                blank_status.append(
                                    {
                                        "record_id": rec_id,
                                        "work_order_id": wo_text,
                                        "site": site,
                                        "row": idx,
                                    }
                                )
                        if is_open({"status": status_text}, cfg):
                            assign_plain = _cell_plain(raw.get(assign_header)) if assign_header else None
                            assign_text = "" if assign_plain in (None, "") else str(assign_plain).strip()
                            if not assign_text:
                                counts["blank_assign"] += 1
                                if len(blank_assign) < sample:
                                    blank_assign.append(
                                        {
                                            "record_id": rec_id,
                                            "work_order_id": wo_text,
                                            "site": site,
                                            "row": idx,
                                            "status": status_text,
                                        }
                                    )
                    for header, cell in zip(headers, row):
                        if norm_header(header) not in formula_headers:
                            continue
                        val = cell.value
                        if _is_formula(val):
                            continue
                        plain = _cell_plain(val)
                        item = {
                            "record_id": rec_id,
                            "work_order_id": wo_text,
                            "sheet": sheet_name,
                            "site": site,
                            "row": idx,
                            "column": header,
                        }
                        if plain in (None, ""):
                            counts["missing_formula"] += 1
                            if len(missing_formula) < sample:
                                missing_formula.append(item)
                        else:
                            counts["overwritten_formula"] += 1
                            if len(overwritten) < sample:
                                overwritten.append({**item, "value": str(plain)[:80]})
        finally:
            wb.close()
        return {
            "scanned_rows": scanned,
            "sheets": sheets,
            "sample": sample,
            "counts": counts,
            "issues": {
                "missing_id": missing_id,
                "blank_assign": blank_assign,
                "blank_status": blank_status,
                "overwritten_formula": overwritten,
                "missing_formula": missing_formula,
                "duplicate_id": duplicates,
            },
        }

    def mapping_scan(self) -> dict[str, Any]:
        from difflib import SequenceMatcher

        if not self.available():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        wb = self._load_workbook(data_only=False, read_only=True)
        try:
            headers: list[str] = []
            seen: set[str] = set()
            header_row = self.cfg().header_row
            for sheet_name in self.data_sheets(wb):
                ws = wb[sheet_name]
                raw: list[str] = []
                for row in ws.iter_rows(min_row=header_row, max_row=header_row, max_col=40):
                    for col_i, cell in enumerate(row, start=1):
                        raw.append(str(cell.value) if cell.value is not None else f"Column{col_i}")
                    break
                while raw and raw[-1].startswith("Column"):
                    raw.pop()
                for h in raw:
                    nh = norm_header(h)
                    if not nh or nh in seen:
                        continue
                    seen.add(nh)
                    headers.append(str(h))
        finally:
            wb.close()
        mapping = self.cfg().mapping.model_dump()
        present = {norm_header(h) for h in headers}
        suggestions: dict[str, dict[str, Any]] = {}
        for field, current in mapping.items():
            current_h = str(current or "").strip()
            present_now = bool(current_h) and norm_header(current_h) in present
            best = current_h
            score = 1.0 if present_now else 0.0
            if not present_now:
                needle = (current_h or field.replace("_", " ")).lower()
                for h in headers:
                    s = SequenceMatcher(None, needle, norm_header(h).lower()).ratio()
                    if s > score:
                        score = s
                        best = h
            suggestions[field] = {
                "current": current_h,
                "present": present_now,
                "suggested": best if score >= 0.4 else "",
                "score": round(score, 2),
            }
        return {"headers": headers, "mapping": mapping, "suggestions": suggestions}

    def check_backup(self, backup_path: str) -> dict[str, Any]:
        src = self._resolve_backup(backup_path)
        err = None
        backup_count: Optional[int] = None
        suffix = src.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            try:
                recs = self.records_from_path(src)
                backup_count = len(recs)
            except Exception as exc:
                err = str(exc)
        db_src = src if suffix == ".db" else src.with_suffix(".db")
        has_db = db_src.is_file()
        db_count: Optional[int] = None
        if has_db:
            try:
                db_count = database.snapshot_wo_count(db_src)
            except Exception as exc:
                if err is None:
                    err = str(exc)
        if suffix == ".db":
            backup_count = db_count
        try:
            live_count = len(self.get_all())
        except Exception:
            live_count = database.wo_cache_count()
        compare = db_count if has_db and db_count is not None else backup_count
        healthy = err is None and compare is not None and compare > 0
        if healthy and live_count:
            healthy = compare >= max(1, int(live_count * 0.5))
        return {
            "path": str(src),
            "name": src.name,
            "backup_count": backup_count,
            "live_count": live_count,
            "db_count": db_count,
            "has_db": has_db,
            "delta": None if compare is None else compare - int(live_count or 0),
            "ok": bool(healthy),
            "error": err,
        }

    def _file_lock(self, timeout: float = 90.0):
        return FileLock(str(self.lock_path()), timeout=timeout)

    def _validate_saved(self, path: Path) -> None:
        wb = load_workbook(path, read_only=True, data_only=False)
        try:
            if not wb.sheetnames:
                raise ValueError("Workbook has no worksheets after save")
        finally:
            wb.close()

    def _atomic_replace(self, tmp_path: Path) -> None:
        dest = self.excel_path()
        self._validate_saved(tmp_path)
        os.replace(tmp_path, dest)

    def _formula_header_set(self) -> set[str]:
        return {norm_header(c) for c in self.cfg().formula_columns}

    def _ensure_mapped_headers(self, ws, headers: list[str]) -> list[str]:
        """Append missing mapped columns at the end of the header row. Never insert/shift."""
        mapping = self.cfg().mapping.internal_to_excel()
        existing = {norm_header(h) for h in headers}
        header_row = self.cfg().header_row
        next_col = len(headers) + 1
        new_headers = list(headers)
        for _field, excel_col in mapping.items():
            nh = norm_header(excel_col)
            if not nh or nh in existing:
                continue
            ws.cell(header_row, next_col).value = excel_col
            new_headers.append(excel_col)
            existing.add(nh)
            next_col += 1
        return new_headers

    def _write_record_to_sheet(self, ws, rec: dict[str, Any], headers: list[str], row_number: int) -> None:
        mapping = self.cfg().mapping.internal_to_excel()
        skip = self._formula_header_set()
        skip.add(norm_header(mapping.get("due_date", "")))
        header_index = {norm_header(h): i + 1 for i, h in enumerate(headers)}
        for field, excel_col in mapping.items():
            if not excel_col or field not in rec:
                continue
            nh = norm_header(excel_col)
            if not nh or nh in skip:
                continue
            col_idx = header_index.get(nh)
            if not col_idx:
                continue
            cell = ws.cell(row=row_number, column=col_idx)
            if _is_formula(cell.value):
                continue
            value = rec.get(field)
            if value in ("", None):
                cell.value = None
            else:
                if field.endswith("_date"):
                    dt = parse_date(value)
                    cell.value = dt if dt else value
                else:
                    cell.value = value

    def _copy_row_formulas(self, ws, from_row: int, to_row: int, headers: list[str]) -> None:
        skip = self._formula_header_set()
        for col_idx, header in enumerate(headers, 1):
            if norm_header(header) not in skip:
                continue
            src = ws.cell(from_row, col_idx).value
            dest_coord = f"{get_column_letter(col_idx)}{to_row}"
            if isinstance(src, ArrayFormula):
                text = src.text.replace(str(from_row), str(to_row))
                ws.cell(to_row, col_idx).value = ArrayFormula(ref=dest_coord, text=text)
            elif isinstance(src, str) and src.startswith("="):
                ws.cell(to_row, col_idx).value = src.replace(str(from_row), str(to_row))

    def _next_id(self, records: list[dict[str, Any]], sheet_name: str) -> str:
        label = self.site_label(sheet_name)
        if label == "F5":
            max_n = 0
            for rec in records:
                if rec.get("_sheet") != sheet_name:
                    continue
                wo = str(rec.get("work_order_id") or "")
                m = re.search(r"(\d+)$", wo)
                if m:
                    max_n = max(max_n, int(m.group(1)))
            return f"LKF5-{max_n + 1:04d}"
        year = datetime.now().year
        prefix = f"{self.cfg().id_prefix}-{year}-"
        max_n = 0
        for rec in records:
            wo = str(rec.get("work_order_id") or "")
            if wo.startswith(prefix):
                try:
                    max_n = max(max_n, int(wo.split("-")[-1]))
                except ValueError:
                    continue
        return f"{prefix}{max_n + 1:06d}"

    def _next_row(self, ws, headers: list[str]) -> int:
        mapping = self.cfg().mapping.excel_to_internal()
        id_col = 2
        for i, h in enumerate(headers, 1):
            if mapping.get(norm_header(h)) == "work_order_id":
                id_col = i
                break
        max_row = self.cfg().data_start_row - 1
        start = self.cfg().data_start_row
        empty = 0
        for r in range(start, ws.max_row + 1):
            if ws.cell(r, id_col).value not in (None, ""):
                max_row = r
                empty = 0
            else:
                empty += 1
                if empty > 80:
                    break
        return max_row + 1

    def _locate(self, recs: list[dict[str, Any]], wo_id: str) -> dict[str, Any]:
        wo_id = str(wo_id)
        target = next((r for r in recs if str(r.get("record_id")) == wo_id), None)
        if not target:
            target = next((r for r in recs if str(r.get("work_order_id")) == wo_id), None)
        if not target:
            raise KeyError(f"Work order {wo_id} was not found in Excel")
        return target


    def update_record(
        self,
        wo_id: str,
        changes: dict[str, Any],
        username: str,
        sync_token: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        current = database.get_wo_record(wo_id)
        if not current:
            raise KeyError(f"Work order {wo_id} was not found")
        old = dict(current)
        target = self._merge_mapped(current, changes)
        try:
            saved = database.upsert_wo_record(target)
        except Exception as exc:
            raise ValueError(f"Database save failed: {exc}") from exc
        self._audit_diff(username, str(saved.get("work_order_id") or wo_id), old, saved)
        self.invalidate()
        try:
            self._excel_update_record(wo_id, changes, username, sync_token, force)
        except SyncConflict as exc:
            return self._attach_backup(saved, exc)
        except (ExcelUnavailable, ExcelLocked, PermissionError, Timeout, KeyError, OSError) as exc:
            return self._attach_backup(saved, exc)
        except Exception as exc:
            return self._attach_backup(saved, exc)
        return self._attach_backup(database.get_wo_record(str(saved.get("record_id") or wo_id)) or saved)

    def update_records(
        self,
        ids: list[str],
        changes: dict[str, Any],
        username: str,
        append_remarks: bool = False,
        sync_token: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        ids = [str(i).strip() for i in ids if str(i).strip()]
        if not ids:
            raise ValueError("Select at least one work order.")
        if len(ids) > 80:
            raise ValueError("Bulk update is limited to 80 work orders at a time.")
        remark_text = str(changes.get("remarks") or "").strip() if append_remarks else ""
        field_changes = {k: v for k, v in (changes or {}).items() if not (append_remarks and k == "remarks")}
        items: list[dict[str, Any]] = []
        missing: list[str] = []
        seen: set[str] = set()
        for wo_id in ids:
            current = database.get_wo_record(wo_id)
            if not current:
                missing.append(wo_id)
                continue
            rid = str(current.get("record_id") or wo_id)
            if rid in seen:
                continue
            seen.add(rid)
            old = dict(current)
            target = self._merge_mapped(current, field_changes)
            if append_remarks and remark_text:
                prev = str(target.get("remarks") or "").rstrip()
                target["remarks"] = f"{prev}\n{remark_text}".strip() if prev else remark_text
            saved = database.upsert_wo_record(target)
            self._audit_diff(username, str(saved.get("work_order_id") or rid), old, saved)
            items.append(saved)
        if not items:
            raise ValueError("None of the selected work orders were found.")
        self.invalidate()
        excel_error = None
        try:
            self._excel_update_records(ids, changes, username, append_remarks, sync_token, force)
        except SyncConflict as exc:
            excel_error = str(exc)
        except (ExcelUnavailable, ExcelLocked, PermissionError, Timeout, KeyError, OSError, ValueError) as exc:
            excel_error = str(exc)
        except Exception as exc:
            excel_error = str(exc)
        out_items = [self._attach_backup(it, excel_error) for it in items]
        return {
            "items": out_items,
            "updated": len(out_items),
            "missing": missing,
            "excel_backup_ok": excel_error is None,
            "excel_backup_error": excel_error,
        }

    def create_record(self, data: dict[str, Any], username: str) -> dict[str, Any]:
        try:
            created = self._excel_create_record(data, username)
            saved = database.upsert_wo_record(created)
            database.add_audit(username, "create", work_order_id=str(saved.get("work_order_id") or ""), details="Created material request")
            self.invalidate()
            return self._attach_backup(saved)
        except (ExcelUnavailable, ExcelLocked, PermissionError, Timeout, OSError, Exception) as exc:
            if isinstance(exc, (KeyError, ValueError)) and "Database save failed" in str(exc):
                raise
            recs = database.load_wo_cache()
            site = str(data.get("department") or data.get("_site") or data.get("_sheet") or "")
            sheet_name = site or ((self.cfg().worksheets or ["sheet"])[0])
            wo_id = str(data.get("work_order_id") or "").strip() or self._next_id(recs, sheet_name)
            rec: dict[str, Any] = {k: "" for k in self.cfg().mapping.model_dump().keys()}
            rec.update({k: v for k, v in data.items() if not str(k).startswith("_")})
            rec["work_order_id"] = wo_id
            rec["created_date"] = rec.get("created_date") or datetime.now().strftime("%Y-%m-%d %H:%M")
            rec["status"] = rec.get("status") or "OPEN"
            rec["department"] = rec.get("department") or site
            rec["_site"] = rec.get("department")
            rec["_sheet"] = sheet_name
            rec["record_id"] = str(data.get("record_id") or f"DB:{wo_id}")
            existing = {str(r.get("record_id")) for r in recs}
            if rec["record_id"] in existing:
                rec["record_id"] = f"DB:{wo_id}:{uuid.uuid4().hex[:8]}"
            self._apply_due_date(rec)
            saved = database.upsert_wo_record(rec)
            database.add_audit(username, "create", work_order_id=wo_id, details="Created material request (database only)")
            self.invalidate()
            return self._attach_backup(saved, exc)

    def delete_record(self, wo_id: str, username: str) -> dict[str, Any]:
        rec = database.get_wo_record(wo_id)
        if not rec:
            raise KeyError(f"Work order {wo_id} was not found")
        database.delete_wo_record(wo_id)
        database.add_audit(username, "delete", work_order_id=str(rec.get("work_order_id") or wo_id), details="Deleted material request")
        self.invalidate()
        excel_error = None
        try:
            self._excel_delete_record(wo_id, username)
        except (ExcelUnavailable, ExcelLocked, PermissionError, Timeout, KeyError, OSError) as exc:
            excel_error = str(exc)
        except Exception as exc:
            excel_error = str(exc)
        return {
            "deleted": True,
            "id": wo_id,
            "record_id": rec.get("record_id"),
            "excel_backup_ok": excel_error is None,
            "excel_backup_error": excel_error,
        }

    def _excel_update_record(
        self,
        wo_id: str,
        changes: dict[str, Any],
        username: str,
        sync_token: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        if not self.available():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        try:
            lock = self._file_lock()
            lock.acquire()
        except Timeout as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        try:
            current_token = self.fingerprint()
            if sync_token and not force and sync_token != current_token:
                current = self.get_by_id(wo_id)
                raise SyncConflict(
                    "The Excel workbook has changed since you last loaded it. Review the latest data before saving.",
                    current=current,
                )
            self.create_backup(reason="update")
            wb = self._load_workbook()
            try:
                all_records: list[dict[str, Any]] = []
                sheet_headers: dict[str, list[str]] = {}
                for sheet_name in self.data_sheets(wb):
                    hdrs, recs = self._read_sheet_records(wb[sheet_name], sheet_name)
                    sheet_headers[sheet_name] = hdrs
                    all_records.extend(recs)
                target = self._locate(all_records, wo_id)
                old = dict(target)
                allowed = set(self.cfg().mapping.model_dump().keys())
                for k, v in changes.items():
                    if k.startswith("_") or k in {"record_id", "department"}:
                        continue
                    if k in allowed:
                        target[k] = v if v is not None else ""
                ws = wb[target["_sheet"]]
                headers = self._ensure_mapped_headers(ws, sheet_headers[target["_sheet"]])
                sheet_headers[target["_sheet"]] = headers
                self._write_record_to_sheet(ws, target, headers, int(target["_row"]))
                tmp = _temp_xlsx(self.excel_path().parent)
                wb.save(tmp)
            finally:
                wb.close()
            try:
                self._atomic_replace(tmp)
            except Exception:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                raise
            self.invalidate()
            rid = old.get("record_id")
            updated = self.get_by_id(rid) or self.get_by_id(wo_id)
            assert updated is not None
            self._audit_diff(username, str(updated.get("work_order_id") or wo_id), old, updated)
            database.set_sync_meta("last_write", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            database.set_sync_meta("last_write_user", username)
            return updated
        except PermissionError as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        finally:
            try:
                lock.release()
            except Exception:
                pass

    def _excel_update_records(
        self,
        ids: list[str],
        changes: dict[str, Any],
        username: str,
        append_remarks: bool = False,
        sync_token: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Apply the same Excel field changes to many rows under one lock/backup/save."""
        ids = [str(i).strip() for i in ids if str(i).strip()]
        if not ids:
            raise ValueError("Select at least one work order.")
        if len(ids) > 80:
            raise ValueError("Bulk update is limited to 80 work orders at a time.")
        if not self.available():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        try:
            lock = self._file_lock()
            lock.acquire()
        except Timeout as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        try:
            current_token = self.fingerprint()
            if sync_token and not force and sync_token != current_token:
                raise SyncConflict(
                    "The Excel workbook has changed since you last loaded it. Review the latest data before saving."
                )
            self.create_backup(reason="bulk")
            wb = self._load_workbook()
            try:
                all_records: list[dict[str, Any]] = []
                sheet_headers: dict[str, list[str]] = {}
                for sheet_name in self.data_sheets(wb):
                    hdrs, recs = self._read_sheet_records(wb[sheet_name], sheet_name)
                    sheet_headers[sheet_name] = hdrs
                    all_records.extend(recs)
                allowed = set(self.cfg().mapping.model_dump().keys())
                remark_text = str(changes.get("remarks") or "").strip() if append_remarks else ""
                field_changes = {k: v for k, v in (changes or {}).items() if not (append_remarks and k == "remarks")}
                pending: list[tuple[dict[str, Any], dict[str, Any]]] = []
                missing: list[str] = []
                seen: set[str] = set()
                for wo_id in ids:
                    try:
                        target = self._locate(all_records, wo_id)
                    except KeyError:
                        missing.append(wo_id)
                        continue
                    rid = str(target.get("record_id") or wo_id)
                    if rid in seen:
                        continue
                    seen.add(rid)
                    old = dict(target)
                    for k, v in field_changes.items():
                        if k.startswith("_") or k in {"record_id", "department"}:
                            continue
                        if k in allowed:
                            target[k] = v if v is not None else ""
                    if append_remarks and remark_text:
                        prev = str(target.get("remarks") or "").rstrip()
                        target["remarks"] = f"{prev}\n{remark_text}".strip() if prev else remark_text
                    ws = wb[target["_sheet"]]
                    headers = self._ensure_mapped_headers(ws, sheet_headers[target["_sheet"]])
                    sheet_headers[target["_sheet"]] = headers
                    self._write_record_to_sheet(ws, target, headers, int(target["_row"]))
                    pending.append((old, rid))
                if not pending:
                    raise ValueError("None of the selected work orders were found in Excel.")
                tmp = _temp_xlsx(self.excel_path().parent)
                wb.save(tmp)
            finally:
                wb.close()
            try:
                self._atomic_replace(tmp)
            except Exception:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                raise
            self.invalidate()
            items: list[dict[str, Any]] = []
            for old, rid in pending:
                rec = self.get_by_id(rid)
                if not rec:
                    continue
                self._audit_diff(username, str(rec.get("work_order_id") or rid), old, rec)
                items.append(rec)
            database.set_sync_meta("last_write", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            database.set_sync_meta("last_write_user", username)
            return {"items": items, "updated": len(items), "missing": missing}
        except PermissionError as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        finally:
            try:
                lock.release()
            except Exception:
                pass

    def _excel_create_record(self, data: dict[str, Any], username: str) -> dict[str, Any]:
        if not self.available():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        try:
            lock = self._file_lock()
            lock.acquire()
        except Timeout as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        try:
            self.create_backup(reason="create")
            wb = self._load_workbook()
            try:
                site = str(data.get("department") or data.get("_site") or data.get("_sheet") or "")
                sheet_name = resolve_data_sheet(site, self.data_sheets(wb), self.cfg().worksheet_labels)
                ws = wb[sheet_name]
                headers, sheet_recs = self._read_sheet_records(ws, sheet_name)
                all_records = list(sheet_recs)
                wo_id = str(data.get("work_order_id") or "").strip()
                if not wo_id:
                    wo_id = self._next_id(all_records, sheet_name)
                rec: dict[str, Any] = {k: "" for k in self.cfg().mapping.model_dump().keys()}
                rec.update({k: v for k, v in data.items() if not k.startswith("_")})
                rec["work_order_id"] = wo_id
                rec["created_date"] = rec.get("created_date") or datetime.now().strftime("%Y-%m-%d %H:%M")
                rec["status"] = rec.get("status") or "OPEN"
                rec["_raw"] = {}
                headers = self._ensure_mapped_headers(ws, headers)
                row_number = self._next_row(ws, headers)
                rec["_row"] = row_number
                rec["_sheet"] = sheet_name
                template_row = max(self.cfg().data_start_row, row_number - 1)
                self._copy_row_formulas(ws, template_row, row_number, headers)
                self._write_record_to_sheet(ws, rec, headers, row_number)
                tmp = _temp_xlsx(self.excel_path().parent)
                wb.save(tmp)
            finally:
                wb.close()
            try:
                self._atomic_replace(tmp)
            except Exception:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                raise
            self.invalidate()
            rec["record_id"] = self.record_id(sheet_name, row_number)
            rec["_site"] = self.site_label(sheet_name)
            rec["department"] = rec.get("department") or rec["_site"]
            rec["_row"] = row_number
            rec["_sheet"] = sheet_name
            self._apply_due_date(rec)
            database.upsert_wo_record(rec)
            created = database.get_wo_record(rec["record_id"]) or rec
            database.set_sync_meta("last_write", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return created
        except PermissionError as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        finally:
            try:
                lock.release()
            except Exception:
                pass

    def _excel_delete_record(self, wo_id: str, username: str) -> None:
        if not self.available():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        try:
            lock = self._file_lock()
            lock.acquire()
        except Timeout as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        try:
            self.create_backup(reason="delete")
            wb = self._load_workbook()
            try:
                all_records = []
                for sheet_name in self.data_sheets(wb):
                    _, recs = self._read_sheet_records(wb[sheet_name], sheet_name)
                    all_records.extend(recs)
                target = self._locate(all_records, wo_id)
                ws = wb[target["_sheet"]]
                ws.delete_rows(int(target["_row"]), 1)
                tmp = _temp_xlsx(self.excel_path().parent)
                wb.save(tmp)
            finally:
                wb.close()
            try:
                self._atomic_replace(tmp)
            except Exception:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                raise
            self.invalidate()
            database.add_audit(username, "delete", work_order_id=str(wo_id), details="Deleted material request")
            database.set_sync_meta("last_write", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except PermissionError as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        finally:
            try:
                lock.release()
            except Exception:
                pass

    def import_rows(self, rows: list[dict[str, Any]], username: str) -> dict[str, Any]:
        """Append or update Excel rows from a mapped import, then copy those rows into the database."""
        if not self.available():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        cleaned: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            item = {k: v for k, v in raw.items() if v not in (None, "")}
            if item.get("work_order_id") or item.get("description") or item.get("remarks"):
                cleaned.append(item)
        if not cleaned:
            return {"created": 0, "updated": 0, "skipped": 0, "total": 0, "errors": ["No usable rows in the import file."]}
        try:
            lock = self._file_lock()
            lock.acquire()
        except Timeout as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        created = 0
        updated = 0
        skipped = 0
        errors: list[str] = []
        try:
            self.create_backup(reason="import")
            wb = self._load_workbook()
            try:
                sheet_headers: dict[str, list[str]] = {}
                all_records: list[dict[str, Any]] = []
                for sheet_name in self.data_sheets(wb):
                    hdrs, recs = self._read_sheet_records(wb[sheet_name], sheet_name)
                    sheet_headers[sheet_name] = hdrs
                    all_records.extend(recs)
                by_rid = {str(r.get("record_id")): r for r in all_records}
                by_wo_site: dict[tuple[str, str], list[dict[str, Any]]] = {}
                by_wo: dict[str, list[dict[str, Any]]] = {}
                for rec in all_records:
                    wo = str(rec.get("work_order_id") or "").strip()
                    site = str(rec.get("department") or rec.get("_site") or "")
                    if wo:
                        by_wo_site.setdefault((wo, site), []).append(rec)
                        by_wo.setdefault(wo, []).append(rec)
                labels = self.cfg().worksheet_labels
                allowed = set(self.cfg().mapping.model_dump().keys())
                for idx, data in enumerate(cleaned, start=1):
                    try:
                        target = None
                        rid = str(data.get("record_id") or "").strip()
                        wo_id = str(data.get("work_order_id") or "").strip()
                        site = str(data.get("department") or data.get("_site") or "").strip()
                        if rid and rid in by_rid:
                            target = by_rid[rid]
                        elif wo_id and site and len(by_wo_site.get((wo_id, site), [])) == 1:
                            target = by_wo_site[(wo_id, site)][0]
                        elif wo_id and len(by_wo.get(wo_id, [])) == 1:
                            target = by_wo[wo_id][0]
                        if target:
                            for k, v in data.items():
                                if k.startswith("_") or k in {"record_id", "department"}:
                                    continue
                                if k in allowed:
                                    target[k] = v if v is not None else ""
                            ws = wb[target["_sheet"]]
                            headers = self._ensure_mapped_headers(ws, sheet_headers[target["_sheet"]])
                            sheet_headers[target["_sheet"]] = headers
                            self._write_record_to_sheet(ws, target, headers, int(target["_row"]))
                            updated += 1
                            continue
                        sheet_name = resolve_data_sheet(site, list(sheet_headers.keys()) or self.data_sheets(wb), labels)
                        ws = wb[sheet_name]
                        headers = self._ensure_mapped_headers(ws, sheet_headers.get(sheet_name) or [])
                        sheet_headers[sheet_name] = headers
                        rec = {k: "" for k in self.cfg().mapping.model_dump().keys()}
                        rec.update({k: v for k, v in data.items() if not str(k).startswith("_")})
                        if not str(rec.get("work_order_id") or "").strip():
                            rec["work_order_id"] = self._next_id(all_records, sheet_name)
                        rec["created_date"] = rec.get("created_date") or datetime.now().strftime("%Y-%m-%d %H:%M")
                        rec["status"] = rec.get("status") or "OPEN"
                        row_number = self._next_row(ws, headers)
                        rec["_row"] = row_number
                        rec["_sheet"] = sheet_name
                        rec["_site"] = self.site_label(sheet_name)
                        rec["record_id"] = self.record_id(sheet_name, row_number)
                        rec["department"] = rec.get("department") or rec["_site"]
                        template_row = max(self.cfg().data_start_row, row_number - 1)
                        self._copy_row_formulas(ws, template_row, row_number, headers)
                        self._write_record_to_sheet(ws, rec, headers, row_number)
                        all_records.append(rec)
                        by_rid[rec["record_id"]] = rec
                        wo = str(rec.get("work_order_id") or "")
                        if wo:
                            by_wo.setdefault(wo, []).append(rec)
                            by_wo_site.setdefault((wo, rec["department"]), []).append(rec)
                        created += 1
                    except Exception as exc:
                        skipped += 1
                        errors.append(f"Row {idx}: {exc}")
                        if len(errors) >= 25:
                            errors.append("Further row errors omitted.")
                            break
                tmp = _temp_xlsx(self.excel_path().parent)
                wb.save(tmp)
            finally:
                wb.close()
            try:
                self._atomic_replace(tmp)
            except Exception:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                raise
            self.invalidate()
            seeded = self.seed_from_excel(username=username)
            records = list(self._cache or [])
            if not seeded.get("ok") and not records:
                raise ExcelUnavailable(seeded.get("error") or "Import saved Excel but the database could not be updated.")
            database.add_audit(
                username,
                "import",
                details=f"Imported {created} new and {updated} updated material requests",
            )
            database.set_sync_meta("last_write", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            database.set_sync_meta("last_write_user", username)
            return {
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "total": len(records),
                "errors": errors,
            }
        except PermissionError as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        finally:
            try:
                lock.release()
            except Exception:
                pass

    def _audit_diff(self, username: str, wo_id: str, old: dict, new: dict) -> None:
        fields = self.cfg().mapping.model_dump().keys()
        for field in fields:
            if field in {"last_updated", "due_date"}:
                continue
            ov = "" if old.get(field) is None else str(old.get(field))
            nv = "" if new.get(field) is None else str(new.get(field))
            if ov != nv:
                database.add_audit(
                    username,
                    "update",
                    work_order_id=wo_id,
                    field=field,
                    old_value=ov,
                    new_value=nv,
                )

    def replace_from_bytes(self, content: bytes, username: str, filename: str = "upload.xlsx") -> dict[str, Any]:
        if not content or len(content) < 100:
            raise ValueError("The uploaded file is empty or too small to be an Excel workbook.")
        dest = self.excel_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = _temp_xlsx(dest.parent)
        tmp.write_bytes(content)
        try:
            self._validate_saved(tmp)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise ValueError(f"That file could not be opened as Excel: {exc}") from exc
        try:
            lock = self._file_lock()
            lock.acquire()
        except Timeout as exc:
            tmp.unlink(missing_ok=True)
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        try:
            if dest.exists():
                self.create_backup(reason="upload")
            os.replace(tmp, dest)
            self.invalidate()
            seeded = self.seed_from_excel(username=username, replace_lines=True)
            records = list(self._cache or [])
            if not seeded.get("ok"):
                raise ExcelUnavailable(seeded.get("error") or "Uploaded workbook could not be seeded.")
            database.add_audit(username, "upload", details=f"Uploaded workbook {filename} ({len(records)} rows)")
            database.set_sync_meta("last_write", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            database.set_sync_meta("last_write_user", username)
            return self.status()
        except PermissionError as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        finally:
            try:
                lock.release()
            except Exception:
                pass
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def ping(self) -> dict[str, Any]:
        """Cheap live check against the database. Excel mtime does not overwrite records."""
        recs = self._cache
        if recs is None:
            recs = database.load_wo_cache()
            if recs:
                self._cache = recs
        count = len(recs or [])
        file_token = self.fingerprint()
        excel_ok = self.available()
        return {
            "available": bool(count) or excel_ok,
            "source": "database",
            "mtime": self.mtime_iso(),
            "sync_token": self.sync_token(),
            "file_token": file_token,
            "record_count": count,
            "stale": False,
            "synchronized": bool(count),
            "excel_backup": excel_ok,
            "error": None if count else (self._last_error or "No work orders in the database yet."),
            "warning": None if excel_ok or not count else "Excel backup file is currently unavailable.",
        }

    def status(self) -> dict[str, Any]:
        available = self.available()
        err = None
        try:
            records = self.load()
        except ExcelUnavailable as e:
            records = list(self._cache or database.load_wo_cache() or [])
            err = str(e)
        except ExcelLocked as e:
            records = list(self._cache or database.load_wo_cache() or [])
            err = str(e)
        live = self.ping()
        return {
            "available": bool(records) or available,
            "source": "database",
            "path": str(self.excel_path()),
            "worksheet": ", ".join(self.cfg().worksheets or [self.cfg().worksheet_name]),
            "mtime": self.mtime_iso(),
            "sync_token": live.get("sync_token") or self.sync_token(),
            "record_count": len(records),
            "last_read": database.get_sync_meta("last_read"),
            "last_write": database.get_sync_meta("last_write"),
            "last_write_user": database.get_sync_meta("last_write_user"),
            "last_backup": database.get_sync_meta("last_backup"),
            "last_seed": database.get_sync_meta("last_seed"),
            "synchronized": bool(records),
            "excel_backup": available,
            "stale": False,
            "error": None if records else err,
            "warning": None if available else (err or live.get("warning")),
            "headers": self._headers if (available or self._headers) else [],
        }

    def reconcile_overlay(self, username: str = "sync") -> dict[str, Any]:
        """Keep Excel and SQLite delay/supplier data in both directions.

        - Append Delay Type / Source / Justification headers if missing (no column shift).
        - Newly added empty columns are filled from SQLite (migration of overlay notes).
        - Once columns exist, Excel is source of truth including blanks.
        - Supplier names from Excel are added to the SQLite catalog.
        """
        if not self.available():
            raise ExcelUnavailable("Excel file is currently unavailable.")
        try:
            lock = self._file_lock()
            lock.acquire()
        except Timeout as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        wrote = False
        pushed_excel = 0
        pulled_db = 0
        suppliers_added = 0
        new_columns = False
        try:
            extras = database.get_all_record_extras()
            original_delay = {
                rid: {f: str(ex.get(f) or "") for f in DELAY_FIELDS} for rid, ex in extras.items()
            }
            known_suppliers = {s["name"].lower() for s in database.list_suppliers()}
            wb = self._load_workbook()
            try:
                sheet_headers: dict[str, list[str]] = {}
                all_records: list[dict[str, Any]] = []
                for sheet_name in self.data_sheets(wb):
                    ws = wb[sheet_name]
                    hdrs, recs = self._read_sheet_records(ws, sheet_name)
                    new_hdrs = self._ensure_mapped_headers(ws, hdrs)
                    if new_hdrs != hdrs:
                        wrote = True
                        new_columns = True
                    sheet_headers[sheet_name] = new_hdrs
                    all_records.extend(recs)
                dirty_ids: set[str] = set()
                for rec in all_records:
                    rid = str(rec.get("record_id") or "")
                    extra = extras.get(rid) or {}
                    for field in DELAY_FIELDS:
                        excel_val = str(rec.get(field) or "").strip()
                        db_val = str(extra.get(field) or "").strip()
                        if new_columns and not excel_val and db_val:
                            rec[field] = db_val
                            extra[field] = db_val
                            extras[rid] = extra
                            dirty_ids.add(rid)
                            pushed_excel += 1
                        else:
                            rec[field] = excel_val
                            if excel_val != db_val:
                                extra[field] = excel_val
                                extras[rid] = extra
                                pulled_db += 1
                    name = str(rec.get("supplier") or "").strip()
                    if name and name.lower() not in known_suppliers:
                        database.add_supplier(name, created_by=username)
                        known_suppliers.add(name.lower())
                        suppliers_added += 1
                if dirty_ids:
                    wrote = True
                    by_sheet: dict[str, list[dict[str, Any]]] = {}
                    for rec in all_records:
                        if str(rec.get("record_id") or "") in dirty_ids:
                            by_sheet.setdefault(rec["_sheet"], []).append(rec)
                    for sheet_name, recs in by_sheet.items():
                        ws = wb[sheet_name]
                        headers = sheet_headers[sheet_name]
                        for rec in recs:
                            self._write_record_to_sheet(ws, rec, headers, int(rec["_row"]))
                if wrote:
                    self.create_backup(reason="reconcile")
                    tmp = _temp_xlsx(self.excel_path().parent)
                    wb.save(tmp)
                else:
                    tmp = None
            finally:
                wb.close()
            if wrote and tmp is not None:
                try:
                    self._atomic_replace(tmp)
                except Exception:
                    if tmp.exists():
                        tmp.unlink(missing_ok=True)
                    raise
            self.invalidate()
            records = self.read_workbook()
            for rec in records:
                rid = str(rec.get("record_id") or "")
                extra = extras.get(rid) or {}
                payload = {f: str(rec.get(f) or "") for f in DELAY_FIELDS}
                previous = original_delay.get(rid) or {f: "" for f in DELAY_FIELDS}
                wo = str(rec.get("work_order_id") or extra.get("work_order_id") or "")
                if payload != previous:
                    database.upsert_record_extra(
                        rid,
                        username,
                        work_order_id=wo,
                        delay_kind=payload["delay_kind"],
                        delay_source=payload["delay_source"],
                        delay_justification=payload["delay_justification"],
                    )
                db_rec = database.get_wo_record(rid)
                if db_rec:
                    changed = False
                    for field in DELAY_FIELDS:
                        val = str(rec.get(field) or "")
                        if str(db_rec.get(field) or "") != val:
                            db_rec[field] = val
                            changed = True
                    if changed:
                        database.upsert_wo_record(db_rec)
            database.set_sync_meta("last_reconcile", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return {
                "wrote_excel": wrote,
                "pushed_to_excel": pushed_excel,
                "pulled_to_db": pulled_db,
                "suppliers_added": suppliers_added,
                "record_count": len(records),
            }
        except PermissionError as exc:
            raise ExcelLocked(
                "Excel file is currently being used by another process. Changes cannot be saved until the file becomes available."
            ) from exc
        finally:
            try:
                lock.release()
            except Exception:
                pass


excel_service = ExcelService()
