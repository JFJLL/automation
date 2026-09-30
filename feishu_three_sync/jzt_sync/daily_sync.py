"""Incremental sync with backups, complete date scanning and read-back checks."""
import json
import math
import numbers
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
from config_loader import APP_ID, APP_SECRET, FEISHU_SHEET_SHENXIANSHUANG, FEISHU_SHEET_ZHANGXIAOYI
from daily_client import ROOT, Feishu, SyncError, fetch_report, read_accounts


def task_mappings():
    local_dir = ROOT / 'configs/local'
    a_file = local_dir / 'tasks_mapping.json' if (local_dir / 'tasks_mapping.json').exists() else ROOT / 'configs/tasks_mapping.json'
    b_file = local_dir / 'b_sheets_tasks.json' if (local_dir / 'b_sheets_tasks.json').exists() else ROOT / 'configs/b_sheets_tasks.json'
    a = json.loads(a_file.read_text(encoding='utf-8'))['zhangxiaoyi']
    b = json.loads(b_file.read_text(encoding='utf-8'))
    return {'zhuorui': a, 'qicui': b}


def date_key(value):
    if isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isfinite(value) and int(value) == value:
        value = str(int(value))
    value = str(value).strip()
    if len(value) == 8 and value.isdigit():
        datetime.strptime(value, '%Y%m%d')
        return value
    return None


def normalize(row):
    result = []
    for v in row:
        if pd.isna(v):
            result.append('')
        elif isinstance(v, numbers.Integral):
            result.append(int(v))
        elif isinstance(v, numbers.Real):
            result.append(int(v) if int(v) == v else float(v))
        else:
            result.append(str(v))
    return result


def index_dates(rows):
    dates = {}
    for index, row in enumerate(rows, 1):
        if row and (key := date_key(row[0])):
            if key in dates:
                raise SyncError(f'Duplicate date {key}; manual review required')
            dates[key] = index
    return dates


def plan_rows(rows, df):
    existing = index_dates(rows)
    ordered = []
    for row in df.itertuples(index=False, name=None):
        r = normalize(row)
        key = date_key(r[0])
        if not key:
            raise SyncError('Invalid report date')
        r[0] = int(key)
        ordered.append(r)
    ordered.sort(key=lambda r: r[0])
    index_dates(ordered)
    append = [r for r in ordered if str(r[0]) not in existing]
    updates = [(existing[str(r[0])], r) for r in ordered[-3:] if str(r[0]) in existing]
    return append, updates


def sync_one(fc, cookie, token, sheet, item, backup_dir, dry_run):
    task_id, sid = str(item['task_id']), sheet['sheetId']
    df = fetch_report(cookie, task_id)
    if df.empty:
        return {'task': task_id, 'status': 'empty', 'appended': 0, 'updated': 0}
    # Read the entire allocated sheet, not the original hard-coded first 200 rows.
    count = int(sheet['rowCount'])
    rows = []
    for start in range(1, count + 1, 2000):
        end = min(start + 1999, count)
        block = fc.read(token, f'{sid}!A{start}:Y{end}')
        rows.extend(block + [[]] * (end - start + 1 - len(block)))
    for r in rows:
        if r and date_key(r[0]):
            existing_id = r[1] if len(r) > 1 else None
            if existing_id in (None, ''):
                if len(r) < 3 or str(r[2]) not in set(df.iloc[:, 2].astype(str)):
                    raise SyncError(f'Task {task_id}: blank task ID and unrecognized title')
            elif str(existing_id).removesuffix('.0') != task_id:
                raise SyncError(f'Task {task_id}: target sheet contains another task')
    append, updates = plan_rows(rows, df)
    changed = []
    for index, row in updates:
        old = (rows[index - 1] + [''] * 25)[:25]
        old[0] = int(date_key(old[0]))
        old = ['' if v is None else v for v in old]
        if old != row:
            changed.append((index, row))
    updates = changed
    result = {'task': task_id, 'sheet': item['sheet_name'], 'status': 'planned' if dry_run else 'success',
              'appended': len(append), 'updated': len(updates), 'latest_date': str(df.iloc[:, 0].max())}
    if dry_run:
        return result
    (backup_dir / f'{sid}_{task_id}.json').write_text(json.dumps({'sheet_id': sid, 'sheet_name': item['sheet_name'], 'rows': rows}, ensure_ascii=False), encoding='utf-8')
    for index, row in updates:
        fc.write(token, f'{sid}!A{index}:Y{index}', [row])
    for start in range(0, len(append), 200):
        fc.append(token, sid, append[start:start + 200])
    expected = append + [r for _, r in updates]
    actual_count = next(int(s['rowCount']) for s in fc.sheets(token) if s['sheetId'] == sid)
    actual_rows = fc.read(token, f'{sid}!A1:Y{actual_count}')
    actual_idx = index_dates(actual_rows)
    for row in expected:
        index = actual_idx.get(str(row[0]))
        if not index:
            raise SyncError(f'Task {task_id}: read-back date missing')
        actual = (actual_rows[index - 1] + [''] * 25)[:25]
        actual[0] = int(date_key(actual[0]))
        if actual != row:
            raise SyncError(f'Task {task_id}: read-back values differ for date {row[0]}')
    return result


def sync_all(dry_run=False, categories=None):
    fc, accounts = Feishu(APP_ID, APP_SECRET), read_accounts()
    mappings = task_mappings()
    urls = {'zhuorui': FEISHU_SHEET_ZHANGXIAOYI, 'qicui': FEISHU_SHEET_SHENXIANSHUANG}
    backup_dir = ROOT / 'backups' / datetime.now().strftime('%Y%m%d_%H%M%S')
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
    jobs, results = [], []
    for cat in (categories or mappings.keys()):
        token = fc.resolve(urls[cat])
        sheets = {s['title']: s for s in fc.sheets(token)}
        for item in mappings[cat]:
            if item['sheet_name'] not in sheets:
                results.append({'task': item['task_id'], 'status': 'failed', 'reason': 'mapped sheet missing'})
            else:
                jobs.append((cat, token, sheets[item['sheet_name']], item))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(sync_one, fc, accounts[cat]['cookie'], token, sheet, item, backup_dir, dry_run): item for cat, token, sheet, item in jobs}
        for future in as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                # Don't dump HTTP headers, response bodies or cookies to logs.
                result = {'task': item['task_id'], 'status': 'failed', 'reason': str(exc) if isinstance(exc, SyncError) else type(exc).__name__}
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    return results
