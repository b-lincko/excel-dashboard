"""In-memory background jobs so Excel upload / restore cannot freeze login."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Optional

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_TTL_SEC = 30 * 60


def _now() -> float:
    return time.time()


def _prune_locked() -> None:
    cutoff = _now() - _TTL_SEC
    dead = [jid for jid, job in _JOBS.items() if float(job.get("updated") or 0) < cutoff]
    for jid in dead:
        _JOBS.pop(jid, None)


def create_job(kind: str, username: str) -> str:
    jid = uuid.uuid4().hex[:16]
    job = {
        "id": jid,
        "kind": kind,
        "status": "queued",
        "phase": "upload",
        "progress": 0,
        "message": "Queued…",
        "error": None,
        "result": None,
        "username": username,
        "created": _now(),
        "updated": _now(),
    }
    with _LOCK:
        _prune_locked()
        _JOBS[jid] = job
    return jid


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def update_job(job_id: str, **fields: Any) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        for key, value in fields.items():
            if key in {"id", "created", "username", "kind"}:
                continue
            job[key] = value
        job["updated"] = _now()


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job.get("id"),
        "kind": job.get("kind"),
        "status": job.get("status"),
        "phase": job.get("phase"),
        "progress": int(job.get("progress") or 0),
        "message": job.get("message") or "",
        "error": job.get("error"),
        "result": job.get("result"),
    }


def run_job(job_id: str, fn: Callable[[Callable[..., None]], Any]) -> None:
    def report(progress: int, message: str, phase: Optional[str] = None) -> None:
        payload: dict[str, Any] = {
            "status": "running",
            "progress": max(0, min(100, int(progress))),
            "message": message,
        }
        if phase:
            payload["phase"] = phase
        update_job(job_id, **payload)

    def worker() -> None:
        update_job(job_id, status="running", phase="apply", progress=5, message="Starting…")
        try:
            result = fn(report)
            update_job(
                job_id,
                status="done",
                phase="done",
                progress=100,
                message="Applied",
                error=None,
                result=result,
            )
        except Exception as exc:
            update_job(
                job_id,
                status="error",
                phase="error",
                message=str(exc),
                error=str(exc),
            )

    threading.Thread(target=worker, name=f"woms-job-{job_id}", daemon=True).start()
