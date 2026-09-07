from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import database
from ..excel.service import ExcelLocked, ExcelUnavailable, SyncConflict, excel_service
from ..materials import (
    canonical_supplier,
    clean_name,
    cluster_duplicates,
    load_alias_map,
    search_material,
    search_supplier,
    suggest_suppliers,
)
from ..security import require_permission

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

DELAY_KINDS = ["placement", "delivery"]
DELAY_SOURCES = ["site", "procurement", "supplier"]


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = None
    email: Optional[str] = None
    contact: Optional[str] = None
    lead_time_days: Optional[int] = None
    notes: Optional[str] = None
    items: list[str] = Field(default_factory=list)


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact: Optional[str] = None
    lead_time_days: Optional[int] = None
    notes: Optional[str] = None
    items: Optional[list[str]] = None


class SupplierItemBody(BaseModel):
    material: str = Field(min_length=1, max_length=400)
    notes: str = ""


class MergeBody(BaseModel):
    canonical: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    write_excel: bool = False


def _excel_suppliers() -> list[str]:
    try:
        return excel_service.unique_values("supplier")
    except (ExcelUnavailable, ExcelLocked):
        return []


def _excel_records() -> list[dict[str, Any]]:
    try:
        return excel_service.get_all()
    except (ExcelUnavailable, ExcelLocked):
        return []


def _raise_excel(exc: Exception) -> None:
    if isinstance(exc, ExcelUnavailable):
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ExcelLocked):
        raise HTTPException(status_code=423, detail=str(exc))
    if isinstance(exc, SyncConflict):
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "conflict": True, "current": getattr(exc, "current", None)},
        )
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _with_items(item: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not item:
        return item
    out = dict(item)
    out["items"] = database.list_supplier_items(str(item.get("name") or ""))
    return out


@router.get("/suppliers")
def list_suppliers(user=Depends(require_permission("view"))):
    catalog = [_with_items(s) for s in database.list_suppliers()]
    names = {str(s["name"]).strip() for s in catalog if s and str(s.get("name") or "").strip()}
    names.update(_excel_suppliers())
    alias_map = load_alias_map()
    canonicals = sorted({canonical_supplier(n, alias_map) for n in names if n}, key=str.lower)
    return {
        "items": catalog,
        "names": sorted(names, key=str.lower),
        "canonical_names": canonicals,
        "aliases": database.list_supplier_aliases(),
        "delay_kinds": DELAY_KINDS,
        "delay_sources": DELAY_SOURCES,
    }


@router.post("/suppliers")
def create_supplier(body: SupplierCreate, user=Depends(require_permission("edit"))):
    try:
        item = database.add_supplier(body.name, created_by=user["username"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = body.model_dump(exclude_unset=True)
    extras = {k: v for k, v in payload.items() if k not in {"name", "items"} and v is not None}
    if extras:
        item = database.update_supplier(int(item["id"]), **extras) or item
    materials = [clean_name(x) for x in (body.items or []) if clean_name(x)]
    if materials:
        database.replace_supplier_items(item["name"], materials, created_by=user["username"])
    database.add_audit(user["username"], "supplier_create", details=f"Added supplier {item['name']}")
    return {"item": _with_items(item)}


@router.put("/suppliers/{supplier_id}")
def save_supplier(supplier_id: int, body: SupplierUpdate, user=Depends(require_permission("edit"))):
    current = database.get_supplier(supplier_id)
    if not current:
        raise HTTPException(status_code=404, detail="Supplier not found")
    payload = body.model_dump(exclude_unset=True)
    items = payload.pop("items", None)
    try:
        item = database.update_supplier(supplier_id, **payload) if payload else current
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = str((item or current).get("name") or "")
    if items is not None:
        database.replace_supplier_items(name, [clean_name(x) for x in items], created_by=user["username"])
    database.add_audit(user["username"], "supplier_update", details=f"Updated supplier {name}")
    return {"item": _with_items(item or current)}


@router.post("/suppliers/{supplier_id}/items")
def add_item(supplier_id: int, body: SupplierItemBody, user=Depends(require_permission("edit"))):
    current = database.get_supplier(supplier_id)
    if not current:
        raise HTTPException(status_code=404, detail="Supplier not found")
    item = database.add_supplier_item(
        current["name"], body.material, notes=body.notes, created_by=user["username"]
    )
    return {"item": item, "supplier": _with_items(current)}


@router.get("/materials")
def materials_directory(
    q: str = "",
    by: str = Query("material"),
    limit: int = Query(40, ge=1, le=100),
    user=Depends(require_permission("view")),
):
    records = _excel_records()
    mode = (by or "material").strip().lower()
    if mode in {"supplier", "suppliers"}:
        return search_supplier(q, records, limit=limit)
    return search_material(q, records, limit=limit)


@router.get("/suggest")
def supplier_suggest(
    q: str = "",
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require_permission("view")),
):
    if not clean_name(q):
        return {"query": "", "total": 0, "items": [], "mode": "suggest"}
    return suggest_suppliers(q, _excel_records(), limit=limit)


@router.get("/duplicates")
def supplier_duplicates(user=Depends(require_permission("view"))):
    records = _excel_records()
    counts: dict[str, int] = {}
    names: list[str] = []
    for rec in records:
        name = clean_name(rec.get("supplier"))
        if not name:
            continue
        counts[name] = counts.get(name, 0) + 1
        names.append(name)
    for row in database.list_suppliers():
        name = clean_name(row.get("name"))
        if name:
            names.append(name)
            counts.setdefault(name, 0)
    clusters = cluster_duplicates(names, counts)
    return {
        "total": len(clusters),
        "aliases": database.list_supplier_aliases(),
        "items": clusters,
        "note": "Excel still has the original spellings until you confirm a merge.",
    }


@router.post("/suppliers/merge")
def merge_suppliers(body: MergeBody, user=Depends(require_permission("edit"))):
    canonical = clean_name(body.canonical)
    aliases = []
    seen = {canonical.lower()}
    for raw in body.aliases or []:
        name = clean_name(raw)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        aliases.append(name)
    if not aliases:
        raise HTTPException(status_code=400, detail="Pick at least one duplicate spelling to merge.")
    for alias in aliases:
        database.upsert_supplier_alias(alias, canonical, created_by=user["username"])
        existing = database.get_supplier_by_name(alias)
        if existing and existing["name"].lower() != canonical.lower():
            for item in database.list_supplier_items(existing["name"]):
                database.add_supplier_item(
                    canonical,
                    item.get("material") or "",
                    notes=item.get("notes") or "",
                    created_by=user["username"],
                )
            database.replace_supplier_items(existing["name"], [], created_by=user["username"])
            if not database.get_supplier_by_name(canonical):
                database.update_supplier(int(existing["id"]), name=canonical)
        database.rename_supplier_refs(alias, canonical)
        if not database.get_supplier_by_name(canonical):
            database.add_supplier(canonical, created_by=user["username"])
    excel_updated = 0
    missing: list[str] = []
    if body.write_excel:
        records = _excel_records()
        wanted = {a.lower() for a in aliases}
        ids = [
            str(rec.get("record_id") or "")
            for rec in records
            if clean_name(rec.get("supplier")).lower() in wanted
        ]
        ids = [i for i in ids if i]
        for start in range(0, len(ids), 80):
            chunk = ids[start : start + 80]
            try:
                result = excel_service.update_records(
                    chunk,
                    {"supplier": canonical},
                    username=user["username"],
                    force=True,
                )
            except (ExcelUnavailable, ExcelLocked, SyncConflict, KeyError, ValueError) as exc:
                _raise_excel(exc)
            excel_updated += int(result.get("updated") or 0)
            missing.extend(result.get("missing") or [])
    database.add_audit(
        user["username"],
        "supplier_merge",
        details=f"Merged {len(aliases)} spellings into {canonical}"
        + (" and wrote Excel" if body.write_excel else " (aliases only)"),
    )
    return {
        "canonical": canonical,
        "aliases": aliases,
        "wrote_excel": bool(body.write_excel),
        "excel_updated": excel_updated,
        "missing": missing,
        "aliases_saved": database.list_supplier_aliases(),
    }


