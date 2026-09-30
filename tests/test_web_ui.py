from fastapi.testclient import TestClient
from app.main import app

def test_original_web_ui():
    client = TestClient(app)
    
    # 1. 验证主页面加载原版 UI 布局
    r_main = client.get("/")
    assert r_main.status_code == 200
    assert 'id="module-sync"' in r_main.text
    assert 'id="module-keyword"' in r_main.text
    assert 'id="keywordFrame"' in r_main.text
    
    # 核心要求：管理员设置按钮已去除
    assert 'switchTab(\'admin\')' not in r_main.text
    assert '管理员设置' not in r_main.text
    
    # 2. 验证各个子页面均正常返回 200
    for path in ["/import", "/tasks", "/runs"]:
        r = client.get(path)
        assert r.status_code == 200
        assert 'id="module-sync"' in r.text
        
    # 3. 验证关键词页面与嵌入 iframe
    r_kw = client.get("/keyword")
    assert r_kw.status_code == 200
    assert 'keywordInput' in r_kw.text
    
    r_kw_embed = client.get("/keyword?embed=1")
    assert r_kw_embed.status_code == 200
    assert 'keywordInput' in r_kw_embed.text

