"""Ordered in-place merge: date ascending, type fidelity, storage-style reuse."""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.database import get_db_connection, run_migrations
from core.models import ProviderFetchResult, ProviderFetchStatus
from core.sync import (
    coerce_numeric_value,
    column_numeric_kinds,
    detect_date_storage,
    format_date_for_storage,
    date_storage_kind,
    execute_inplace_ordered_sync,
)


def test_detect_date_storage_variants():
    assert detect_date_storage([["日期"], [46310], [46311]], 0) == "serial"
    assert detect_date_storage([["日期"], [20261007], [20261008]], 0) == "yyyymmdd_num"
    assert detect_date_storage([["日期"], ["20260912\t"], ["20260911"]], 0) == "yyyymmdd_text"
    assert detect_date_storage([["日期"], ["2026/10/15"]], 0) == "date_text_slash"
    assert detect_date_storage([["日期"], ["2026-10-15"]], 0) == "date_text_dash"
    # 无任何可识别日期时回落到真实日期序列号
    assert detect_date_storage([["日期"], [""]], 0) == "serial"


def test_date_storage_kind_ignores_plain_numbers():
    assert date_storage_kind(123) is None
    assert date_storage_kind("hello") is None
    assert date_storage_kind(20261007) == "yyyymmdd_num"


def test_format_date_for_storage_keeps_existing_style():
    assert format_date_for_storage("20261015", "serial") == 46310
    assert format_date_for_storage("20261015", "yyyymmdd_num") == 20261015
    assert format_date_for_storage("20261015", "yyyymmdd_text") == "20261015"
    assert format_date_for_storage("20261015", "date_text_slash") == "2026/10/15"
    assert format_date_for_storage("20261015", "date_text_dash") == "2026-10-15"


def test_column_numeric_kinds_picks_dominant_type():
    rows = [
        ["日期", "任务ID", "UV", "GMV"],
        [46310, "132897085", 364, 0],
        [46311, "132897085", "512", 12.5],
        [46312, "132897085", 18, 0],
    ]
    kinds = column_numeric_kinds(rows, ["日期", "任务ID", "UV", "GMV"], {0, 1})
    assert kinds[2] == "int"
    assert kinds[3] in ("int", "float")
    assert 0 not in kinds and 1 not in kinds


def test_coerce_numeric_value_never_leaves_text_numbers():
    assert coerce_numeric_value("30", "int") == 30
    assert coerce_numeric_value("31017.18", "float") == 31017.18
    assert coerce_numeric_value("abc", "int") == "abc"
    assert coerce_numeric_value("30", None) == "30"


def _setup_task(conn, sync_style="inplace_ordered"):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tasks (
            name, platform, folder_token, spreadsheet_token, spreadsheet_url,
            update_mode, calibration_days, rrule, status, created_at, updated_at, sync_style
        ) VALUES ('有序同步测试', 'taobao', 'fld', 'ss_token', 'https://example.com/ss',
                  'append', 2, 'RRULE:FREQ=DAILY;BYHOUR=9', 'active', '2026-10-01T00:00:00',
                  '2026-10-01T00:00:00', ?)
        """,
        (sync_style,),
    )
    task_id = cur.lastrowid
    headers = ["日期", "任务ID", "阅读/播放UV", "商家GMV"]
    cur.execute(
        """
        INSERT INTO task_sheets (
            task_id, sheet_title, worksheet_id, dimension, id_column, date_column,
            header_json, column_map_json, entity_ids_json, created_at, sheet_start_date
        ) VALUES (?, '竞品潜客', 'ws_1', '任务', '任务ID', '日期', ?, '{}', '["132897085"]',
                  '2026-10-01T00:00:00', '2026-09-23')
        """,
        (task_id, json.dumps(headers, ensure_ascii=False)),
    )
    conn.commit()
    return task_id, headers


def test_ordered_sync_sorts_ascending_and_keeps_numeric_types():
    tmp_dir = tempfile.mkdtemp()
    try:
        db_file = Path(tmp_dir) / "ordered.db"
        conn = get_db_connection(db_file)
        run_migrations(conn, module="sync")
        task_id, headers = _setup_task(conn)
        conn.close()

        # 现有表：日期倒序 + 最后一行指标是文本（复现线上问题）
        store = {
            "rows": [
                headers,
                [20261007, "132897085", 364, 2548],
                [20261006, "132897085", 2132, 149],
                [20261005, "132897085", "187", "271.9"],
            ]
        }

        mock_feishu = MagicMock()

        def fake_read(ss, ws, rng):
            return [list(r) for r in store["rows"]]

        def fake_write(ss, ws, start_row, rows):
            while len(store["rows"]) < start_row - 1:
                store["rows"].append([])
            for offset, row in enumerate(rows):
                idx = start_row - 1 + offset
                if idx < len(store["rows"]):
                    store["rows"][idx] = list(row)
                else:
                    store["rows"].append(list(row))

        mock_feishu.read_values.side_effect = fake_read
        mock_feishu.read_values_formula.side_effect = lambda *a, **k: [list(r) for r in store["rows"]]
        mock_feishu.write_rows.side_effect = fake_write
        mock_feishu.get_sheets.return_value = [
            {"sheet_id": "ws_1", "grid_properties": {"row_count": 200}}
        ]
        mock_feishu.find_last_row_index.side_effect = lambda ss, ws: len(store["rows"])
        mock_feishu.clear_rows_below.return_value = None
        mock_feishu.batch_update_values.return_value = None
        mock_feishu.set_number_format.return_value = {}

        fetched = [
            {"日期": "20261008", "任务ID": "132897085", "阅读/播放UV": 1355, "商家GMV": 1353.7},
        ]

        with patch("core.sync.FeishuClient", return_value=mock_feishu), \
             patch("core.sync.latest_sync_cutoff_date", return_value="2026-10-20"), \
             patch("core.sync.get_db", side_effect=lambda: get_db_connection(db_file)), \
             patch("core.sync.fetch_taobao_data", return_value=ProviderFetchResult(
                 status=ProviderFetchStatus.SUCCESS, rows=fetched, pages_fetched=1
             )), \
             patch("core.sync.Notifier"):
            result = execute_inplace_ordered_sync(task_id, trigger_type="manual")

        assert result["status"] == "success", result
        data = store["rows"][1:]
        # 日期升序
        assert [row[0] for row in data] == [20261005, 20261006, 20261007, 20261008]
        # 数字保持数字类型（原有文本行被纠正）
        assert isinstance(data[0][2], int), data[0]
        assert isinstance(data[0][3], float)
        # 新抓取行指标也是数字
        assert isinstance(data[-1][2], int)
        assert isinstance(data[-1][3], float)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_ordered_sync_reuses_text_date_storage_and_desc_values_are_sorted_asc():
    tmp_dir = tempfile.mkdtemp()
    try:
        db_file = Path(tmp_dir) / "ordered_text.db"
        conn = get_db_connection(db_file)
        run_migrations(conn, module="sync")
        task_id, headers = _setup_task(conn)
        conn.close()

        store = {
            "rows": [
                headers,
                ["20261007", "132897085", "364", "2548"],
                ["20261006", "132897085", "2132", "149"],
            ]
        }

        mock_feishu = MagicMock()
        mock_feishu.read_values.side_effect = lambda ss, ws, rng: [list(r) for r in store["rows"]]
        mock_feishu.read_values_formula.side_effect = lambda *a, **k: [list(r) for r in store["rows"]]

        def fake_write(ss, ws, start_row, rows):
            for offset, row in enumerate(rows):
                idx = start_row - 1 + offset
                if idx < len(store["rows"]):
                    store["rows"][idx] = list(row)
                else:
                    store["rows"].append(list(row))

        mock_feishu.write_rows.side_effect = fake_write
        mock_feishu.get_sheets.return_value = [
            {"sheet_id": "ws_1", "grid_properties": {"row_count": 200}}
        ]
        mock_feishu.find_last_row_index.side_effect = lambda ss, ws: len(store["rows"])
        mock_feishu.clear_rows_below.return_value = None
        mock_feishu.batch_update_values.return_value = None
        mock_feishu.set_number_format.return_value = {}

        fetched = [
            {"日期": "20261008", "任务ID": "132897085", "阅读/播放UV": 1355, "商家GMV": 1353.7},
        ]

        with patch("core.sync.FeishuClient", return_value=mock_feishu), \
             patch("core.sync.latest_sync_cutoff_date", return_value="2026-10-20"), \
             patch("core.sync.get_db", side_effect=lambda: get_db_connection(db_file)), \
             patch("core.sync.fetch_taobao_data", return_value=ProviderFetchResult(
                 status=ProviderFetchStatus.SUCCESS, rows=fetched, pages_fetched=1
             )), \
             patch("core.sync.Notifier"):
            result = execute_inplace_ordered_sync(task_id, trigger_type="manual")

        assert result["status"] == "success", result
        data = store["rows"][1:]
        # 日期沿用原文本存储风格，且升序
        assert [str(row[0]) for row in data] == ["20261006", "20261007", "20261008"]
        # 原本是文本数字的列，按多数列类型被纠正为数字
        assert isinstance(data[0][2], int)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
