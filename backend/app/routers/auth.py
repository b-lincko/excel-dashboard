from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import database
from ..security import (
    GUEST_PAGES,
    VALID_ROLES,
    create_token,
    editable_fields,
    get_current_user,
    parse_extra_permissions,
    require_permission,
    user_permissions,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest):
    user = database.get_user_by_username(body.username.strip())
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account is disabled")
    token = create_token(user)
    database.touch_login(user["id"])
    user = database.get_user_by_id(user["id"]) or user
    database.add_audit(user["username"], "login", details="User signed in")
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": public_user(user),
    }


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.post("/password")
def change_password(body: PasswordChange, user=Depends(get_current_user)):
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")
    database.update_user(user["id"], password=body.new_password)
    database.add_audit(user["username"], "password_change", details="User changed password")
    return {"ok": True}


@router.post("/logout")
def logout(user=Depends(get_current_user)):
    database.add_audit(user["username"], "logout", details="User signed out")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return public_user(user)


class LayoutBody(BaseModel):
    widgets: list[dict[str, Any]]


@router.get("/layout")
def get_layout(user=Depends(require_permission("view"))):
    raw = database.get_setting(f"dashboard_layout:{user['username']}")
    if not raw:
        return {"widgets": None}
    try:
        return {"widgets": json.loads(raw)}
    except json.JSONDecodeError:
        return {"widgets": None}


@router.put("/layout")
def save_layout(body: LayoutBody, user=Depends(require_permission("view"))):
    database.set_setting(f"dashboard_layout:{user['username']}", json.dumps(body.widgets))
    return {"ok": True, "widgets": body.widgets}


def public_user(user: dict) -> dict:
    extra = parse_extra_permissions(user)
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "role": user["role"],
        "is_active": bool(user.get("is_active")),
        "last_login": user.get("last_login"),
        "created_at": user.get("created_at"),
        "permissions": user_permissions(user),
        "extra_permissions": extra,
        "guest_pages": GUEST_PAGES,
        "roles": sorted(VALID_ROLES),
        "editable_fields": editable_fields(user),
    }
