from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import database
from ..excel.service import ExcelLocked, ExcelUnavailable, excel_service
from ..security import require_permission

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

DELAY_KINDS = ["placement", "delivery"]
DELAY_SOURCES = ["site", "procurement", "supplier"]


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def _excel_suppliers() -> list[str]:
    try:
        return excel_service.unique_values("supplier")
    except (ExcelUnavailable, ExcelLocked):
        return []


@router.get("/suppliers")
def list_suppliers(user=Depends(require_permission("view"))):
    catalog = database.list_suppliers()
    names = {str(s["name"]).strip() for s in catalog if str(s.get("name") or "").strip()}
    names.update(_excel_suppliers())
    return {
        "items": catalog,
        "names": sorted(names, key=str.lower),
        "delay_kinds": DELAY_KINDS,
        "delay_sources": DELAY_SOURCES,
    }


@router.post("/suppliers")
def create_supplier(body: SupplierCreate, user=Depends(require_permission("edit"))):
    try:
        item = database.add_supplier(body.name, created_by=user["username"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    database.add_audit(user["username"], "supplier_create", details=f"Added supplier {item['name']}")
    return {"item": item}
