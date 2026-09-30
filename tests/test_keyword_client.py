import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from keyword_service.client import (
    KeywordFetchStatus,
    KeywordUpstreamError,
    _fetch_single_word,
    fetch_keywords_insight,
)

FAKE_TOKEN = {
    "cookie": "test_cookie=1",
    "v_seller_id": "test_seller_id"
}

def test_single_word_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": 0,
        "success": True,
        "data": {
            "dataList": [
                {
                    "dataValueJson": json.dumps({
                        "detailDay": "2026-09-28",
                        "keywordSearchNum": 120,
                        "keywordAdsImpNum": 300,
                        "adsNoteNum": 15,
                        "keywordBid": 2.5
                    })
                }
            ]
        }
    }
    with patch("requests.post", return_value=mock_resp):
        res = _fetch_single_word("户外登山", "2026-09-20", "2026-09-28", FAKE_TOKEN, ["2026-09-28"])
        assert res.status == KeywordFetchStatus.SUCCESS
        assert "2026-09-28" in res.data
        assert res.data["2026-09-28"]["search_num"] == 120
        assert res.data["2026-09-28"]["bid"] == 2.5

def test_single_word_empty():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": 0,
        "success": True,
        "data": {
            "dataList": []
        }
    }
    with patch("requests.post", return_value=mock_resp):
        res = _fetch_single_word("冷门冷门词", "2026-09-20", "2026-09-28", FAKE_TOKEN, ["2026-09-28"])
        assert res.status == KeywordFetchStatus.EMPTY
        assert res.data == {}

def test_single_word_401():
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    with patch("requests.post", return_value=mock_resp):
        res = _fetch_single_word("词1", "2026-09-20", "2026-09-28", FAKE_TOKEN, ["2026-09-28"])
        assert res.status == KeywordFetchStatus.AUTH_ERROR

def test_single_word_902_code():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": 902, "success": False, "msg": "用户未登录"}
    with patch("requests.post", return_value=mock_resp):
        res = _fetch_single_word("词1", "2026-09-20", "2026-09-28", FAKE_TOKEN, ["2026-09-28"])
        assert res.status == KeywordFetchStatus.AUTH_ERROR

def test_single_word_500():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    with patch("requests.post", return_value=mock_resp):
        res = _fetch_single_word("词1", "2026-09-20", "2026-09-28", FAKE_TOKEN, ["2026-09-28"])
        assert res.status == KeywordFetchStatus.UPSTREAM_ERROR

def test_single_word_timeout():
    with patch("requests.post", side_effect=requests.Timeout("Connection timeout")):
        res = _fetch_single_word("词1", "2026-09-20", "2026-09-28", FAKE_TOKEN, ["2026-09-28"])
        assert res.status == KeywordFetchStatus.TIMEOUT

def test_single_word_invalid_json():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = json.JSONDecodeError("Invalid JSON", "<html>", 0)
    with patch("requests.post", return_value=mock_resp):
        res = _fetch_single_word("词1", "2026-09-20", "2026-09-28", FAKE_TOKEN, ["2026-09-28"])
        assert res.status == KeywordFetchStatus.INVALID_RESPONSE

def test_partial_success_never_fills_zeros_for_failed():
    def mock_post(url, *args, **kwargs):
        body = kwargs.get("json", {})
        word = body["filters"][0]["values"][0]
        resp = MagicMock()
        if word == "成功词":
            resp.status_code = 200
            resp.json.return_value = {
                "code": 0, "success": True,
                "data": {"dataList": [{"dataValueJson": json.dumps({"detailDay": "2026-09-25", "keywordSearchNum": 88})}]}
            }
        elif word == "空词":
            resp.status_code = 200
            resp.json.return_value = {"code": 0, "success": True, "data": {"dataList": []}}
        else:
            resp.status_code = 500
        return resp

    with patch("keyword_service.client.load_token", return_value=FAKE_TOKEN):
        with patch("requests.post", side_effect=mock_post):
            res = fetch_keywords_insight(
                ["成功词", "空词", "失败词"],
                start_date="2026-09-25",
                end_date="2026-09-26",
                strict=False
            )
            assert res["overall_status"] == "partial"
            assert "成功词" in res["successful_keywords"]
            assert "空词" in res["empty_keywords"]
            assert "失败词" in res["failed_keywords"]

            # 核心保证：失败词的 data 绝不是全 0 字典，而是 None
            assert res["data"]["失败词"] is None
            assert res["data"]["成功词"]["2026-09-25"]["search_num"] == 88
            assert res["data"]["空词"]["2026-09-25"]["search_num"] == 0

def test_strict_mode_rejects_partial_failure():
    def mock_post(url, *args, **kwargs):
        body = kwargs.get("json", {})
        word = body["filters"][0]["values"][0]
        resp = MagicMock()
        if word == "成功词":
            resp.status_code = 200
            resp.json.return_value = {"code": 0, "success": True, "data": {"dataList": []}}
        else:
            resp.status_code = 500
        return resp

    with patch("keyword_service.client.load_token", return_value=FAKE_TOKEN):
        with patch("requests.post", side_effect=mock_post):
            with pytest.raises(KeywordUpstreamError) as exc_info:
                fetch_keywords_insight(
                    ["成功词", "失败词"],
                    start_date="2026-09-25",
                    end_date="2026-09-26",
                    strict=True
                )
            assert "终止写入飞书" in str(exc_info.value)

def test_auth_retry_flow():
    attempt = {"count": 0}
    def mock_post(url, *args, **kwargs):
        attempt["count"] += 1
        resp = MagicMock()
        if attempt["count"] == 1:
            resp.status_code = 401
        else:
            resp.status_code = 200
            resp.json.return_value = {"code": 0, "success": True, "data": {"dataList": []}}
        return resp

    with patch("keyword_service.client.load_token", return_value=FAKE_TOKEN):
        with patch("keyword_service.client.sync_token_from_oss", return_value={"cookie": "refreshed=1", "v_seller_id": "test"}):
            with patch("requests.post", side_effect=mock_post):
                res = fetch_keywords_insight(["词1"], start_date="2026-09-25", end_date="2026-09-26")
                assert res["overall_status"] == "success"
                assert attempt["count"] == 2
