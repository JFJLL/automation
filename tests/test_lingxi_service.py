import pytest
import json
from fastapi.testclient import TestClient
from sync_console.app.main import app
from lingxi_service.db import init_db, get_db
from lingxi_service.sync_engine import (
    build_lingxi_matrix,
    create_lingxi_task,
    append_keywords_to_lingxi_task,
    remove_keywords_from_lingxi_task
)

client = TestClient(app)

def test_lingxi_matrix_builder():
    keywords = ["奶粉", "纸尿裤"]
    data = {
        "奶粉": {"user_cnt": 12000},
        "纸尿裤": {"user_cnt": 8500}
    }
    time_str = "2026-09-30 12:00:00"
    matrix = build_lingxi_matrix(keywords, data, time_str)
    assert len(matrix) == 3
    assert matrix[0] == ["关键词", "覆盖人群数量", "统计时间"]
    assert matrix[1] == ["奶粉", 12000, time_str]
    assert matrix[2] == ["纸尿裤", 8500, time_str]

def test_lingxi_task_crud():
    init_db()
    task_id = create_lingxi_task(
        name="测试灵犀任务",
        keywords=["奶粉", "辅食"],
        spreadsheet_token="test_token_123",
        spreadsheet_url="https://feishu.cn/sheets/test_token_123",
        update_mode="overwrite",
        rrule="FREQ=DAILY;BYHOUR=10;BYMINUTE=0"
    )
    assert task_id > 0

    # 追加关键词
    updated = append_keywords_to_lingxi_task(task_id, ["米粉", "辅食"])
    assert "米粉" in updated
    assert len(updated) == 3 # 去重后

    # 移除关键词
    remaining = remove_keywords_from_lingxi_task(task_id, ["辅食"])
    assert "辅食" not in remaining
    assert len(remaining) == 2

def test_lingxi_api_routes():
    init_db()
    res = client.get("/api/lingxi/tasks")
    assert res.status_code == 200
    tasks = res.json()
    assert isinstance(tasks, list)

    res_runs = client.get("/api/lingxi/runs")
    assert res_runs.status_code == 200
    runs_data = res_runs.json()
    assert "items" in runs_data
    assert isinstance(runs_data["items"], list)

    # 搜索接口容错测试
    res_search = client.post("/api/lingxi/search", json={"keywords": ""})
    assert res_search.status_code == 400

if __name__ == "__main__":
    test_lingxi_matrix_builder()
    test_lingxi_task_crud()
    test_lingxi_api_routes()
    print("All lingxi unit tests passed successfully!")
