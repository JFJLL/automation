from unittest.mock import MagicMock

from feishu.client import FeishuClient, column_letter


def test_column_letter():
    assert column_letter(1) == "A"
    assert column_letter(26) == "Z"
    assert column_letter(27) == "AA"
    assert column_letter(28) == "AB"
    assert column_letter(52) == "AZ"
    assert column_letter(53) == "BA"

def test_feishu_429_retry_after():
    client = FeishuClient(app_id="mock_id", app_secret="mock_secret")
    client.get_token = MagicMock(return_value="mock_token")

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"Retry-After": "0.01"}

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.json.return_value = {"code": 0, "data": {"result": "ok"}}

    client.session.request = MagicMock(side_effect=[resp_429, resp_ok])

    res = client.request("GET", "test/path")
    assert res == {"result": "ok"}
    assert client.session.request.call_count == 2

def test_feishu_90217_rate_limit_code_retry():
    client = FeishuClient(app_id="mock_id", app_secret="mock_secret")
    client.get_token = MagicMock(return_value="mock_token")

    resp_90217 = MagicMock()
    resp_90217.status_code = 200
    resp_90217.json.return_value = {"code": 90217, "msg": "frequency limit"}

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.json.return_value = {"code": 0, "data": {"sheets": [{"sheet_id": "0"}]}}

    client.session.request = MagicMock(side_effect=[resp_90217, resp_ok])
    res = client.request("GET", "sheets/v3/test")
    assert res == {"sheets": [{"sheet_id": "0"}]}
    assert client.session.request.call_count == 2

def test_wide_table_beyond_az_range():
    # 模拟超过 26 列的宽表 (30 列)
    col_count = 30
    end_col = column_letter(col_count)
    assert end_col == "AD"
