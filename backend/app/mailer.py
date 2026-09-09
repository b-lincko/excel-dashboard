from __future__ import annotations

import html
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any, Optional

from . import database
from .config import load_config

OUTBOX: list[dict[str, Any]] = []

SECRET_FIELDS = ("jwt_secret", "smtp_password", "resend_api_key")
FAKE_EMAIL_SUFFIXES = ("@woms.local", "@local")


def _testing() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    flag = (os.environ.get("WOMS_TESTING") or "").strip().lower()
    return flag in {"1", "true", "yes"}


def provider_name(cfg=None) -> str:
    cfg = cfg or load_config()
    name = str(getattr(cfg, "email_provider", "") or "off").strip().lower()
    if name in {"", "none", "off", "disabled"}:
        return "off"
    if name in {"smtp", "resend"}:
        return name
    return "off"


def is_configured(cfg=None) -> bool:
    cfg = cfg or load_config()
    provider = provider_name(cfg)
    if provider == "resend":
        return bool(str(getattr(cfg, "resend_api_key", "") or "").strip())
    if provider == "smtp":
        return bool(str(getattr(cfg, "smtp_host", "") or "").strip())
    return False


def public_base(request: Any = None, cfg=None) -> str:
    cfg = cfg or load_config()
    url = str(getattr(cfg, "email_public_url", "") or os.environ.get("WOMS_PUBLIC_URL") or "").strip().rstrip("/")
    if url:
        return url
    if request is not None:
        try:
            return str(request.base_url).rstrip("/")
        except Exception:
            pass
    return ""


def looks_real_email(address: str) -> bool:
    text = str(address or "").strip()
    if "@" not in text or "." not in text.split("@")[-1]:
        return False
    lower = text.lower()
    return not any(lower.endswith(suf) for suf in FAKE_EMAIL_SUFFIXES)


def _from_header(cfg) -> str:
    addr = str(getattr(cfg, "email_from_address", "") or "").strip()
    name = str(getattr(cfg, "email_from_name", "") or "").strip() or "Linkco MR"
    if not addr:
        raise ValueError("Set a From email address in Settings.")
    return f"{name} <{addr}>" if name else addr


def _html_body(title: str, body: str, url: str = "", cta: str = "") -> str:
    safe_title = html.escape(title)
    paragraphs = "".join(f"<p style=\"margin:0 0 12px;line-height:1.5\">{html.escape(p)}</p>" for p in body.split("\n") if p.strip())
    button = ""
    if url:
        label = html.escape(cta or "Open Linkco MR")
        href = html.escape(url, quote=True)
        button = (
            f'<p style="margin:24px 0"><a href="{href}" style="display:inline-block;background:#0D9F8A;color:#fff;'
            f'padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600">{label}</a></p>'
            f'<p style="font-size:12px;color:#64748b;word-break:break-all">{html.escape(url)}</p>'
        )
    return (
        '<div style="font-family:Segoe UI,system-ui,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#0f172a">'
        f"<h1 style=\"font-size:18px;margin:0 0 16px\">{safe_title}</h1>"
        f"{paragraphs}{button}"
        '<p style="margin-top:28px;font-size:12px;color:#94a3b8">Linkco MR · material requests</p>'
        "</div>"
    )


def _text_body(body: str, url: str = "") -> str:
    if url:
        return f"{body.strip()}\n\n{url}\n"
    return body.strip() + "\n"


def send_mail(
    to: str,
    subject: str,
    body: str,
    *,
    url: str = "",
    cta: str = "",
    title: str = "",
) -> dict[str, Any]:
    dest = str(to or "").strip()
    if not dest:
        return {"ok": False, "skipped": True, "reason": "no address"}
    if not looks_real_email(dest):
        return {"ok": False, "skipped": True, "reason": "placeholder email"}
    cfg = load_config()
    provider = provider_name(cfg)
    if provider == "off":
        return {"ok": False, "skipped": True, "reason": "email is off"}
    if provider == "resend" and not str(getattr(cfg, "resend_api_key", "") or "").strip():
        return {"ok": False, "skipped": True, "reason": "Resend API key is missing"}
    if provider == "smtp" and not str(getattr(cfg, "smtp_host", "") or "").strip():
        return {"ok": False, "skipped": True, "reason": "SMTP host is missing"}
    if not str(getattr(cfg, "email_from_address", "") or "").strip():
        return {"ok": False, "skipped": True, "reason": "From email is missing"}
    heading = title or subject
    payload = {
        "to": dest,
        "subject": subject,
        "text": _text_body(body, url),
        "html": _html_body(heading, body, url, cta),
        "url": url,
        "provider": provider,
    }
    if _testing():
        OUTBOX.append(payload)
        return {"ok": True, "provider": "test", "to": dest}
    try:
        if provider == "resend":
            _send_resend(cfg, payload)
        else:
            _send_smtp(cfg, payload)
        return {"ok": True, "provider": provider, "to": dest}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "provider": provider, "to": dest}


def _send_smtp(cfg, payload: dict[str, Any]) -> None:
    host = str(getattr(cfg, "smtp_host", "") or "").strip()
    if not host:
        raise ValueError("SMTP host is required.")
    port = int(getattr(cfg, "smtp_port", 587) or 587)
    security = str(getattr(cfg, "smtp_security", "starttls") or "starttls").strip().lower()
    username = str(getattr(cfg, "smtp_username", "") or "").strip()
    password = str(getattr(cfg, "smtp_password", "") or "")
    msg = EmailMessage()
    msg["Subject"] = payload["subject"]
    msg["From"] = _from_header(cfg)
    msg["To"] = payload["to"]
    msg.set_content(payload["text"])
    msg.add_alternative(payload["html"], subtype="html")
    context = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(msg)
        return
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.ehlo()
        if security != "none":
            smtp.starttls(context=context)
            smtp.ehlo()
        if username:
            smtp.login(username, password)
        smtp.send_message(msg)


def _send_resend(cfg, payload: dict[str, Any]) -> None:
    key = str(getattr(cfg, "resend_api_key", "") or "").strip()
    if not key:
        raise ValueError("Resend API key is required.")
    from_addr = str(getattr(cfg, "email_from_address", "") or "").strip()
    from_name = str(getattr(cfg, "email_from_name", "") or "").strip()
    if not from_addr:
        raise ValueError("Set a From email address in Settings. It must be on a domain verified in Resend.")
    sender = f"{from_name} <{from_addr}>" if from_name else from_addr
    body = json.dumps(
        {
            "from": sender,
            "to": [payload["to"]],
            "subject": payload["subject"],
            "html": payload["html"],
            "text": payload["text"],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "Linkco-MR/1.1",
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        hint = ""
        if exc.code in {401, 403}:
            hint = " Check the API key."
        elif exc.code == 422:
            hint = " From address must be on a domain you verified in Resend."
        raise ValueError(f"Resend rejected the email ({exc.code}): {detail}.{hint}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach Resend: {exc.reason}") from exc


def link_for(path: str, request: Any = None, cfg=None) -> str:
    base = public_base(request, cfg)
    rel = path if str(path).startswith("/") else f"/{path}"
    return f"{base}{rel}" if base else rel


def send_verification(user: dict[str, Any], request: Any = None) -> dict[str, Any]:
    email = str(user.get("email") or "").strip()
    if not looks_real_email(email):
        return {"ok": False, "skipped": True, "reason": "no real email"}
    if not is_configured():
        return {"ok": False, "skipped": True, "reason": "email is off"}
    token = database.create_email_token(user["username"], "verify", email, hours=48)
    url = link_for(f"/verify-email?token={token}", request)
    name = user.get("full_name") or user.get("username")
    return send_mail(
        email,
        "Verify your Linkco MR email",
        f"Hello {name},\n\nConfirm this email for your Linkco MR login ({user.get('username')}). "
        "The link expires in 48 hours.",
        url=url,
        cta="Verify email",
        title="Verify your email",
    )


def send_reset(user: dict[str, Any], request: Any = None) -> dict[str, Any]:
    email = str(user.get("email") or "").strip()
    if not looks_real_email(email):
        return {"ok": False, "skipped": True, "reason": "no real email"}
    if not is_configured():
        return {"ok": False, "skipped": True, "reason": "email is off"}
    token = database.create_email_token(user["username"], "reset", email, hours=2)
    url = link_for(f"/reset-password?token={token}", request)
    name = user.get("full_name") or user.get("username")
    return send_mail(
        email,
        "Reset your Linkco MR password",
        f"Hello {name},\n\nSomeone asked to reset the password for {user.get('username')}. "
        "If that was you, use this link within 2 hours. If not, ignore this email.",
        url=url,
        cta="Choose a new password",
        title="Password reset",
    )


def notify_path(kind: str, record_id: str = "", work_order_id: str = "", thread_id: Any = None) -> str:
    rid = str(record_id or "").strip()
    if kind in {"po", "accounts", "ping"} and rid:
        return f"/approvals?id={rid}"
    if rid:
        return f"/work-orders/{rid}"
    if thread_id:
        return f"/chat?thread={thread_id}"
    return "/"


def should_email_kind(kind: str, cfg=None) -> bool:
    cfg = cfg or load_config()
    key = str(kind or "").strip().lower()
    if key in {"po", "accounts", "ping"}:
        return bool(getattr(cfg, "email_notify_po", True))
    if key == "assign":
        return bool(getattr(cfg, "email_notify_assign", True))
    if key == "mention":
        return bool(getattr(cfg, "email_notify_mention", True))
    if key in {"message", "watch"}:
        return bool(getattr(cfg, "email_notify_chat", False))
    return False


def maybe_notify_email(
    username: str,
    kind: str,
    body: str,
    *,
    record_id: str = "",
    work_order_id: str = "",
    thread_id: Any = None,
) -> Optional[dict[str, Any]]:
    if not is_configured() or not should_email_kind(kind):
        return None
    user = database.get_user_by_username(username)
    if not user or not user.get("is_active"):
        return None
    email = str(user.get("email") or "").strip()
    if not looks_real_email(email):
        return None
    path = notify_path(kind, record_id, work_order_id, thread_id)
    url = link_for(path)
    wo = work_order_id or record_id
    subject = {
        "po": f"PO request{f' · {wo}' if wo else ''}",
        "ping": f"PO follow-up{f' · {wo}' if wo else ''}",
        "accounts": f"PO for Accounts{f' · {wo}' if wo else ''}",
        "assign": f"Assigned to you{f' · {wo}' if wo else ''}",
        "mention": "You were mentioned in Linkco MR",
        "message": "New chat message",
        "watch": f"Update{f' · {wo}' if wo else ''}",
    }.get(kind, "Linkco MR notification")
    return send_mail(email, subject, str(body or ""), url=url, cta="Open in Linkco MR", title=subject)
