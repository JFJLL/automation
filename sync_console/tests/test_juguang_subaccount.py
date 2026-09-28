import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.config import ACCESS_TOKEN
from platforms.juguang import get_juguang_subaccounts_list, get_juguang_subaccount_headers, fetch_juguang_data
from app.db import get_db

class TestJuguangSubaccountFlow(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"X-Access-Token": ACCESS_TOKEN}

    def test_01_get_subaccounts_list(self):
        r = self.client.get("/api/platforms/juguang/subaccounts")
        self.assertEqual(r.status_code, 200)
        items = r.json()
        self.assertIsInstance(items, list)
        self.assertGreaterEqual(len(items), 300)
        first = items[0]
        self.assertIn("id", first)
        self.assertIn("name", first)
        self.assertTrue(len(first["id"]) == 24)

    def test_02_get_subaccount_headers_from_oss(self):
        sub_id = "628b3a5056228a000189c0e4"
        hdrs = get_juguang_subaccount_headers(sub_id)
        self.assertEqual(hdrs["v-seller-id"], sub_id)
        self.assertIn("a1=", hdrs["cookie"])
        self.assertEqual(hdrs["origin"], "https://ad.xiaohongshu.com")

    def test_03_fetch_juguang_data_with_subaccount(self):
        sub_id = "628b3a5056228a000189c0e4"
        rows = fetch_juguang_data(
            entity_id="test_account",
            split_type="account",
            start_date="2026-09-20",
            end_date="2026-09-27",
            sub_account_id=sub_id
        )
        self.assertIsInstance(rows, list)
        if rows:
            self.assertIn("时间", rows[0])
            self.assertIn("消费", rows[0])

    def test_04_preview_api_with_subaccount(self):
        sub_id = "628b3a5056228a000189c0e4"
        payload = {
            "platform": "juguang",
            "sheet_title": "测试聚光",
            "headers": ["时间", "投放位置", "消费", "展现量", "点击量"],
            "entity_ids": ["test_account"],
            "id_column": "时间",
            "date_column": "时间",
            "dimension": "account",
            "start_date": "2026-09-20",
            "end_date": "2026-09-27",
            "sub_account_id": sub_id
        }
        r = self.client.post("/api/preview", json=payload)
        self.assertEqual(r.status_code, 200)
        res = r.json()
        self.assertIn("rows", res)
        self.assertIn("total_fetched", res)

    def test_05_invalid_subaccount_error_handling(self):
        with self.assertRaises(RuntimeError):
            get_juguang_subaccount_headers("non_existent_subaccount_id_999")

if __name__ == "__main__":
    unittest.main()
