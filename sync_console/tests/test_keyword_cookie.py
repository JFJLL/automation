import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.config import ACCESS_TOKEN

def test_cookie_and_search_handling():
    client = TestClient(app)
    # 登录管理员
    r = client.post("/api/auth/login", json={"password": ACCESS_TOKEN})
    csrf = r.json().get("csrf_token")
    if csrf:
        client.headers["X-CSRF-Token"] = csrf

    # 1. Test get cookie
    r_get = client.get("/api/keyword/cookie")
    assert r_get.status_code == 200
    data = r_get.json()
    assert "v_seller_id" in data
    assert "cookie_length" in data
    assert "cookie_preview" not in data

    # 2. Test update cookie with empty
    r_empty = client.post("/api/keyword/cookie", json={"cookie": ""})
    assert r_empty.status_code == 400

    # 3. Test search with mock insight fetch (隔离外部真实接口)
    mock_insight = {
        "success": True,
        "overall_status": "success",
        "keywords": ["凯乐石"],
        "start_date": "2026-09-01",
        "end_date": "2026-09-10",
        "dates": ["2026-09-01"],
        "data": {"凯乐石": {"2026-09-01": {"search_num": 100, "imp_num": 200, "note_num": 10, "bid": 2.0}}},
        "successful_keywords": ["凯乐石"],
        "empty_keywords": [],
        "failed_keywords": []
    }
    with patch("keyword_service.router.fetch_keywords_insight", return_value=mock_insight):
        r_search = client.post("/api/keyword/search", json={"keywords": "凯乐石", "start_date": "2026-09-01", "end_date": "2026-09-10"})
        assert r_search.status_code == 200
        s_data = r_search.json()
        assert s_data["success"] is True
        assert "凯乐石" in s_data["data"]
        nums = [v["search_num"] for v in s_data["data"]["凯乐石"].values()]
        assert sum(nums) > 0

