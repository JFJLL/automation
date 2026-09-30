# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections import defaultdict
from typing import Any, Dict, Optional

from app.config import (
    ACCESS_TOKEN,
    ALLOW_INTERNAL_AUTH,
    AUTH_MODE,
)
from app.config import (
    SESSION_SECRET as CONFIG_SESSION_SECRET,
)
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "sync_session"
CSRF_COOKIE_NAME = "csrf_token"

# Rate limiting storage: ip -> list of timestamps
_login_attempts: Dict[str, list] = defaultdict(list)
LOGIN_RATE_LIMIT = 10  # max 10 per minute
LOGIN_RATE_WINDOW = 60  # seconds

def get_session_secret() -> bytes:
    sec = os.getenv("SESSION_SECRET", CONFIG_SESSION_SECRET or "")
    if not sec or len(sec) < 32:
        raise RuntimeError("SESSION_SECRET must be configured and be at least 32 characters long.")
    return sec.encode("utf-8")

def sign_payload(payload: Dict[str, Any]) -> str:
    secret = get_session_secret()
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    b64_data = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    sig = hmac.new(secret, b64_data.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_data}.{sig}"

def verify_session_str(token: str) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        secret = get_session_secret()
    except RuntimeError:
        return None

    b64_data, sig = token.rsplit(".", 1)
    expected_sig = hmac.new(secret, b64_data.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        padded = b64_data + "=" * (-len(b64_data) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        data = json.loads(raw.decode("utf-8"))
        if data.get("exp") and data["exp"] < time.time():
            return None
        return data
    except Exception:
        return None

def create_admin_session() -> str:
    payload = {
        "role": "admin",
        "jti": secrets.token_hex(16),
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400 * 30
    }
    return sign_payload(payload)

def generate_csrf_token() -> str:
    return secrets.token_hex(16)

def check_login_rate_limit(client_ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _login_attempts[client_ip] if now - t < LOGIN_RATE_WINDOW]
    _login_attempts[client_ip] = attempts
    if len(attempts) >= LOGIN_RATE_LIMIT:
        return False
    _login_attempts[client_ip].append(now)
    return True

def reset_login_rate_limit(client_ip: str) -> None:
    _login_attempts.pop(client_ip, None)

def is_admin_authenticated(request: Request) -> bool:
    # 1. HttpOnly Session Cookie
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        session = verify_session_str(cookie_token)
        if session and session.get("role") == "admin":
            return True

    # 2. Header: X-Access-Token
    header_token = request.headers.get("X-Access-Token") or ""
    if header_token:
        session = verify_session_str(header_token)
        if session and session.get("role") == "admin":
            return True
        if ACCESS_TOKEN and hmac.compare_digest(header_token, ACCESS_TOKEN):
            return True

    # 3. Header: Authorization: Bearer
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        bearer_val = auth_header[7:].strip()
        session = verify_session_str(bearer_val)
        if session and session.get("role") == "admin":
            return True
        if ACCESS_TOKEN and hmac.compare_digest(bearer_val, ACCESS_TOKEN):
            return True

    return False

def verify_csrf_token(request: Request) -> None:
    # Only verify CSRF if authenticated via session cookie and method modifies state
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.url.path in ("/api/auth/login", "/api/auth/logout"):
            return
        # If client supplied valid Bearer or X-Access-Token header, CSRF is not required
        bearer = request.headers.get("Authorization", "")
        token_hdr = request.headers.get("X-Access-Token", "")
        if (bearer.startswith("Bearer ") and ACCESS_TOKEN and hmac.compare_digest(bearer[7:].strip(), ACCESS_TOKEN)) or            (token_hdr and ACCESS_TOKEN and hmac.compare_digest(token_hdr, ACCESS_TOKEN)):
            return

        cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
        header_csrf = request.headers.get("X-CSRF-Token")
        if not cookie_csrf or not header_csrf or not hmac.compare_digest(cookie_csrf, header_csrf):
            raise HTTPException(status_code=403, detail="CSRF 校验失败: 缺少或不匹配的 X-CSRF-Token")

def require_admin(request: Request) -> bool:
    # Internal mode only valid if ALLOW_INTERNAL_AUTH=1
    auth_mode = AUTH_MODE or "token"
    if auth_mode == "internal":
        if ALLOW_INTERNAL_AUTH:
            logger.warning("AUTH_MODE is set to internal; authentication is bypassed due to ALLOW_INTERNAL_AUTH=1.")
            return True
        else:
            logger.error("AUTH_MODE=internal requested but ALLOW_INTERNAL_AUTH is not enabled. Failing closed.")
            raise HTTPException(status_code=401, detail="未授权，需要管理员权限")

    if not is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="未授权，需要管理员权限")

    # Double submit CSRF check for state mutation requests authenticated via cookie
    verify_csrf_token(request)
    return True

def require_auth(request: Request) -> bool:
    return require_admin(request)
