import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent / "feishu_three_sync"
sys.path.insert(0, str(ROOT / "jg_sync"))
sys.path.insert(0, str(ROOT / "taobao"))

from daily import format_date
from taobaoxinghe_feishu_order_effect import cutoff_time_range, row_match_key
from taobaoxinghe_scraper import ApiError, TaobaoXingheScraperV5


def test_jg_format_date_zero_padded():
    d = date(2026, 9, 5)
    res = format_date(d)
    assert res == "2026/09/05"
    assert res != "2026/9/5"

def test_taobao_cutoff_time_range_not_zero_duration():
    res = cutoff_time_range("2026-09-30")
    assert res["startTime"] == "2026-09-30 00:00:00"
    assert res["endTime"] == "2026-09-30 23:59:59"
    assert res["startTime"] != res["endTime"]

def test_taobao_row_match_key_contains_order_id():
    row1 = {"任务组名称": "组A", "日期": "2026-09-30", "流量类型": "全部", "归因周期": "15天", "订单ID": "order_100"}
    row2 = {"任务组名称": "组A", "日期": "2026-09-30", "流量类型": "全部", "归因周期": "15天", "订单ID": "order_200"}

    k1 = row_match_key(row1)
    k2 = row_match_key(row2)
    assert k1 != k2
    assert "order_100" in k1
    assert "order_200" in k2

def test_taobao_scraper_get_json_raises_on_success_false():
    scraper = TaobaoXingheScraperV5(cookies={"_tb_token_": "mock"})
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": False, "message": "API permission denied"}

    with patch.object(scraper.session, "get", return_value=mock_resp):
        with pytest.raises(ApiError):
            scraper.get_json("/test/path", {})
