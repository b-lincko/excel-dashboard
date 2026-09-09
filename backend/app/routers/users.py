from __future__ import annotations

import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import database, mailer
from ..config import load_config
from ..security import ADMIN_ONLY_PERMS, ALL_PERMS, GUEST_PAGES, GRANTABLE_PERMS, VALID_ROLES, require_permission
from .auth import public_user

router = APIRouter(prefix="/api/users", tags=["users"])

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,40}$")
ROLE_ORDER = ["admin", "manager", "user", "readonly", "guest"]


def _permissions_json(role: str, extra: Optional[list[str]]) -> str:
    if role == "admin":
        return "[]"
    allowed = set(GRANTABLE_PERMS)
    values: list[str] = []
    seen: set[str] = set()
    for item in extra or []:
        key = str(item or "").strip()
        if key in ADMIN_ONLY_PERMS or key not in allowed or key in seen:
            continue
        if role == "guest" and key not in GUEST_PAGES and key != "view":
            continue
        seen.add(key)
        values.append(key)
    return json.dumps(values)


def _clean_username(raw: str) -> str:
    name = str(raw or "").strip()
    if not USERNAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3–40 characters: letters, numbers, dot, underscore or hyphen.",
        )
    return name


def _active_admins(except_id: Optional[int] = None) -> int:
    n = 0
    for item in database.list_users():
        if except_id is not None and item.get("id") == except_id:
            continue
        if item.get("role") == "admin" and item.get("is_active"):
            n += 1
    return n


def _guard_last_admin(existing: dict, payload: dict) -> None:
    still_admin = payload.get("role", existing.get("role")) == "admin"
    still_active = existing.get("is_active")
    if "is_active" in payload:
        still_active = bool(payload.get("is_active"))
    if existing.get("role") == "admin" and existing.get("is_active") and (not still_admin or not still_active):
        if _active_admins(except_id=existing.get("id")) < 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last active administrator.")


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    full_name: str = ""
    email: str = ""
    role: str = "user"
    extra_permissions: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)
    extra_permissions: Optional[list[str]] = None


@router.get("/access-catalog")
def access_catalog(user=Depends(require_permission("users"))):
    cfg = load_config()
    return {
        "roles": [r for r in ROLE_ORDER if r in VALID_ROLES],
        "actions": [p for p in ALL_PERMS if p not in GUEST_PAGES and p not in ADMIN_ONLY_PERMS],
        "admin_only": sorted(ADMIN_ONLY_PERMS),
        "pages": list(GUEST_PAGES),
        "role_defaults": cfg.permissions,
    }


@router.get("")
def list_users(user=Depends(require_permission("users"))):
    return {"items": [public_user(u) | {"is_active": bool(u["is_active"])} for u in database.list_users()]}


@router.get("/{user_id}")
def get_user(user_id: int, user=Depends(require_permission("users"))):
    existing = database.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    return {"item": public_user(existing)}


@router.post("")
def create_user(body: UserCreate, request: Request, user=Depends(require_permission("users"))):
    username = _clean_username(body.username)
    if database.get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username already exists")
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    created = database.create_user(
        username,
        " ".join(body.full_name.split()),
        body.email.strip(),
        body.password,
        body.role,
        extra_permissions=_permissions_json(body.role, body.extra_permissions),
    )
    database.add_audit(user["username"], "user_create", details=f"Created user {username}")
    email_send = mailer.send_verification(created, request) if created.get("email") else None
    return {"item": public_user(created), "email_send": email_send}


@router.put("/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, user=Depends(require_permission("users"))):
    existing = database.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    payload = body.model_dump(exclude_unset=True)
    if payload.get("is_active") is not None:
        payload["is_active"] = 1 if payload["is_active"] else 0
    if payload.get("role") and payload["role"] not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if "full_name" in payload:
        payload["full_name"] = " ".join(str(payload.get("full_name") or "").split())
    if "email" in payload:
        payload["email"] = str(payload.get("email") or "").strip()
        if payload["email"].lower() != str(existing.get("email") or "").strip().lower():
            payload["email_verified"] = 0
    _guard_last_admin(existing, payload)
    role = payload.get("role") or existing["role"]
    if "extra_permissions" in payload:
        payload["extra_permissions"] = _permissions_json(role, payload.get("extra_permissions") or [])
    elif payload.get("role") and payload["role"] != existing.get("role"):
        if payload["role"] == "admin":
            payload["extra_permissions"] = "[]"
        elif payload["role"] == "guest":
            payload["extra_permissions"] = _permissions_json("guest", [])
        else:
            payload["extra_permissions"] = _permissions_json(payload["role"], [])
    updated = database.update_user(user_id, **payload)
    database.add_audit(user["username"], "user_update", details=f"Updated user {existing['username']}")
    return {"item": public_user(updated)}


@router.delete("/{user_id}")
def delete_user(user_id: int, user=Depends(require_permission("users"))):
    existing = database.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    if existing["username"] == user["username"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if existing.get("role") == "admin" and existing.get("is_active") and _active_admins(except_id=user_id) < 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last active administrator.")
    database.delete_user(user_id)
    database.add_audit(user["username"], "user_delete", details=f"Deleted user {existing['username']}")
    return {"deleted": True, "id": user_id}
