from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

from . import database

_WLL_FIX = (
    ("WL.L", "WLL"),
    ("W.L.L.", "WLL"),
    ("W.L.L", "WLL"),
    ("L.L.C.", "LLC"),
    ("L.L.C", "LLC"),
)
_LEGAL = re.compile(r"\b(WLL|LLC|CO|LTD|INC|COMPANY|EST|ESTABLISHMENT)\b")
_TOKEN = re.compile(r"[A-Za-z0-9]{3,}")


def clean_name(name: Any) -> str:
    return " ".join(str(name or "").split())


def norm_supplier_key(name: Any) -> str:
    s = clean_name(name).upper()
    for src, dest in _WLL_FIX:
        s = s.replace(src, dest)
    s = re.sub(r"[^A-Z0-9&]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def core_supplier_key(name: Any) -> str:
    s = _LEGAL.sub(" ", norm_supplier_key(name))
    return re.sub(r"\s+", " ", s).strip()


def compact_supplier_key(name: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", core_supplier_key(name))


def looks_combined(name: Any) -> bool:
    text = str(name or "")
    if text.count(" & ") >= 2:
        return True
    if "," in text and " & " in text:
        return True
    if "\n" in text:
        return True
    if re.search(r"\b1[\.\)]\s+\S.+\b2[\.\)]\s+", text):
        return True
    if re.search(r"^\s*\d+[\.\)]\s+", text) and re.search(r"\s+\d+[\.\)]\s+", text):
        return True
    return False


def unique_supplier_names(names: Iterable[str], alias_map: Optional[dict[str, str]] = None) -> list[str]:
    """One dropdown entry per supplier. Drops numbered/combined Excel cells and W.L.L vs WLL twins."""
    amap = alias_map if alias_map is not None else load_alias_map()
    best: dict[str, str] = {}
    for raw in names:
        cleaned = clean_name(raw)
        if not cleaned or looks_combined(cleaned):
            continue
        canon = canonical_supplier(cleaned, amap)
        key = compact_supplier_key(canon) or compact_supplier_key(cleaned)
        if not key:
            continue
        prev = best.get(key)
        if not prev or len(canon) < len(prev):
            best[key] = canon
    return sorted(best.values(), key=str.lower)


def existing_supplier_match(name: Any) -> Optional[dict[str, Any]]:
    cleaned = clean_name(name)
    if not cleaned:
        return None
    hit = database.get_supplier_by_name(cleaned)
    if hit:
        return hit
    key = compact_supplier_key(cleaned)
    if not key:
        return None
    for row in database.list_suppliers():
        if compact_supplier_key(row.get("name")) == key:
            return row
    return None


def supplier_similarity(a: Any, b: Any) -> float:
    ca, cb = compact_supplier_key(a), compact_supplier_key(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    ka, kb = core_supplier_key(a), core_supplier_key(b)
    if ka and ka == kb:
        return 1.0
    na, nb = norm_supplier_key(a), norm_supplier_key(b)
    if na and na == nb:
        return 1.0
    return max(
        SequenceMatcher(None, ca, cb).ratio(),
        SequenceMatcher(None, ka, kb).ratio() if ka and kb else 0.0,
    )


def load_alias_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for row in database.list_supplier_aliases():
        alias = clean_name(row.get("alias"))
        canon = clean_name(row.get("canonical"))
        if not alias or not canon:
            continue
        out[alias.lower()] = canon
        key = norm_supplier_key(alias).lower()
        if key:
            out[key] = canon
    return out


def canonical_supplier(name: Any, alias_map: Optional[dict[str, str]] = None) -> str:
    cleaned = clean_name(name)
    if not cleaned:
        return ""
    amap = alias_map if alias_map is not None else load_alias_map()
    hit = amap.get(cleaned.lower()) or amap.get(norm_supplier_key(cleaned).lower())
    return hit or cleaned


def normalize_lines(raw: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return items
    for row in raw:
        if not isinstance(row, dict):
            continue
        supplier = clean_name(row.get("supplier"))
        material = clean_name(row.get("material"))
        if not supplier and not material:
            continue
        items.append(
            {
                "supplier": supplier,
                "material": material,
                "qty": clean_name(row.get("qty")),
                "unit": clean_name(row.get("unit")),
                "notes": clean_name(row.get("notes")),
                "needed_date": clean_name(row.get("needed_date"))[:10],
            }
        )
    return items


def apply_lines_to_excel_fields(excel_data: dict[str, Any], lines: list[dict[str, str]]) -> None:
    """Fill blank Excel supplier/description from structured lines. Never invent extra columns."""
    if not lines:
        return
    suppliers: list[str] = []
    materials: list[str] = []
    for line in lines:
        supplier = clean_name(line.get("supplier"))
        material = clean_name(line.get("material"))
        if supplier and supplier not in suppliers:
            suppliers.append(supplier)
        if material and material not in materials:
            materials.append(material)
    if suppliers and not clean_name(excel_data.get("supplier")):
        excel_data["supplier"] = suppliers[0]
    if materials and not clean_name(excel_data.get("description")):
        excel_data["description"] = "; ".join(materials)


def material_matches(query: str, text: Any) -> bool:
    q = clean_name(query).lower()
    t = str(text or "").lower()
    if not q or not t:
        return False
    if q in t:
        return True
    tokens = _TOKEN.findall(q)
    if not tokens:
        return False
    return all(tok in t for tok in tokens)


def _excel_history(records: Iterable[dict[str, Any]], alias_map: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in records:
        supplier = clean_name(rec.get("supplier"))
        material = clean_name(rec.get("description"))
        if not supplier and not material:
            continue
        out.append(
            {
                "supplier": supplier,
                "canonical": canonical_supplier(supplier, alias_map) if supplier else "",
                "material": material,
                "source": "excel",
                "record_id": str(rec.get("record_id") or ""),
                "work_order_id": str(rec.get("work_order_id") or ""),
                "site": str(rec.get("department") or rec.get("_site") or ""),
            }
        )
    return out


def _line_history(alias_map: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in database.list_all_mr_lines():
        supplier = clean_name(row.get("supplier"))
        material = clean_name(row.get("material"))
        if not supplier and not material:
            continue
        out.append(
            {
                "supplier": supplier,
                "canonical": canonical_supplier(supplier, alias_map) if supplier else "",
                "material": material,
                "source": "line",
                "record_id": str(row.get("record_id") or ""),
                "work_order_id": str(row.get("work_order_id") or ""),
                "site": "",
                "qty": row.get("qty") or "",
                "unit": row.get("unit") or "",
            }
        )
    return out


def _catalog_history(alias_map: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in database.list_supplier_items():
        supplier = clean_name(row.get("supplier_name"))
        material = clean_name(row.get("material"))
        if not supplier or not material:
            continue
        out.append(
            {
                "supplier": supplier,
                "canonical": canonical_supplier(supplier, alias_map),
                "material": material,
                "source": "catalog",
                "record_id": "",
                "work_order_id": "",
                "site": "",
                "notes": row.get("notes") or "",
            }
        )
    return out


def history_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    alias_map = load_alias_map()
    return [
        *_excel_history(records, alias_map),
        *_line_history(alias_map),
        *_catalog_history(alias_map),
    ]


def search_material(query: str, records: Iterable[dict[str, Any]], limit: int = 40) -> dict[str, Any]:
    q = clean_name(query)
    rows = [r for r in history_rows(records) if material_matches(q, r.get("material"))]
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = (row.get("canonical") or row.get("supplier") or "").lower()
        if not key:
            continue
        bucket = grouped.setdefault(
            key,
            {
                "supplier": row.get("canonical") or row.get("supplier"),
                "aliases": set(),
                "materials": [],
                "sources": set(),
                "work_orders": set(),
                "count": 0,
            },
        )
        if row.get("supplier"):
            bucket["aliases"].add(row["supplier"])
        material = clean_name(row.get("material"))
        if material and material not in bucket["materials"]:
            bucket["materials"].append(material)
        bucket["sources"].add(row.get("source") or "")
        if row.get("work_order_id"):
            bucket["work_orders"].add(row["work_order_id"])
        bucket["count"] += 1
    items = []
    for bucket in grouped.values():
        items.append(
            {
                "supplier": bucket["supplier"],
                "aliases": sorted(a for a in bucket["aliases"] if a and a != bucket["supplier"]),
                "materials": bucket["materials"][:12],
                "sources": sorted(s for s in bucket["sources"] if s),
                "work_order_count": len(bucket["work_orders"]),
                "hit_count": bucket["count"],
            }
        )
    items.sort(key=lambda x: (-x["hit_count"], -x["work_order_count"], str(x["supplier"]).lower()))
    return {"query": q, "total": len(items), "items": items[: max(1, min(int(limit or 40), 100))]}


def search_supplier(query: str, records: Iterable[dict[str, Any]], limit: int = 40) -> dict[str, Any]:
    q = clean_name(query)
    q_key = compact_supplier_key(q)
    rows = []
    for row in history_rows(records):
        supplier = row.get("canonical") or row.get("supplier") or ""
        hay = f"{supplier} {row.get('supplier') or ''}"
        if q.lower() in hay.lower() or (q_key and q_key in compact_supplier_key(supplier)):
            rows.append(row)
            continue
        if material_matches(q, supplier):
            rows.append(row)
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = (row.get("canonical") or row.get("supplier") or "").lower()
        if not key:
            continue
        bucket = grouped.setdefault(
            key,
            {
                "supplier": row.get("canonical") or row.get("supplier"),
                "aliases": set(),
                "materials": [],
                "sources": set(),
                "work_orders": set(),
                "count": 0,
            },
        )
        if row.get("supplier"):
            bucket["aliases"].add(row["supplier"])
        material = clean_name(row.get("material"))
        if material and material not in bucket["materials"]:
            bucket["materials"].append(material)
        bucket["sources"].add(row.get("source") or "")
        if row.get("work_order_id"):
            bucket["work_orders"].add(row["work_order_id"])
        bucket["count"] += 1
    items = []
    for bucket in grouped.values():
        items.append(
            {
                "supplier": bucket["supplier"],
                "aliases": sorted(a for a in bucket["aliases"] if a and a != bucket["supplier"]),
                "materials": bucket["materials"][:40],
                "sources": sorted(s for s in bucket["sources"] if s),
                "work_order_count": len(bucket["work_orders"]),
                "hit_count": bucket["count"],
            }
        )
    items.sort(key=lambda x: (-x["hit_count"], str(x["supplier"]).lower()))
    return {"query": q, "total": len(items), "items": items[: max(1, min(int(limit or 40), 100))]}


def suggest_suppliers(query: str, records: Iterable[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    result = search_material(query, records, limit=limit)
    result["mode"] = "suggest"
    return result


def cluster_duplicates(
    names: Iterable[str],
    counts: Optional[dict[str, int]] = None,
    threshold: float = 0.9,
) -> list[dict[str, Any]]:
    counts = counts or {}
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        cleaned = clean_name(name)
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        unique.append(cleaned)
    used: set[str] = set()
    ranked = sorted(unique, key=lambda n: (-int(counts.get(n) or 0), n.lower()))
    clusters: list[dict[str, Any]] = []
    for name in ranked:
        if name in used or looks_combined(name):
            continue
        group = [name]
        used.add(name)
        for other in unique:
            if other in used or looks_combined(other):
                continue
            if supplier_similarity(name, other) >= threshold:
                group.append(other)
                used.add(other)
        if len(group) < 2:
            continue
        canonical = max(group, key=lambda n: (int(counts.get(n) or 0), -len(n)))
        aliases = [n for n in group if n != canonical]
        clusters.append(
            {
                "canonical": canonical,
                "aliases": aliases,
                "names": group,
                "counts": {n: int(counts.get(n) or 0) for n in group},
                "total": sum(int(counts.get(n) or 0) for n in group),
            }
        )
    clusters.sort(key=lambda c: (-c["total"], -len(c["names"])))
    return clusters


def persist_work_order_lines(
    record_id: str,
    work_order_id: str,
    lines: list[dict[str, Any]],
    username: str,
) -> list[dict[str, str]]:
    cleaned = normalize_lines(lines)
    for line in cleaned:
        supplier = line.get("supplier")
        if supplier and not looks_combined(supplier):
            match = existing_supplier_match(supplier)
            if match:
                line["supplier"] = match["name"]
            else:
                database.add_supplier(supplier, created_by=username)
    database.replace_mr_lines(record_id, cleaned, created_by=username, work_order_id=work_order_id)
    for line in cleaned:
        if line.get("supplier") and line.get("material"):
            database.add_supplier_item(line["supplier"], line["material"], created_by=username)
    return cleaned


def merge_choices(existing: Iterable[str], extras: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in list(existing or []) + list(extras or []):
        text = clean_name(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out
