import hmac
import hashlib
import time
import json
import base64
import os
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
from app.config import ACCESS_TOKEN

SESSION_SECRET = os.getenv("SESSION_SECRET", ACCESS_TOKEN or "sync-console-secret-key").encode("utf-8")
SESSION_COOKIE_NAME = "sync_session"

def sign_payload(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    b64_data = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    sig = hmac.new(SESSION_SECRET, b64_data.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_data}.{sig}"

def verify_session_str(token: str) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    b64_data, sig = token.rsplit(".", 1)
    expected_sig = hmac.new(SESSION_SECRET, b64_data.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        padded = b64_data + "=" * (-len(b64_data) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        data = json.loads(raw.decode("utf-8"))
        # 检查过期时间 (默认30天)
        if data.get("exp") and data["exp"] < time.time():
            return None
        return data
    except Exception:
        return None

def create_admin_session() -> str:
    payload = {
        "role": "admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400 * 30
    }
    return sign_payload(payload)

def is_admin_authenticated(request: Request) -> bool:
    # 1. 优先检查 HttpOnly Cookie
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        session = verify_session_str(cookie_token)
        if session and session.get("role") == "admin":
            return True
            
    # 2. 检查 Header: X-Access-Token (兼容旧客户端或直接密码/签名)
    header_token = request.headers.get("X-Access-Token") or ""
    if header_token:
        session = verify_session_str(header_token)
        if session and session.get("role") == "admin":
            return True
        if ACCESS_TOKEN and header_token == ACCESS_TOKEN:
            return True
            
    # 3. 检查 Authorization: Bearer
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        bearer_val = auth_header[7:].strip()
        session = verify_session_str(bearer_val)
        if session and session.get("role") == "admin":
            return True
        if ACCESS_TOKEN and bearer_val == ACCESS_TOKEN:
            return True
            
    # 4. 检查旧 access_token cookie
    legacy_cookie = request.cookies.get("access_token")
    if legacy_cookie and ACCESS_TOKEN and legacy_cookie == ACCESS_TOKEN:
        return True
        
    return False

def require_admin(request: Request) -> bool:
    auth_mode = os.getenv("AUTH_MODE", "token").strip().lower()
    if auth_mode == "internal":
        return True
    if not is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="未授权，需要管理员权限")
    return True

def require_auth(request: Request) -> bool:
    auth_mode = os.getenv("AUTH_MODE", "internal").strip().lower()
    if auth_mode == "internal":
        return True
    return require_admin(request)

