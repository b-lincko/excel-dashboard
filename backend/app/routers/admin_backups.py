from __future__ import annotations

"""Admin API for the dual backup system (local + SMB).

POST /api/admin/backups        - run a dual backup now (backup permission)
GET  /api/admin/backups/status - last result + history + configuration
                                   (never includes SMB credentials)
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .. import database
from ..dual_backup import DualConfig, read_status_history, run_dual_backup
from ..security import require_permission

router = APIRouter(prefix="/api/admin", tags=["dual-backup"])


@router.post("/backups")
def run_backup(user=Depends(require_permission("backup"))):
    cfg = DualConfig()
    if not cfg.enabled:
        raise HTTPException(status_code=409, detail="Dual backup is disabled (BACKUP_ENABLED=false).")
    status = run_dual_backup(reason="manual")
    if status is None:
        raise HTTPException(status_code=409, detail="Dual backup is disabled.")
    def _dest_word(d: dict[str, Any]) -> str:
        if d["status"] == "SUCCESS" and d.get("verification") == "PASSED":
            return "verified"
        if d["status"] == "SKIPPED":
            return "skipped"
        return "failed"

    payload = {
        "status": "success" if status["overall"] == "SUCCESS"
        else "partial_success" if status["overall"] == "PARTIAL_SUCCESS"
        else "failed",
        "backup_id": status.get("backup_id"),
        "local_backup": _dest_word(status["local"]),
        "smb_backup": _dest_word(status["smb"]),
        "duration_s": status.get("duration_s"),
        "size_bytes": status["local"].get("size"),
    }
    if payload["status"] == "failed":
        payload["detail"] = status.get("error") or status["smb"].get("reason") or "see the backup log"
    return payload


@router.get("/backups/status")
def backup_status(user=Depends(require_permission("backup"))):
    cfg = DualConfig()
    history = read_status_history(limit=15)
    summary = []
    for h in history:
        summary.append(
            {
                "backup_id": h.get("backup_id"),
                "started": h.get("started"),
                "finished": h.get("finished"),
                "duration_s": h.get("duration_s"),
                "local": h.get("local", {}).get("status"),
                "local_verification": h.get("local", {}).get("verification"),
                "smb": h.get("smb", {}).get("status"),
                "smb_verification": h.get("smb", {}).get("verification"),
                "smb_reason": h.get("smb", {}).get("reason") or "",
                "smb_mount_warning": h.get("smb", {}).get("mount_warning") or "",
                "smb_fallback": h.get("smb", {}).get("fallback") or "",
                "overall": h.get("overall"),
                "size": h.get("local", {}).get("size") or 0,
                "encrypted": bool(h.get("encrypted")),
                "reason": h.get("reason"),
            }
        )
    return {
        "config": cfg.describe(),
        "last": summary[0] if summary else None,
        "last_sync_meta": database.get_sync_meta("last_dual_backup"),
        "history": summary,
    }
