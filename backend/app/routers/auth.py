from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import database
from ..security import create_token, get_current_user, verify_password

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


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "role": user["role"],
        "is_active": bool(user.get("is_active")),
    }
