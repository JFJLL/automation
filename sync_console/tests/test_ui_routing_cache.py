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
    assert 'id="kwTaskCountBadge"' in html
    assert 'selectRunsPageSize(' in html
    assert 'initKeywordRouter()' in html
    assert 'updateKeywordTaskBadge()' in html

    app_js = (console_dir / "web" / "app.js").read_text(encoding="utf-8")
    assert "updateTaskCountBadge()" in app_js
    assert "renderTasksList(" in app_js
    assert "renderRunsTable(" in app_js

