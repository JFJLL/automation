import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.database import get_db_connection, run_migrations
from core.models import ProviderFetchResult, ProviderFetchStatus
from core.sync import execute_inplace_ordered_sync


def test_task_20_jugaoxing_yellow_formula_column_strictly_not_updated():
    tmp_dir = tempfile.mkdtemp()
    try:
        db_file = Path(tmp_dir) / 'task20_guard.db'
        conn = get_db_connection(db_file)
        run_migrations(conn, module='sync')
        headers = ['日期', '任务ID', '流量类型', '归因口径']
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO tasks (
                id, name, platform, folder_token, spreadsheet_token, spreadsheet_url,
                update_mode, calibration_days, rrule, status, created_at, updated_at, sync_style
            ) VALUES (
                20, '淘宝星河-信息表全量同步', 'taobao', 'fld', 'mock_ss_token', 'https://example.com/ss',
                'append', 2, 'RRULE:FREQ=DAILY;BYHOUR=9', 'active', '2026-10-01T00:00:00',
                '2026-10-01T00:00:00', 'inplace_ordered'
            )'''
        )
        cur.execute(
            '''INSERT INTO task_sheets (
                task_id, sheet_title, worksheet_id, dimension, id_column, date_column,
                header_json, column_map_json, entity_ids_json, created_at, sheet_start_date
            ) VALUES (
                20, '电商-9-10月-聚高星-小红星-品类新客', 'zdctqN', '任务', '任务ID', '日期',
                ?, '{}', '[ 132897081]', '2026-10-01T00:00:00', '2026-09-23'
            )''',
            (json.dumps(headers, ensure_ascii=False),)
        )
        conn.commit()
        conn.close()

        sheet_headers = list(headers) + ['归属']
        existing_row = ['20261015', '132897081', '全部流量', '30', '=IF(A2=",",品类新客)']
        existing_formula = ['', '', '', '', '=IF(A2=",",品类新客)']

        batch_updates = []
        written_rows = []
        mock_feishu = MagicMock()
        mock_feishu.read_values.side_effect = lambda ss, ws, rng: [sheet_headers, existing_row]
        mock_feishu.read_values_formula.side_effect = lambda ss, ws, rng: [sheet_headers, existing_formula]
        mock_feishu.write_rows.side_effect = lambda ss, ws, start_row, rows: written_rows.extend(rows)
        mock_feishu.get_sheets.return_value = [{'sheet_id': 'zdctqN', 'grid_properties': {'row_count': 100}}]
        mock_feishu.find_last_row_index.return_value = 2
        mock_feishu.clear_rows_below.return_value = None
        mock_feishu.batch_update_values.side_effect = lambda ss, updates: batch_updates.extend(updates)
        mock_feishu.set_number_format.return_value = {}

        fetched = [{'日期': '20261016', '任务ID': '132897081', '流量类型': '全部流量', '归因口径': 30}]

        with patch('core.sync.FeishuClient', return_value=mock_feishu), \
             patch('core.sync.latest_sync_cutoff_date', return_value='2026-10-20'), \
             patch('core.sync.get_db', side_effect=lambda: get_db_connection(db_file)), \
             patch('core.sync.fetch_taobao_data', return_value=ProviderFetchResult(status=ProviderFetchStatus.SUCCESS, rows=fetched, pages_fetched=1)), \
             patch('core.sync.Notifier'):
            result = execute_inplace_ordered_sync(20, trigger_type='manual')

        assert result['status'] == 'success', result
        for r in written_rows:
            assert len(r) == len(headers)
        for upd in batch_updates:
            rng = upd.get('range', '')
            assert '!E' not in rng and '!AD' not in rng, f'Formula update leaked to protected column: {rng}'
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
