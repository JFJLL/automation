import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.database import get_db_connection, run_migrations
from core.models import ProviderFetchResult, ProviderFetchStatus
from core.errors import ProviderUpstreamError, FeishuWriteError
from core.sync import execute_task_sync

def setup_test_task(conn, update_mode="append"):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tasks (
            name, platform, folder_token, spreadsheet_token, spreadsheet_url,
            update_mode, calibration_days, rrule, status, created_at, updated_at
        ) VALUES ('测试同步任务', 'jzt', 'fld_1', 'ss_token_123', 'https://example.com/ss', ?, 2, 'RRULE:FREQ=DAILY;BYHOUR=9', 'active', '2026-09-01T00:00:00', '2026-09-01T00:00:00')
    """, (update_mode,))
    task_id = cur.lastrowid
    
    headers = ["日期", "任务ID", "成交GMV"]
    cur.execute("""
        INSERT INTO task_sheets (
            task_id, sheet_title, worksheet_id, dimension, id_column, date_column,
            header_json, column_map_json, entity_ids_json, created_at
        ) VALUES (?, '每日数据', 'ws_sheet_1', '', '任务ID', '日期', ?, '{}', '["198973"]', '2026-09-01T00:00:00')
    """, (task_id, json.dumps(headers, ensure_ascii=False)))
    conn.commit()
    return task_id

def test_append_mode_idempotent_no_duplicate_rows():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_sync.db"
        conn = get_db_connection(db_file)
        run_migrations(conn, module="sync")
        task_id = setup_test_task(conn, update_mode="append")
        
        # 模拟工作体现有行：表头 + 1 行历史数据
        feishu_store = {
            "rows": [
                ["日期", "任务ID", "成交GMV"],
                ["2026-09-20", "198973", "100.0"]
            ]
        }
        
        mock_feishu = MagicMock()
        def mock_read(ss, ws, rng):
            return [list(r) for r in feishu_store["rows"]]
        def mock_write(ss, ws, start_row, rows):
            # 将写入同步到 feishu_store
            while len(feishu_store["rows"]) < start_row - 1:
                feishu_store["rows"].append(["", "", ""])
            for offset, r in enumerate(rows):
                idx = (start_row - 1) + offset
                if idx < len(feishu_store["rows"]):
                    feishu_store["rows"][idx] = list(r)
                else:
                    feishu_store["rows"].append(list(r))
                    
        def mock_find_last(ss, ws):
            return len(feishu_store["rows"])
            
        mock_feishu.read_values.side_effect = mock_read
        mock_feishu.write_rows.side_effect = mock_write
        mock_feishu.find_last_row_index.side_effect = mock_find_last
        
        mock_provider_result = ProviderFetchResult(
            status=ProviderFetchStatus.SUCCESS,
            rows=[
                {"日期": "2026-09-20", "任务ID": "198973", "成交GMV": "150.0"}, # 已存在的同 key 数据 (进行 upsert 更新)
                {"日期": "2026-09-21", "任务ID": "198973", "成交GMV": "200.0"}  # 新的一天数据 (append)
            ]
        )
        
        with patch("core.sync.get_db", return_value=conn),              patch("core.sync.FeishuClient", return_value=mock_feishu),              patch("core.sync.Notifier"),              patch("core.sync.fetch_jzt_data", return_value=mock_provider_result):
            
            # 第一次同步执行
            res1 = execute_task_sync(task_id, trigger_type="manual")
            assert res1["status"] == "success"
            assert res1["rows_updated"] == 1
            assert res1["rows_appended"] == 1
            # 现在表内行数应为 1 (表头) + 2 (数据行) = 3
            assert len(feishu_store["rows"]) == 3
            assert feishu_store["rows"][1] == ["2026-09-20", "198973", "150.0"]
            assert feishu_store["rows"][2] == ["2026-09-21", "198973", "200.0"]
            
            # 第二次执行完全相同的抓取 (幂等性测试：绝不追加重复行！)
            res2 = execute_task_sync(task_id, trigger_type="manual")
            assert res2["status"] == "success"
            assert res2["rows_updated"] == 2 # 两次均在 key map 中命中，做原地更新
            assert res2["rows_appended"] == 0 # 没有新 key，追加行数为 0！
            assert len(feishu_store["rows"]) == 3, "重复运行同一任务绝对不能产生重复数据行！"
        conn.close()

def test_phase1_fetch_failure_aborts_before_writing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_sync.db"
        conn = get_db_connection(db_file)
        run_migrations(conn, module="sync")
        task_id = setup_test_task(conn, update_mode="overwrite")
        
        initial_sheet_content = [
            ["日期", "任务ID", "成交GMV"],
            ["2026-09-20", "198973", "5000.0"]
        ]
        mock_feishu = MagicMock()
        mock_feishu.read_values.return_value = list(initial_sheet_content)
        
        with patch("core.sync.get_db", return_value=conn),              patch("core.sync.FeishuClient", return_value=mock_feishu),              patch("core.sync.Notifier"),              patch("core.sync.fetch_jzt_data", side_effect=ProviderUpstreamError("JD API 500 error")):
            
            with pytest.raises(ProviderUpstreamError):
                execute_task_sync(task_id, trigger_type="manual")
                
            # 关键断言：Phase 1 抓取失败时，Phase 2 清表和写表绝对没有被调用！
            mock_feishu.clear_rows_below.assert_not_called()
            mock_feishu.write_rows.assert_not_called()
            
            # 运行记录记录 failed
            cur = conn.cursor()
            cur.execute("SELECT status, message FROM runs WHERE task_id = ?", (task_id,))
            run = cur.fetchone()
            assert run["status"] == "failed"
            assert "中止写表" in run["message"]
        conn.close()

