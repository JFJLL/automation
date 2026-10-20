import json
from unittest.mock import MagicMock, patch

import pytest

from core.sync import execute_inplace_merge_sync


class _Task(dict):
    def keys(self):
        return super().keys()


def _make_db(task, sheets):
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    state = {"call": 0}

    cursor.fetchone.return_value = task
    cursor.fetchall.return_value = sheets
    cursor.lastrowid = 1
    return conn


@pytest.fixture
def base_task():
    return _Task(
        id=99,
        name="测试原地合并",
        platform="taobao",
        spreadsheet_token="tok",
        calendar=None,
        calibration_days=2,
        sub_account_id=None,
        sync_style="inplace",
    )


def test_inplace_merge_appends_without_overwriting_formula(base_task):
    headers = ["日期", "任务ID", "阅读/播放UV", "归属"]
    existing = [
        ["日期", "任务ID", "阅读/播放UV", "归属"],
        ["20261016", "123", "10", "10月包"],
        ["20261017", "123", "20", "10月包"],
    ]
    formulas = [
        ["日期", "任务ID", "阅读/播放UV", "归属"],
        ["20261016", "123", "10", '=IF(A2="","","10月包")'],
        ["20261017", "123", "20", '=IF(A3="","","10月包")'],
    ]
    sheet = _Task(
        id=1,
        sheet_title="测试表",
        worksheet_id="sid1",
        dimension="任务",
        id_column="任务ID",
        date_column="日期",
        header_json=json.dumps(headers, ensure_ascii=False),
        entity_ids_json=json.dumps(["123"], ensure_ascii=False),
        sheet_start_date="2026-10-01",
    )

    fake_feishu = MagicMock()
    fake_feishu.read_values.return_value = existing
    fake_feishu.read_values_formula.return_value = formulas
    fake_feishu.get_sheets.return_value = [{"sheet_id": "sid1", "grid_properties": {"row_count": 200}}]

    fetched = [
        {"日期": "2026-10-18", "任务ID": "123", "阅读/播放UV": 30},
        {"日期": "2026-10-17", "任务ID": "123", "阅读/播放UV": 25},
    ]

    with patch("core.sync.get_db", return_value=_make_db(base_task, [sheet])), \
         patch("core.sync.FeishuClient", return_value=fake_feishu), \
         patch("core.sync.Notifier", return_value=MagicMock()), \
         patch("core.sync.acquire_task_lease", return_value=True), \
         patch("core.sync.release_task_lease"), \
         patch("core.sync.fetch_taobao_data") as fetch_mock, \
         patch("core.sync.latest_sync_cutoff_date", return_value="2026-10-18"), \
         patch("core.sync.BACKUPS_DIR") as backups_dir:
        backups_dir.__truediv__ = lambda self, other: MagicMock(write_text=lambda *a, **k: None)
        fetch_mock.return_value = MagicMock(rows=fetched)
        result = execute_inplace_merge_sync(99, trigger_type="manual")

    assert result["status"] == "success"
    assert result["rows_appended"] == 1
    assert result["rows_updated"] == 1

    written_ranges = []
    for call in fake_feishu.batch_update_values.call_args_list:
        for entry in call.args[1]:
            written_ranges.append(entry["range"])

    # 新增 10-18 行写入第 4 行；更新 10-17 只改 C3
    assert "sid1!C3:C3" in written_ranges
    assert any(r.startswith("sid1!A4:A4") for r in written_ranges)
    # 已有行的归属列（D3）绝不能被写死值
    assert "sid1!D3:D3" not in written_ranges

    # 新增行的归属列（公式列）应写入上面的计算结果，不能写入公式本身
    d4_values = [
        entry["values"][0][0]
        for call in fake_feishu.batch_update_values.call_args_list
        for entry in call.args[1]
        if entry["range"] == "sid1!D4:D4"
    ]
    assert d4_values == ['10月包']


def test_inplace_merge_skips_sheet_when_api_empty(base_task):
    headers = ["日期", "任务ID", "阅读/播放UV"]
    existing = [
        ["日期", "任务ID", "阅读/播放UV"],
        ["20261017", "123", "20"],
    ]
    sheet = _Task(
        id=1,
        sheet_title="空数据表",
        worksheet_id="sid2",
        dimension="任务",
        id_column="任务ID",
        date_column="日期",
        header_json=json.dumps(headers, ensure_ascii=False),
        entity_ids_json=json.dumps(["123"], ensure_ascii=False),
        sheet_start_date="2026-10-01",
    )

    fake_feishu = MagicMock()
    fake_feishu.read_values.return_value = existing
    fake_feishu.read_values_formula.return_value = existing

    with patch("core.sync.get_db", return_value=_make_db(base_task, [sheet])), \
         patch("core.sync.FeishuClient", return_value=fake_feishu), \
         patch("core.sync.Notifier", return_value=MagicMock()), \
         patch("core.sync.acquire_task_lease", return_value=True), \
         patch("core.sync.release_task_lease"), \
         patch("core.sync.fetch_taobao_data", return_value=MagicMock(rows=[])) as fetch_mock, \
         patch("core.sync.latest_sync_cutoff_date", return_value="2026-10-18"):
        result = execute_inplace_merge_sync(99, trigger_type="scheduled")

    assert result["status"] == "success"
    assert result["rows_appended"] == 0
    assert result["rows_updated"] == 0
    fake_feishu.batch_update_values.assert_not_called()
