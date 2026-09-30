import io
import json
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
import requests

from platforms.jzt import fetch_jzt_data
from platforms.juguang import fetch_juguang_data
from platforms.taobao import fetch_taobao_data
from core.models import ProviderFetchStatus
from core.errors import ProviderAuthError, ProviderUpstreamError

def test_jzt_valid_excel():
    df = pd.DataFrame([{"日期": "2026-09-20", "任务ID": "12345", "成交GMV": 99.0}])
    bio = io.BytesIO()
    df.to_excel(bio, index=False)
    content = bio.getvalue()
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = content
    with patch("requests.Session.post", return_value=mock_resp):
        res = fetch_jzt_data("12345", "2026-09-20", "2026-09-21", cookie="pin=test;wskey=123")
        assert res.status == ProviderFetchStatus.SUCCESS
        assert len(res.rows) == 1
        assert res.rows[0]["成交GMV"] == 99.0

def test_jzt_empty_excel():
    df = pd.DataFrame(columns=["日期", "任务ID", "成交GMV"])
    bio = io.BytesIO()
    df.to_excel(bio, index=False)
    content = bio.getvalue()
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = content
    with patch("requests.Session.post", return_value=mock_resp):
        res = fetch_jzt_data("12345", "2026-09-20", "2026-09-21", cookie="pin=test;wskey=123")
        assert res.status == ProviderFetchStatus.EMPTY
        assert len(res.rows) == 0

def test_jzt_html_login_page_raises_auth_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"<html><head><title>Login</title></head><body>Please login</body></html>"
    mock_resp.text = "<html><head><title>Login</title></head><body>Please login</body></html>"
    with patch("requests.Session.post", return_value=mock_resp):
        with pytest.raises(ProviderAuthError) as exc_info:
            fetch_jzt_data("12345", "2026-09-20", "2026-09-21", cookie="pin=test;wskey=123")
        assert "登录" in str(exc_info.value) or "Cookie" in str(exc_info.value)

def test_jzt_http_500_raises_upstream_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    with patch("requests.Session.post", return_value=mock_resp):
        with pytest.raises(ProviderUpstreamError):
            fetch_jzt_data("12345", "2026-09-20", "2026-09-21", cookie="pin=test;wskey=123")

def test_juguang_success_rows():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "code": 0,
        "data": {
            "page": {"totalPage": 1},
            "dataList": [
                {
                    "dataValueJson": json.dumps({"time": "2026-09-20", "fee": 150.0, "impression": 2000}),
                    "placement": 1
                }
            ]
        }
    }
    with patch("requests.Session.post", return_value=mock_resp):
        res = fetch_juguang_data("eid", "account", "2026-09-20", "2026-09-21", headers_override={"cookie": "c"})
        assert res.status == ProviderFetchStatus.SUCCESS
        assert len(res.rows) == 1
        assert res.rows[0]["消费"] == 150.0

def test_juguang_api_failure_raises_upstream_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": False, "code": 50001, "msg": "系统繁忙"}
    with patch("requests.Session.post", return_value=mock_resp):
        with pytest.raises(ProviderUpstreamError) as exc_info:
            fetch_juguang_data("eid", "account", "2026-09-20", "2026-09-21", headers_override={"cookie": "c"})
        assert "系统繁忙" in str(exc_info.value)

def test_juguang_page_2_failure_does_not_return_partial():
    call_count = {"cnt": 0}
    def mock_post(*args, **kwargs):
        call_count["cnt"] += 1
        resp = MagicMock()
        resp.status_code = 200
        if call_count["cnt"] == 1:
            resp.json.return_value = {
                "success": True, "code": 0,
                "data": {"page": {"totalPage": 2}, "dataList": [{"dataValueJson": json.dumps({"time": "2026-09-20"})}]}
            }
        else:
            resp.json.return_value = {"success": False, "code": 500, "msg": "Page 2 crash"}
        return resp

    with patch("requests.Session.post", side_effect=mock_post):
        with pytest.raises(ProviderUpstreamError):
            fetch_juguang_data("eid", "account", "2026-09-20", "2026-09-21", headers_override={"cookie": "c"})

def test_taobao_nologin_raises_auth_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"info": {"message": "nologin"}, "success": False}
    with patch("requests.Session.get", return_value=mock_resp):
        with pytest.raises(ProviderAuthError):
            fetch_taobao_data("123", "内容", "2026-09-20", "2026-09-21", cookies={"adstar": "token"})

