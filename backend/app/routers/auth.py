from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import database
from ..security import create_token, get_current_user, require_permission, verify_password

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
    database.add_audit(user["username"], "login", details="User signed in")
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": public_user(user),
    }


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
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "role": user["role"],
        "is_active": bool(user.get("is_active")),
    }
