import sys
import os
from pathlib import Path

console_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(console_dir))

from fastapi.testclient import TestClient
from app.main import app

def test_routing_and_endpoints():
    client = TestClient(app)
    
    r_kw = client.get("/keyword")
    assert r_kw.status_code == 200
    
    r_tasks = client.get("/keyword/tasks")
    assert r_tasks.status_code == 200
    
    r_runs = client.get("/keyword/runs")
    assert r_runs.status_code == 200

    html = r_kw.text
    assert 'id="keywordFrame"' in html
    assert 'id="module-keyword"' in html
    assert 'id="module-sync"' in html
    assert 'sidebar-group-keyword' in html

    r_embed = client.get("/keyword?embed=1")
    assert r_embed.status_code == 200
    embed_html = r_embed.text
    assert 'initKeywordRouter()' in embed_html
    assert 'initDragSelection()' in embed_html
    assert "activePrimaryCategory = '全部词库'" in embed_html

    app_js = (console_dir / "web" / "app.js").read_text(encoding="utf-8")
    assert "updateTaskCountBadge()" in app_js
    assert "switchToKeywordSection" in app_js
    assert "switchToSyncSection" in app_js

