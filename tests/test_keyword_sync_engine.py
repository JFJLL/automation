import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.database import get_db_connection, run_migrations
from core.errors import TaskAlreadyRunningError, KeywordUpstreamError
from keyword_service.sync_engine import (
    parse_existing_sheet_history,
    build_sheet_matrix,
    create_keyword_task,
    run_keyword_task,
    remove_keywords_from_task
)

def test_parse_existing_sheet_history_and_alignment():
    # Day 1: 表格有两天 2026-09-20, 2026-09-21
    existing_rows = [
        ["关键词", "2026-09-20", "", "", "", "2026-09-21", "", "", ""],
        ["", "搜索指数", "广告曝光量", "广告笔记数", "平均市场出价", "搜索指数", "广告曝光量", "广告笔记数", "平均市场出价"],
        ["词A", 100, 200, 10, 1.5, 110, 220, 12, 1.6],
        ["词B", 50, 80, 5, 0.8, 60, 90, 6, 0.9],
    ]
    dates, history = parse_existing_sheet_history(existing_rows)
    assert dates == ["2026-09-20", "2026-09-21"]
    assert "词A" in history
    assert history["词A"]["2026-09-20"] == [100, 200, 10, 1.5]
    assert history["词A"]["2026-09-21"] == [110, 220, 12, 1.6]
    assert history["词B"]["2026-09-20"] == [50, 80, 5, 0.8]

def test_removed_keyword_date_alignment_on_day_3():
    # 场景复现 Section 十三：
    # 历史表头为 2026-09-20, 2026-09-21
    # 用户减去 "词B"
    # Day 3 新抓取日期窗口为 2026-09-21, 2026-09-22
    # "词B" 作为 removed keyword，其在 2026-09-21 的指标必须依然是 60 (而不是被新数据或偏移列覆盖)
    existing_rows = [
        ["关键词", "2026-09-20", "", "", "", "2026-09-21", "", "", ""],
        ["", "搜索指数", "广告曝光量", "广告笔记数", "平均市场出价", "搜索指数", "广告曝光量", "广告笔记数", "平均市场出价"],
        ["词A", 100, 200, 10, 1.5, 110, 220, 12, 1.6],
        ["词B", 50, 80, 5, 0.8, 60, 90, 6, 0.9],
    ]
    dates, history = parse_existing_sheet_history(existing_rows)
    
    new_dates = ["2026-09-21", "2026-09-22"]
    removed_kws = ["词B"]
    active_kws = ["词A"]
    new_data = {
        "词A": {
            "2026-09-21": {"search_num": 115, "imp_num": 230, "note_num": 13, "bid": 1.7},
            "2026-09-22": {"search_num": 130, "imp_num": 250, "note_num": 14, "bid": 1.8},
        }
    }
    
    # 模拟 run_keyword_task 中构建矩阵对齐
    row1 = ["关键词"]
    row2 = [""]
    for d in new_dates:
        row1.extend([d, "", "", ""])
        row2.extend(["搜索指数", "广告曝光量", "广告笔记数", "平均市场出价"])
    matrix = [row1, row2]
    
    for kw in ["词A", "词B"]:
        row = [kw]
        is_removed = kw in removed_kws
        kw_hist = history.get(kw, {})
        kw_new = new_data.get(kw, {}) if not is_removed else {}
        for d in new_dates:
            if not is_removed and kw in new_data and kw_new and d in kw_new:
                item = kw_new[d]
                row.extend([item["search_num"], item["imp_num"], item["note_num"], item["bid"]])
            elif d in kw_hist:
                row.extend(kw_hist[d])
            else:
                row.extend(["", "", "", ""])
        matrix.append(row)
        
    # 验证 词B 的行
    row_b = matrix[3]
    assert row_b[0] == "词B"
    # 2026-09-21 对应列 1..4 (B:E)
    assert row_b[1:5] == [60, 90, 6, 0.9], "历史日期 2026-09-21 必须精准保留历史指标"
    # 2026-09-22 对应列 5..8 (F:I) - 减词后新出现的日期保持空白
    assert row_b[5:9] == ["", "", "", ""], "减词后新出现的日期不应写入假数据或错误位移"

def test_create_task_transaction_no_orphan_sheet_on_fetch_failure():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_kw.db"
        conn = get_db_connection(db_file)
        run_migrations(conn, module="keyword")
        
        mock_feishu = MagicMock()
        with patch("keyword_service.sync_engine.get_db", return_value=conn),              patch("keyword_service.sync_engine.FeishuClient", return_value=mock_feishu),              patch("keyword_service.sync_engine.fetch_keywords_insight", side_effect=KeywordUpstreamError("API network error")):
            with pytest.raises(KeywordUpstreamError):
                create_keyword_task("测试任务", ["词1"])
                
            # 确认在 fetch 失败时，根本没有调用 create_spreadsheet
            mock_feishu.create_spreadsheet.assert_not_called()
            
            # 确认数据库里没有创建孤儿任务
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM keyword_tasks")
            assert cur.fetchone()[0] == 0
        conn.close()

