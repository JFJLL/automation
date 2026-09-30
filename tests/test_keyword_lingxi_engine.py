from unittest.mock import MagicMock

import pytest
from app.config import ACCESS_TOKEN
from app.main import app
from core.feishu_matrix import write_matrix_to_sheet
from fastapi.testclient import TestClient

from lingxi_service.sync_engine import build_lingxi_date_matrix


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_failed_keyword_never_written_as_zero():
    # 验证当词失败时，matrix builder 绝不将缺失数据写入为 0
    keywords = ["成功词", "失败词"]
    new_data = {
        "成功词": {"user_cnt": 5000}
        # 失败词不在 new_data 中
    }
    old_history = {}
    target_dates = ["2026-09-30"]

    matrix = build_lingxi_date_matrix(
        keywords=keywords,
        target_dates=target_dates,
        new_date="2026-09-30",
        new_data=new_data,
        old_history=old_history
    )
    # 成功词有真实数据
    assert matrix[1] == ["成功词", 5000]

def test_pagination_page_size_zero_returns_422(client):
    r_kw = client.get("/api/keyword/runs?page_size=0", headers={"X-Access-Token": ACCESS_TOKEN})
    assert r_kw.status_code == 422

    r_lx = client.get("/api/lingxi/runs?page_size=0", headers={"X-Access-Token": ACCESS_TOKEN})
    assert r_lx.status_code == 422

def test_empty_sheet_no_index_error():
    mock_feishu = MagicMock()
    mock_feishu.get_sheets.return_value = []
    with pytest.raises(Exception) as exc_info:
        write_matrix_to_sheet(mock_feishu, "ss_token", "sheet_0", [["关键词", "2026-09-30"], ["测试", 100]])
    assert "has no sheets" in str(exc_info.value)
