import sys
import os
from pathlib import Path

console_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(console_dir))

from fastapi.testclient import TestClient
from app.main import app

def test_cookie_and_search_handling():
    client = TestClient(app)

    # 1. Test get cookie
    r_get = client.get("/api/keyword/cookie")
    assert r_get.status_code == 200
    data = r_get.json()
    assert "v_seller_id" in data
    assert "cookie_length" in data

    # 2. Test update cookie with empty
    r_empty = client.post("/api/keyword/cookie", json={"cookie": ""})
    assert r_empty.status_code == 400

    # 3. Test search with outdoor keyword that exists in local trends
    r_search = client.post("/api/keyword/search", json={"keywords": "凯乐石", "start_date": "2026-09-01", "end_date": "2026-09-10"})
    assert r_search.status_code == 200
    s_data = r_search.json()
    assert s_data["success"] is True
    assert "凯乐石" in s_data["data"]
    nums = [v["search_num"] for v in s_data["data"]["凯乐石"].values()]
    assert sum(nums) > 0, "Should have non-zero metrics!"

