import hmac
import hashlib
import time
import json
import base64
import os
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends, Header
from app.config import ACCESS_TOKEN

SESSION_SECRET = os.getenv("SESSION_SECRET", ACCESS_TOKEN or "sync-console-secret-key").encode("utf-8")
SESSION_COOKIE_NAME = "sync_session"
ADMIN_ROLES = {"admin", "simple_promo_admin"}

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

def is_admin_authenticated(request: Optional[Request] = None) -> bool:
    return True

def require_admin(request: Optional[Request] = None) -> bool:
    return True

def require_auth(request: Optional[Request] = None) -> bool:
    return True


def get_admin_token(request: Optional[Request] = None, header_token: Optional[str] = None) -> Optional[str]:
    """按优先级收集管理员会话凭据：请求头 > 私密板块 Cookie > 后台登录 Cookie"""
    if header_token:
        return header_token
    if request is not None:
        return (
            request.headers.get("x-admin-token")
            or request.headers.get("x-simple-promo-token")
            or request.cookies.get("simple_promo_token")
            or request.cookies.get(SESSION_COOKIE_NAME)
        )
    return None


def is_admin_session(token: Optional[str]) -> bool:
    data = verify_session_str(token or "")
    if not data:
        return False
    return str(data.get("role") or "") in ADMIN_ROLES


def require_admin_access(
    request: Request,
    x_simple_promo_token: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
):
    """删除等高风险操作的管理员校验。

    /admin 解锁后浏览器会持有 simple_promo_token，删除操作据此放行；
    未解锁时一律 401，避免任何前端按钮被绕过直接调用接口。
    """
    token = get_admin_token(request, x_admin_token or x_simple_promo_token)
    if not is_admin_session(token):
        raise HTTPException(status_code=401, detail="该操作仅限管理员：请先访问 /admin 并输入管理口令解锁")
    return True
