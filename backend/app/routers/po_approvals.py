from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from .. import approvals
from ..security import require_permission

router = APIRouter(prefix="/api/po-approvals", tags=["po-approvals"])


@router.get("")
def list_po_inbox(
    q: Optional[str] = Query(None),
    user=Depends(require_permission("view")),
):
    return approvals.inbox(user, q=str(q or "").strip())
