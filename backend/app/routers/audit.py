from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from .. import database
from ..security import require_permission

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(
    work_order_id: Optional[str] = None,
    username: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user=Depends(require_permission("audit")),
):
    items, total = database.list_audit(work_order_id=work_order_id, username=username, limit=limit, offset=offset)
    return {"items": items, "total": total}
