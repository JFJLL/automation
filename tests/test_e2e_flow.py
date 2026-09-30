import tempfile
from unittest.mock import MagicMock, patch

import pytest
from app.config import ACCESS_TOKEN
from app.main import app
from core.models import ProviderFetchResult, ProviderFetchStatus
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": ACCESS_TOKEN})
        csrf = r.json().get("csrf_token")
        if csrf:
            c.headers["X-CSRF-Token"] = csrf
        yield c

def test_e2e_data_sync_and_keyword_flow(client):
    with tempfile.TemporaryDirectory():
        mock_feishu = MagicMock()
        mock_feishu.get_or_create_shared_folder.return_value = "fld_mock"
        mock_feishu.create_spreadsheet.return_value = {
            "spreadsheet_token": "ss_mock_123",
            "url": "https://feishu.cn/sheets/ss_mock_123"
        }
        mock_feishu.get_sheets.return_value = [{"sheet_id": "0", "grid_properties": {"column_count": 50, "row_count": 200}}]
        mock_feishu.read_values.return_value = [["日期", "任务ID", "成交GMV"]]
        mock_feishu.find_last_row_index.return_value = 1

        mock_jzt_result = ProviderFetchResult(
            status=ProviderFetchStatus.SUCCESS,
            rows=[{"日期": "2026-09-20", "任务ID": "198973", "成交GMV": 500.0}]
        )

        # 1. 模拟数据同步全流程
        with patch("app.main.FeishuClient", return_value=mock_feishu),              patch("core.sync.FeishuClient", return_value=mock_feishu),              patch("core.sync.fetch_jzt_data", return_value=mock_jzt_result),              patch("core.sync.Notifier"):

            # 创建任务
            create_payload = {
                "task_name": "E2E京准通测试",
                "platform": "jzt",
                "update_mode": "append",
                "calibration_days": 2,
                "rrule": "RRULE:FREQ=DAILY;BYHOUR=9",
                "sheets": [
                    {
                        "sheet_title": "每日数据",
                        "dimension": "",
                        "id_column": "任务ID",
                        "date_column": "日期",
                        "headers": ["日期", "任务ID", "成交GMV"],
                        "entity_ids": ["198973"],
                        "column_mapping": []
                    }
                ]
            }
            r_create = client.post("/api/create_task", json=create_payload)
            assert r_create.status_code == 200
            task_id = r_create.json()["task_id"]

            # 立即执行任务
            r_run = client.post(f"/api/tasks/{task_id}/run_now")
            assert r_run.status_code == 200
            assert r_run.json()["status"] == "success"

            # 查看 runs 列表
            r_runs = client.get("/api/runs")
            assert r_runs.status_code == 200
            runs_data = r_runs.json()
            assert any(r["task_id"] == task_id for r in runs_data)

        # 2. 模拟关键词全流程
        mock_kw_insight = {
            "success": True,
            "overall_status": "success",
            "keywords": ["冲锋衣"],
            "start_date": "2026-09-20",
            "end_date": "2026-09-28",
            "dates": ["2026-09-20"],
            "data": {"冲锋衣": {"2026-09-20": {"search_num": 3000, "imp_num": 6000, "note_num": 20, "bid": 2.2}}},
            "successful_keywords": ["冲锋衣"],
            "empty_keywords": [],
            "failed_keywords": [],
            "keyword_statuses": {"冲锋衣": {"status": "success"}}
        }
        with patch("keyword_service.router.fetch_keywords_insight", return_value=mock_kw_insight),              patch("keyword_service.sync_engine.fetch_keywords_insight", return_value=mock_kw_insight),              patch("keyword_service.sync_engine.FeishuClient", return_value=mock_feishu):

            # 关键词查询
            r_kw_search = client.post("/api/keyword/search", json={"keywords": "冲锋衣"})
            assert r_kw_search.status_code == 200
            assert r_kw_search.json()["data"]["冲锋衣"]["2026-09-20"]["search_num"] == 3000

            # 创建关键词任务
            r_kw_task = client.post("/api/keyword/tasks", json={
                "task_name": "E2E关键词任务",
                "keywords": ["冲锋衣"],
                "update_mode": "overwrite",
                "rrule": "FREQ=DAILY;BYHOUR=12;BYMINUTE=30",
                "days_range": 90
            })
            assert r_kw_task.status_code == 200
            kw_task_id = r_kw_task.json()["task_id"]

            # 立即运行关键词任务
            r_kw_run = client.post(f"/api/keyword/tasks/{kw_task_id}/run_now")
            assert r_kw_run.status_code == 200
            assert r_kw_run.json()["status"] == "success"

            # 查看关键词 runs 列表
            r_kw_runs = client.get("/api/keyword/runs")
            assert r_kw_runs.status_code == 200
            assert r_kw_runs.json()["total"] >= 1

