from __future__ import annotations

import json
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import database, mailer
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

_LOGIN_FAILS: dict[str, list[float]] = {}
_LOGIN_WINDOW_SEC = 600
_LOGIN_MAX_FAILS = 8


def _login_key(username: str, request: Request) -> str:
    host = request.client.host if request.client else "?"
    return f"{host}|{(username or '').strip().lower()}"


def _login_locked(key: str) -> bool:
    now = time.time()
    stamps = [t for t in _LOGIN_FAILS.get(key, []) if now - t < _LOGIN_WINDOW_SEC]
    if stamps:
        _LOGIN_FAILS[key] = stamps
    else:
        _LOGIN_FAILS.pop(key, None)
    return len(stamps) >= _LOGIN_MAX_FAILS


def _record_login_fail(key: str) -> None:
    _LOGIN_FAILS.setdefault(key, []).append(time.time())


def _clear_login_fails(key: str) -> None:
    _LOGIN_FAILS.pop(key, None)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, request: Request):
    key = _login_key(body.username, request)
    if _login_locked(key):
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-ins. Try again in a few minutes.",
        )
    user = database.get_user_by_username(body.username.strip())
    if not user or not verify_password(body.password, user["password_hash"]):
        _record_login_fail(key)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account is disabled")
    _clear_login_fails(key)
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
    fresh = database.get_user_by_id(user["id"]) or user
    token = create_token(fresh)
    return {"ok": True, "access_token": token, "token_type": "bearer", "user": public_user(fresh)}


@router.post("/logout")
def logout(user=Depends(get_current_user)):
    database.revoke_token(str(user.get("_jti") or ""), user.get("username") or "", int(user.get("_token_exp") or 0))
    database.add_audit(user["username"], "logout", details="User signed out")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return public_user(user)


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None


@router.put("/profile")
def update_profile(body: ProfileUpdate, request: Request, user=Depends(get_current_user)):
    payload = body.model_dump(exclude_unset=True)
    if "full_name" in payload:
        payload["full_name"] = " ".join(str(payload.get("full_name") or "").split())
    email_changed = False
    if "email" in payload:
        payload["email"] = str(payload.get("email") or "").strip()
        email_changed = payload["email"].lower() != str(user.get("email") or "").strip().lower()
        if email_changed:
            payload["email_verified"] = 0
    updated = database.update_user(user["id"], **payload)
    database.add_audit(user["username"], "profile_update", details="Updated name or email")
    out = public_user(updated or user)
    if email_changed and payload.get("email"):
        out["email_send"] = mailer.send_verification(updated or user, request)
    return out


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


class ForgotBody(BaseModel):
    username: str = ""
    email: str = ""


class TokenBody(BaseModel):
    token: str


class ResetBody(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


_FORGOT: dict[str, list[float]] = {}


def _forgot_locked(request: Request) -> bool:
    host = request.client.host if request.client else "?"
    now = time.time()
    stamps = [t for t in _FORGOT.get(host, []) if now - t < 600]
    _FORGOT[host] = stamps
    return len(stamps) >= 8


@router.post("/forgot")
def forgot_password(body: ForgotBody, request: Request):
    if _forgot_locked(request):
        raise HTTPException(status_code=429, detail="Too many reset requests. Try again in a few minutes.")
    host = request.client.host if request.client else "?"
    _FORGOT.setdefault(host, []).append(time.time())
    ident = str(body.username or body.email or "").strip()
    user = database.get_user_by_username(ident) if ident else None
    if not user and ident:
        user = database.get_user_by_email(ident)
    if user and user.get("is_active"):
        mailer.send_reset(user, request)
    return {"ok": True, "message": "If that account has a real email and mail is on, we sent a reset link."}


@router.post("/reset-password")
def reset_password(body: ResetBody):
    try:
        item = database.consume_email_token(body.token, "reset")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user = database.get_user_by_username(str(item.get("username") or ""))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    database.update_user(user["id"], password=body.new_password)
    database.add_audit(user["username"], "password_reset", details="Password reset from email link")
    return {"ok": True}


@router.post("/verify-email")
def verify_email(body: TokenBody):
    try:
        item = database.consume_email_token(body.token, "verify")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user = database.get_user_by_username(str(item.get("username") or ""))
    if not user:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    wanted = str(item.get("email") or user.get("email") or "").strip()
    if wanted and str(user.get("email") or "").strip().lower() != wanted.lower():
        raise HTTPException(status_code=400, detail="This email is no longer on the account. Request a new link.")
    database.update_user(user["id"], email_verified=1)
    database.add_audit(user["username"], "email_verify", details=f"Verified {wanted}")
    return {"ok": True, "email": wanted}


@router.post("/verify-email/resend")
def resend_verification(request: Request, user=Depends(get_current_user)):
    if not str(user.get("email") or "").strip():
        raise HTTPException(status_code=400, detail="Add an email on your account first.")
    if user.get("email_verified"):
        return {"ok": True, "already": True}
    result = mailer.send_verification(user, request)
    if result.get("skipped"):
        raise HTTPException(status_code=400, detail=result.get("reason") or "Email is not configured.")
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Could not send the email.")
    return {"ok": True}


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
        "must_change_password": bool(user.get("must_change_password")),
        "email_verified": bool(user.get("email_verified")),
        "email_enabled": mailer.is_configured(),
    }
