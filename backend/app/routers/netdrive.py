from __future__ import annotations

"""Network drive (added 2026-09-12): a shared file area users can browse,
upload to, view in the browser and download from.

Root directory comes from the NETDRIVE_PATH environment variable (default
data/netdrive). Point it at a mounted company/SMB share to serve that drive;
the app only ever reads/writes INSIDE the configured root - path traversal is
blocked by resolution + containment checks.

- read  (list / download / preview) needs the "view" permission
- write (upload / mkdir / delete)   needs "edit" OR "create"
- previews reuse the attachment extraction (PDF text+tables, Excel/CSV rows,
  DOCX text, images with OCR when tesseract exists) and are cached per
  path+mtime+size in-process.
"""

import os
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..extract import extract_attachment
from ..security import require_any_permission, require_permission
from ..config import ROOT

router = APIRouter(prefix="/api/netdrive", tags=["netdrive"])

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB per file
PREVIEW_MAX_BYTES = 15 * 1024 * 1024  # extraction cost bound
BLOCKED_EXT = {".exe", ".bat", ".cmd", ".com", ".msi", ".dll", ".scr", ".ps1"}
_cache: dict[str, tuple[float, int, dict[str, Any]]] = {}
_CACHE_CAP = 64


def _backup_zones() -> list[Path]:
    """Folders that Files-page users must NEVER be able to reach."""
    from ..config import ROOT

    zones: list[Path] = []
    for raw in (
        os.environ.get("SMB_MOUNT_PATH", ""),
        os.environ.get("LOCAL_BACKUP_PATH", ""),
        str(ROOT / "backups"),
        str(ROOT / "backup"),
    ):
        raw = str(raw or "").strip()
        if not raw:
            continue
        try:
            zones.append(Path(raw).expanduser().resolve())
        except OSError:
            continue
    return zones


def _guard_not_backup(root: Path) -> None:
    """The Files share and the backup share use DIFFERENT accounts and folders.

    If NETDRIVE_PATH points at (or contains, or sits inside) a backup
    destination, users could browse or delete backups through the web app -
    forbidden by the backup security model. Fail closed with a clear message.
    """
    from ..config import ROOT

    for zone in _backup_zones():
        if root == zone or zone in root.parents or root in zone.parents:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"NETDRIVE_PATH ({root}) overlaps a backup destination ({zone}). "
                    "Files-page users must not be able to reach backups. Use a separate "
                    "folder/share with a separate service account (docs/files-drive.md)."
                ),
            )


def drive_root() -> Path:
    from ..config import ROOT

    raw = str(os.environ.get("NETDRIVE_PATH") or "").strip() or str(ROOT / "data" / "netdrive")
    root = Path(raw).expanduser()
    try:
        root = root.resolve()
    except OSError:
        pass
    root.mkdir(parents=True, exist_ok=True)
    _guard_not_backup(root)
    return root


def _safe_path(rel: str) -> Path:
    root = drive_root()
    rel = str(rel or "").strip().replace("\\", "/").lstrip("/")
    if rel in {"", "."}:
        return root
    target = (root / rel).resolve() if Path(rel).is_absolute() is False else Path(rel).resolve()
    # absolute paths are never allowed; containment is the real gate
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path is outside the file area.")
    return target


def _rel_to_root(p: Path) -> str:
    return str(p.relative_to(drive_root())).replace(os.sep, "/")


def _kind(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if ext in {".xlsx", ".xlsm", ".csv"}:
        return "sheet"
    if ext == ".docx":
        return "doc"
    if ext == ".txt":
        return "text"
    return "file"


@router.get("")
def listing(dir: str = "", user=Depends(require_permission("view"))):
    base = _safe_path(dir)
    if not base.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found.")
    items = []
    try:
        entries = sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not read the folder: {exc}")
    for p in entries:
        try:
            st = p.stat()
        except OSError:
            continue
        item: dict[str, Any] = {
            "name": p.name,
            "dir": p.is_dir(),
            "size": 0 if p.is_dir() else st.st_size,
            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
            "kind": "" if p.is_dir() else _kind(p.name),
        }
        items.append(item)
    return {
        "dir": _rel_to_root(base) if base != drive_root() else "",
        "root_name": drive_root().name,
        "items": items,
    }


@router.post("/mkdir")
def make_dir(body: dict[str, Any], user=Depends(require_any_permission("edit", "create"))):
    target = _safe_path(str(body.get("path") or ""))
    if target.exists():
        raise HTTPException(status_code=409, detail="That folder already exists.")
    try:
        target.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not create the folder: {exc}")
    return {"created": _rel_to_root(target)}


@router.post("/upload")
async def upload(
    dir: str = Form(""),
    file: UploadFile = File(...),
    user=Depends(require_any_permission("edit", "create")),
):
    base = _safe_path(str(dir or ""))
    if not base.is_dir():
        raise HTTPException(status_code=404, detail="Target folder not found.")
    name = Path(file.filename or "file").name
    ext = Path(name).suffix.lower()
    if ext in BLOCKED_EXT:
        raise HTTPException(status_code=400, detail=f"Files of type {ext} are not allowed here.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Files up to 100 MB are supported.")
    dest = base / name
    n = 1
    stem, suffix = Path(name).stem, Path(name).suffix
    while dest.exists():  # never overwrite: auto-rename like a drive would
        dest = base / f"{stem} ({n}){suffix}"
        n += 1
    try:
        dest.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not save the file: {exc}")
    return {"item": {"name": dest.name, "dir": False, "size": len(content), "kind": _kind(dest.name), "path": _rel_to_root(dest)}}


@router.get("/download")
def download(path: str = "", user=Depends(require_permission("view"))):
    p = _safe_path(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(p, filename=p.name, media_type="application/octet-stream")


@router.get("/preview")
def preview(path: str = "", user=Depends(require_permission("view"))):
    p = _safe_path(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        st = p.stat()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    key = f"{p}|{st.st_mtime_ns}|{st.st_size}"
    hit = _cache.get(key)
    if hit is not None:
        extract = hit[2]
    else:
        if st.st_size > PREVIEW_MAX_BYTES:
            extract = {
                "ok": False,
                "kind": _kind(p.name),
                "engine": "",
                "pages": 0,
                "words": 0,
                "text": "",
                "tables": [],
                "sheets": [],
                "message": "File is larger than 15 MB - download it instead (preview text extraction is limited to 15 MB).",
            }
        else:
            try:
                extract = extract_attachment(p.name, p.read_bytes())
            except Exception as exc:
                extract = {"ok": False, "kind": _kind(p.name), "engine": "", "pages": 0, "words": 0, "text": "", "tables": [], "sheets": [], "message": f"Preview failed: {exc}"}
        if len(_cache) >= _CACHE_CAP:
            _cache.clear()
        _cache[key] = (st.st_mtime, st.st_size, extract)
    return {
        "item": {"filename": p.name, "mime": "", "kind": _kind(p.name), "size": st.st_size, "path": _rel_to_root(p)},
        "extract": extract,
    }


@router.delete("")
def delete_path(path: str = "", user=Depends(require_any_permission("edit", "create"))):
    p = _safe_path(path)
    if p == drive_root():
        raise HTTPException(status_code=400, detail="The drive root cannot be deleted.")
    if p.is_file():
        try:
            p.unlink()
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not delete the file: {exc}")
        return {"deleted": _rel_to_root(p)}
    if p.is_dir():
        try:
            if any(p.iterdir()):
                raise HTTPException(status_code=400, detail="Folder is not empty.")
            p.rmdir()
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not delete the folder: {exc}")
        return {"deleted": _rel_to_root(p)}
    raise HTTPException(status_code=404, detail="Not found.")
