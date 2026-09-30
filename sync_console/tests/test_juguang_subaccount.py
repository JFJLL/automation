import unittest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.config import ACCESS_TOKEN
from platforms.juguang import get_juguang_subaccounts_list, get_juguang_subaccount_headers, fetch_juguang_data
from core.errors import ProviderAuthError

class TestJuguangSubaccountFlow(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"X-Access-Token": ACCESS_TOKEN}

    def test_01_get_subaccounts_list(self):
        mock_subaccounts = [
            {"id": "629dd021b276e90001fc3b8c", "name": "测试子账号A", "status": 1},
            {"id": "628b3a5056228a000189c0e4", "name": "测试子账号B", "status": 1}
        ]
        with patch("app.main.get_juguang_subaccounts_list", return_value=mock_subaccounts):
            r = self.client.get("/api/platforms/juguang/subaccounts")
            self.assertEqual(r.status_code, 200)
            items = r.json()
            self.assertIsInstance(items, list)
            self.assertEqual(len(items), 2)
            first = items[0]
            self.assertEqual(first["id"], "629dd021b276e90001fc3b8c")
            self.assertEqual(first["name"], "测试子账号A")

    def test_02_get_subaccount_headers_mocked(self):
        sub_id = "629dd021b276e90001fc3b8c"
        with patch("platforms.juguang.fetch_oss_token", return_value="a1=test_cookie_123"):
            hdrs = get_juguang_subaccount_headers(sub_id)
            self.assertEqual(hdrs["v-seller-id"], sub_id)
            self.assertIn("a1=", hdrs["cookie"])
            self.assertEqual(hdrs["origin"], "https://ad.xiaohongshu.com")

    def test_03_fetch_juguang_data_with_subaccount_mocked(self):
        sub_id = "629dd021b276e90001fc3b8c"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "code": 0,
            "data": {
                "page": {"totalPage": 1},
                "dataList": [
                    {
                        "dataValueJson": json.dumps({"time": "2026-09-20", "fee": 120.0}),
                        "placement": 1
                    }
                ]
            }
        }
        with patch("platforms.juguang.fetch_oss_token", return_value="a1=cookie"):
            with patch("requests.Session.post", return_value=mock_resp):
                res = fetch_juguang_data(
                    entity_id="test_account",
                    split_type="account",
                    start_date="2026-09-20",
                    end_date="2026-09-27",
                    sub_account_id=sub_id
                )
                self.assertEqual(len(res.rows), 1)
                self.assertEqual(res.rows[0]["时间"], "2026-09-20")
                self.assertEqual(res.rows[0]["消费"], 120.0)

    def test_05_invalid_subaccount_error_handling(self):
        with patch("platforms.juguang.fetch_oss_token", side_effect=Exception("Not found")):
            with self.assertRaises((RuntimeError, ProviderAuthError)):
                get_juguang_subaccount_headers("non_existent_subaccount_id_999")

if __name__ == "__main__":
    unittest.main()
