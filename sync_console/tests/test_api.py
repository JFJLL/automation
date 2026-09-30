import unittest
import io
import openpyxl
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.config import ACCESS_TOKEN

class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"X-Access-Token": ACCESS_TOKEN}

    def test_auth_flow(self):
        # 普通公开接口免鉴权
        r = self.client.get("/api/platforms", headers=self.headers)
        self.assertEqual(r.status_code, 200)

        # 未授权管理接口
        r = self.client.get("/api/settings")
        self.assertEqual(r.status_code, 401)

        # 密码登录
        r = self.client.post("/api/auth/login", json={"password": ACCESS_TOKEN})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

        # 校验成功访问管理接口 (Mock 飞书客户端避免外部请求)
        mock_feishu = MagicMock()
        mock_feishu.get_or_create_shared_folder.return_value = "mock_folder_token_123"
        with patch("app.main.FeishuClient", return_value=mock_feishu):
            r = self.client.get("/api/settings", headers=self.headers)
            self.assertEqual(r.status_code, 200)
            self.assertIn("shared_folder_token", r.json())

    def test_upload_and_preview_flow(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "测试9月数据"
        ws.append(["日期", "任务ID", "成交GMV", "下单UV"])
        ws.append(["2026-09-18", "198973", "1200", "25"])
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)

        files = {"file": ("test.xlsx", bio.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        data = {"selected_platform": "jzt"}
        r = self.client.post("/api/upload", files=files, data=data, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        res = r.json()
        self.assertEqual(len(res["sheets"]), 1)
        s = res["sheets"][0]
        self.assertEqual(s["sheet_title"], "测试9月数据")
        self.assertEqual(s["id_column"], "任务ID")
        self.assertEqual(s["detected_entity_ids"], ["198973"])

    def test_task_management_routes(self):
        r = self.client.get("/api/tasks", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

        r = self.client.get("/api/runs", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

if __name__ == "__main__":
    unittest.main()
