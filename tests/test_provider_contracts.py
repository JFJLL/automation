import io
import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from core.errors import ProviderAuthError, ProviderUpstreamError
from core.models import ProviderFetchStatus
from platforms.juguang import fetch_juguang_data
from platforms.jzt import fetch_jzt_data
from platforms.taobao import fetch_taobao_data


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


def test_jzt_30_day_window_restriction():
    # 超过 30 天回溯明确报错
    with pytest.raises(ProviderUpstreamError) as exc_info:
        fetch_jzt_data("12345", "2026-01-01", "2026-09-30", cookie="pin=test")
    assert "30 天" in str(exc_info.value)

def test_taobao_partial_on_max_pages():
    def mock_get(url, params, **kwargs):
        p = params.get("pageNo", 1)
        resp = MagicMock()
        resp.status_code = 200
        # 每页 100 条且包含当前页标识以避免被判定为重复页
        items = [{"theDate": "2026-09-20", "readUv1d": 100, "detailUrl": f"http://test.com/{p}/{i}"} for i in range(100)]
        resp.json.return_value = {
            "success": True,
            "model": {
                "list": items,
                "hasNext": True,
                "total": 50000
            }
        }
        return resp

    with patch("requests.Session.get", side_effect=mock_get), patch("time.sleep"):
        res = fetch_taobao_data("12345", "内容", "2026-09-20", "2026-09-20", cookies={"_tb_token_": "test"})
        assert res.status == ProviderFetchStatus.PARTIAL
        assert res.pages_fetched == 100

def test_excel_upload_limits_and_zip_bomb():
    import zipfile

    from core.ingest import check_zip_bomb, parse_excel_sheets
    from fastapi import HTTPException

    # 1. 超过 10MB 拒绝
    with pytest.raises(HTTPException) as exc:
        parse_excel_sheets(b"0" * (11 * 1024 * 1024), "large.xlsx")
    assert exc.value.status_code == 400

    # 2. 不支持的扩展名拒绝
    with pytest.raises(HTTPException) as exc:
        parse_excel_sheets(b"data", "script.exe")
    assert exc.value.status_code == 400

    # 3. 构造 ZipBomb 拒绝 (高压缩比)
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("huge.txt", "A" * (1024 * 1024))
    compressed = bio.getvalue()
    # 压缩比检查直接生效
    with pytest.raises(HTTPException):
        check_zip_bomb(compressed)

def test_webhook_domain_whitelist():
    from feishu.notify import Notifier
    notifier = Notifier()
    # 非法域名被拦截
    ok = notifier.send_webhook_message("https://evil-attacker.com/webhook", "test alert")
    assert ok is False

def test_formula_injection_sanitization():
    from core.feishu_matrix import sanitize_formula_injection
    assert sanitize_formula_injection("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert sanitize_formula_injection("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_formula_injection("-200") == "'-200"
    assert sanitize_formula_injection("@secret") == "'@secret"
    assert sanitize_formula_injection("normal_text") == "normal_text"
