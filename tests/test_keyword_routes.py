import tempfile
from pathlib import Path
from unittest.mock import patch

from app.config import ACCESS_TOKEN
from app.main import app
from core.database import get_db_connection, run_migrations
from fastapi.testclient import TestClient


def test_keyword_routes_and_search_mocked():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_kw.db"
        conn = get_db_connection(db_file)
        run_migrations(conn, module="keyword")

        client = TestClient(app)
        r_login = client.post("/api/auth/login", json={"password": ACCESS_TOKEN})
        csrf = r_login.json().get("csrf_token")
        if csrf:
            client.headers["X-CSRF-Token"] = csrf

        # 1. 验证 HTML / 页面端点
        r_page = client.get("/keyword")
        assert r_page.status_code == 200

        # 2. 验证多词搜索接口 (使用 Mock 确保离线安全，不请求外部接口)
        mock_search_res = {
            "success": True,
            "overall_status": "success",
            "keywords": ["辛芷蕾同款凯乐石", "凯乐石"],
            "start_date": "2026-08-25",
            "end_date": "2026-09-23",
            "dates": ["2026-08-25"],
            "data": {
                "辛芷蕾同款凯乐石": {"2026-08-25": {"search_num": 66620, "imp_num": 100000, "note_num": 50, "bid": 2.5}},
                "凯乐石": {"2026-08-25": {"search_num": 5000, "imp_num": 10000, "note_num": 10, "bid": 1.5}}
            },
            "successful_keywords": ["辛芷蕾同款凯乐石", "凯乐石"],
            "empty_keywords": [],
            "failed_keywords": []
        }
        with patch("keyword_service.router.fetch_keywords_insight", return_value=mock_search_res):
            r_search = client.post("/api/keyword/search", json={
                "keywords": "辛芷蕾同款凯乐石 凯乐石",
                "start_date": "2026-08-25",
                "end_date": "2026-09-23"
            })
            assert r_search.status_code == 200
            s_data = r_search.json()
            assert s_data["success"] is True
            assert set(s_data["keywords"]) == {"辛芷蕾同款凯乐石", "凯乐石"}
            xzl_total = sum(v["search_num"] for v in s_data["data"]["辛芷蕾同款凯乐石"].values())
            assert xzl_total == 66620

        # 3. 验证词库接口
        r_lib = client.get("/api/keyword/library")
        assert r_lib.status_code == 200
        assert "categories" in r_lib.json()
        conn.close()

