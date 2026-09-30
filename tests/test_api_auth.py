import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import ACCESS_TOKEN
from core.security import SESSION_COOKIE_NAME

@pytest.fixture
def client():
    # Use TestClient with app
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
    # 错误密码
    r_bad = client.post("/api/auth/login", json={"password": "wrong_password"})
    assert r_bad.status_code == 400
    
    # 正确密码
    r_ok = client.post("/api/auth/login", json={"password": ACCESS_TOKEN})
    assert r_ok.status_code == 200
    res_data = r_ok.json()
    assert res_data.get("success") is True
    # 绝对不再向前端返回明文密码或 ACCESS_TOKEN！
    assert "token" not in res_data
    
    # 确认设置了 HttpOnly session cookie
    assert SESSION_COOKIE_NAME in client.cookies
    
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
    # 核心安全保证：绝对不返回 cookie_preview 或任何 cookie 字符串片段！
    assert "cookie_preview" not in c_data
    assert "cookie" not in c_data

def test_admin_route_protection(client):
    # 登出状态下访问写接口全部 401
    client.post("/api/auth/logout")
    
    r_settings = client.get("/api/settings")
    assert r_settings.status_code == 401
    
    r_create = client.post("/api/create_task", json={"task_name": "x", "platform": "jzt", "sheets": []})
    assert r_create.status_code == 401
    
    r_kw_task = client.post("/api/keyword/tasks", json={"task_name": "x", "keywords": ["a"]})
    assert r_kw_task.status_code == 401

