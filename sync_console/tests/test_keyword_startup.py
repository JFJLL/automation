import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.config import ACCESS_TOKEN
from keyword_service.db import get_db, init_db
from keyword_service.router import app as standalone_app
from keyword_service.scheduler import kw_scheduler


class TestKeywordStartup(unittest.TestCase):
    def test_combined_app_restores_active_keyword_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            console_db = Path(directory) / "console.db"
            keyword_db = Path(directory) / "keyword.db"
            with patch("app.db.DB_PATH", console_db), patch("keyword_service.db.DB_PATH", keyword_db):
                init_db()
                now = datetime.now().isoformat()
                with closing(get_db()) as conn:
                    cursor = conn.execute(
                        "INSERT INTO keyword_tasks (name, keywords_json, spreadsheet_token, spreadsheet_url, rrule, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ("startup test", '["test"]', "test", "https://example.com", "FREQ=DAILY;BYHOUR=12;BYMINUTE=30", now, now),
                    )
                    task_id = cursor.lastrowid
                    conn.commit()
                try:
                    with TestClient(app) as client:
                        self.assertEqual(client.get("/keyword").status_code, 200)
                        self.assertEqual(client.get("/api/keyword/tasks", headers={"X-Access-Token": ACCESS_TOKEN}).status_code, 200)
                        self.assertTrue(kw_scheduler.running)
                        self.assertIsNotNone(kw_scheduler.get_job(f"kw_task_{task_id}"))
                        with closing(get_db()) as conn:
                            next_run = conn.execute("SELECT next_run_at FROM keyword_tasks WHERE id = ?", (task_id,)).fetchone()[0]
                        self.assertIsNotNone(next_run)
                    standalone_client = TestClient(standalone_app)
                    self.assertEqual(standalone_client.get("/api/keyword/tasks").status_code, 200)
                finally:
                    if kw_scheduler.running:
                        kw_scheduler.remove_all_jobs()
                        kw_scheduler.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
