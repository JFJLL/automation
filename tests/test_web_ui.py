from fastapi.testclient import TestClient
from sync_console.app.main import app

def test_react_spa_production_serving():
    client = TestClient(app)
    
    # 1. 验证所有 SPA 路由均正常返回 200 并加载 React SPA 入口
    routes = [
        "/",
        "/import",
        "/tasks",
        "/runs",
        "/keyword",
        "/keyword/tasks",
        "/keyword/runs",
        "/settings",
        "/admin"
    ]
    for r in routes:
        resp = client.get(r)
        assert resp.status_code == 200, f"Route {r} must return 200"
        assert '<div id="root"></div>' in resp.text
        # 核心架构断言：彻底消除 iframe 嵌套架构
        assert '<iframe id="keywordFrame"' not in resp.text
        assert 'keywordFrame' not in resp.text

    # 2. 验证 favicon 服务安全无报错
    r_fav = client.get("/favicon.svg")
    assert r_fav.status_code == 200
    
    r_ico = client.get("/favicon.ico")
    assert r_ico.status_code == 200

