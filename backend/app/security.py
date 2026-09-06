from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from . import database
from .config import load_config
from .passwords import hash_password, verify_password  # re-export

VALID_ROLES = {"admin", "manager", "user", "readonly", "guest"}
GUEST_PAGES = [
    "dashboard",
    "work_orders",
    "open",
    "placed",
    "overdue",
    "closed",
    "queue",
    "suppliers",
    "analytics",
    "reports",
    "chat",
    "projects",
    "import",
    "performance",
]
ALL_PERMS = [
    "view",
    "edit",
    "create",
    "delete",
    "reports",
    "analytics",
    "settings",
    "users",
    "audit",
    "backup",
    "import",
    *GUEST_PAGES,
]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt, digest = stored.split("$", 3)
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iters)
        )
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


def create_token(user: dict[str, Any]) -> str:
    cfg = load_config()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "uid": user["id"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=cfg.jwt_expire_hours)).timestamp()),
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    cfg = load_config()
    try:
        return jwt.decode(token, cfg.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    payload = decode_token(token)
    user = database.get_user_by_username(payload.get("sub", ""))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def parse_extra_permissions(user: Optional[dict[str, Any]]) -> list[str]:
    if not user:
        return []
    raw = user.get("extra_permissions")
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            values = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            values = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        values = []
    allowed = set(ALL_PERMS)
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        key = str(item or "").strip()
        if key in allowed and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def user_permissions(user: dict[str, Any]) -> list[str]:
    role = str(user.get("role") or "user")
    cfg = load_config()
    if role == "admin":
        return list(ALL_PERMS)
    if role == "guest":
        extra = parse_extra_permissions(user)
        pages = [p for p in extra if p in GUEST_PAGES]
        return ["view", *pages]
    allowed = list(cfg.permissions.get(role) or ["view"])
    if "view" not in allowed:
        allowed = ["view", *allowed]
    return allowed


def require_permission(permission: str):
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") == "admin":
            return user
        allowed = user_permissions(user)
        if permission not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return checker


def optional_user(token: Optional[str] = Depends(oauth2_optional)) -> Optional[dict]:
    if not token:
        return None
    try:
        return get_current_user(token)
    except HTTPException:
        return None
