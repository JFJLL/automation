
from app.config import ACCESS_TOKEN
from fastapi.testclient import TestClient

from lingxi_service.db import init_db
from lingxi_service.sync_engine import (
    append_keywords_to_lingxi_task,
    build_lingxi_date_matrix,
    create_lingxi_task,
    remove_keywords_from_lingxi_task,
)
from sync_console.app.main import app

client = TestClient(app)

def test_lingxi_matrix_builder():
    keywords = ["奶粉", "纸尿裤"]
    data = {
        "奶粉": {"user_cnt": 12000},
        "纸尿裤": {"user_cnt": 8500}
    }
    time_str = "2026-09-30"
    matrix = build_lingxi_date_matrix(keywords, [time_str], time_str, data, {})
    assert len(matrix) == 3
    assert matrix[0] == ["关键词", time_str]
    assert matrix[1] == ["奶粉", 12000]
    assert matrix[2] == ["纸尿裤", 8500]

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
    res = client.get("/api/lingxi/tasks", headers={"X-Access-Token": ACCESS_TOKEN})
    assert res.status_code == 200
    tasks = res.json()
    assert isinstance(tasks, list)

    res_runs = client.get("/api/lingxi/runs", headers={"X-Access-Token": ACCESS_TOKEN})
    assert res_runs.status_code == 200
    runs_data = res_runs.json()
    assert "items" in runs_data
    assert isinstance(runs_data["items"], list)

    # 搜索接口容错测试
    res_search = client.post("/api/lingxi/search", json={"keywords": ""}, headers={"X-Access-Token": ACCESS_TOKEN})
    assert res_search.status_code == 400

if __name__ == "__main__":
    test_lingxi_matrix_builder()
    test_lingxi_task_crud()
    test_lingxi_api_routes()
    print("All lingxi unit tests passed successfully!")
