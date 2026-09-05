from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import database
from ..security import require_permission
from .auth import public_user

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=4)
    full_name: str = ""
    email: str = ""
    role: str = "user"


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@router.get("")
def list_users(user=Depends(require_permission("users"))):
    return {"items": [public_user(u) | {"is_active": bool(u["is_active"])} for u in database.list_users()]}


@router.post("")
def create_user(body: UserCreate, user=Depends(require_permission("users"))):
    if database.get_user_by_username(body.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    if body.role not in {"admin", "manager", "user"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    created = database.create_user(body.username, body.full_name, body.email, body.password, body.role)
    database.add_audit(user["username"], "user_create", details=f"Created user {body.username}")
    return {"item": public_user(created)}


@router.put("/{user_id}")
def update_user(user_id: int, body: UserUpdate, user=Depends(require_permission("users"))):
    existing = database.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    payload = body.model_dump(exclude_unset=True)
    if payload.get("is_active") is not None:
        payload["is_active"] = 1 if payload["is_active"] else 0
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
    database.delete_user(user_id)
    database.add_audit(user["username"], "user_delete", details=f"Deleted user {existing['username']}")
    return {"deleted": True}
