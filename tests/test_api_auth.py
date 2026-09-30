import os
import re
from unittest.mock import patch

import pytest
from app.config import ACCESS_TOKEN
from app.main import PUBLIC_API_ROUTES, app
from core.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, get_session_secret, reset_login_rate_limit
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_health_and_ready_endpoints(client):
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_ready = client.get("/api/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["status"] == "ready"
    assert r_ready.json()["database"] == "ok"

def test_login_flow_session_cookie_no_token_leak(client):
    reset_login_rate_limit("testclient")
    # 错误密码
    r_bad = client.post("/api/auth/login", json={"password": "wrong_password"})
    assert r_bad.status_code == 400

    # 正确密码
    r_ok = client.post("/api/auth/login", json={"password": ACCESS_TOKEN})
    assert r_ok.status_code == 200
    res_data = r_ok.json()
    assert res_data.get("success") is True
    assert "token" not in res_data
    assert "csrf_token" in res_data

    # 确认设置了 HttpOnly session cookie 和 csrf cookie
    assert SESSION_COOKIE_NAME in client.cookies
    assert CSRF_COOKIE_NAME in client.cookies

    # 验证 auth/check 端点
    r_check = client.get("/api/auth/check")
    assert r_check.status_code == 200
    assert r_check.json()["authenticated"] is True

    # 登出测试
    r_logout = client.post("/api/auth/logout")
    assert r_logout.status_code == 200
    r_check_after = client.get("/api/auth/check")
    assert r_check_after.json()["authenticated"] is False

def test_cookie_preview_never_exposed(client):
    reset_login_rate_limit("testclient")
    client.post("/api/auth/logout")
    # 未登录访问返回 401
    r_unauth = client.get("/api/keyword/cookie")
    assert r_unauth.status_code == 401

    # 登录后访问
    client.post("/api/auth/login", json={"password": ACCESS_TOKEN})
    r_cookie = client.get("/api/keyword/cookie")
    assert r_cookie.status_code == 200
    c_data = r_cookie.json()
    assert "configured" in c_data
    assert "v_seller_id" in c_data
    assert "cookie_preview" not in c_data
    assert "cookie" not in c_data

def test_admin_route_protection(client):
    reset_login_rate_limit("testclient")
    # 登出状态下访问写接口全部 401
    client.post("/api/auth/logout")

    r_settings = client.get("/api/settings")
    assert r_settings.status_code == 401

    r_create = client.post("/api/create_task", json={"task_name": "x", "platform": "jzt", "sheets": []})
    assert r_create.status_code == 401

    r_kw_task = client.post("/api/keyword/tasks", json={"task_name": "x", "keywords": ["a"]})
    assert r_kw_task.status_code == 401

def test_dynamic_api_routes_all_require_auth(client):
    # 动态发现所有注册在 app 中的 /api/* 路由，确保未登录全部返回 401 (白名单除外)
    client.post("/api/auth/logout")
    discovered_routes = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/"):
            # 替换路径参数如 {task_id} 为 1
            concrete_path = re.sub(r"\{[^}]+}", "1", route.path)
            for method in route.methods:
                if method not in ("OPTIONS", "HEAD"):
                    discovered_routes.add((concrete_path, method, route.path))

    for path, method, raw_path in discovered_routes:
        if raw_path in PUBLIC_API_ROUTES or path in PUBLIC_API_ROUTES:
            continue
        resp = client.request(method, path)
        assert resp.status_code == 401, f"Route {method} {path} should be 401 when unauthenticated, got {resp.status_code}"

def test_session_secret_enforcement():
    with patch.dict(os.environ, {"SESSION_SECRET": ""}):
        with pytest.raises(RuntimeError):
            get_session_secret()

    with patch.dict(os.environ, {"SESSION_SECRET": "short_secret_under_32_chars"}):
        with pytest.raises(RuntimeError):
            get_session_secret()

def test_csrf_protection_on_state_mutations(client):
    reset_login_rate_limit("testclient")
    # 登录获取 session cookie
    r_login = client.post("/api/auth/login", json={"password": ACCESS_TOKEN})
    assert r_login.status_code == 200
    csrf_token = r_login.json()["csrf_token"]

    # 尝试在有 cookie 认证下发起 POST 请求但缺少 X-CSRF-Token -> 403
    r_no_csrf = client.post("/api/tasks/1/toggle_status")
    assert r_no_csrf.status_code == 403
    assert "CSRF" in r_no_csrf.json().get("detail", "")

    # 携带错误的 CSRF token -> 403
    r_bad_csrf = client.post("/api/tasks/1/toggle_status", headers={"X-CSRF-Token": "invalid_csrf_token"})
    assert r_bad_csrf.status_code == 403

    # 携带正确的 CSRF token -> 允许通行 (返回 404 因为任务 1 不存在，绝非 403)
    r_ok_csrf = client.post("/api/tasks/1/toggle_status", headers={"X-CSRF-Token": csrf_token})
    assert r_ok_csrf.status_code in (200, 404)

def test_login_rate_limiting(client):
    reset_login_rate_limit("testclient")
    # 连续 10 次密码错误尝试
    for _ in range(10):
        r = client.post("/api/auth/login", json={"password": "bad_password"})
        assert r.status_code == 400

    # 第 11 次尝试返回 429 Too Many Requests
    r_11 = client.post("/api/auth/login", json={"password": "bad_password"})
    assert r_11.status_code == 429
    assert "频繁" in r_11.json()["detail"]
    reset_login_rate_limit("testclient")
