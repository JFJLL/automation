"""Synchronize the user-managed information sheet; preserve unrelated columns."""
import argparse
import json
import os
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import taobaoxinghe_feishu_order_effect as m

ROOT = Path(__file__).resolve().parent
WIKI = 'OOpNw9CBJiqNrCkFjcIc5Q8bnXc'


def cell(value):
    if isinstance(value, list):
        return ''.join(str(x.get('text', '')) if isinstance(x, dict) else str(x) for x in value)
    return '' if value is None else str(value).strip()


def day(value):
    text = cell(value).replace('/', '').replace('-', '')
    return datetime.strptime(text[:8], '%Y%m%d').date()


def equivalent(a, b):
    a, b = cell(a), cell(b)
    if a == b:
        return True
    try:
        return Decimal(a) == Decimal(b)
    except InvalidOperation:
        return False


def row_key(row):
    return (day(row[0]).isoformat(), cell(row[1]), cell(row[2]), cell(row[3]))


def merge_changes(old, fetched, width):
    """Return only changed managed cells, retaining row positions and annotations."""
    indices = {}
    last = 1
    for index, row in enumerate(old[1:], 2):
        if any(cell(x) for x in row):
            last = index
        if not cell(row[0]):
            continue
        key = row_key(row)
        if key in indices:
            raise ValueError(f'Duplicate existing key: {key}')
        indices[key] = index
    changes, added, updated = {}, 0, 0
    seen = set()
    for row in fetched:
        key = row_key(row)
        if key in seen:
            raise ValueError(f'Duplicate source key: {key}')
        seen.add(key)
        index = indices.get(key)
        if index is None:
            last += 1
            index = last
            added += 1
        elif all(equivalent(a, b) for a, b in zip(old[index-1][:width], row)):
            continue
        else:
            updated += 1
        changes[index] = row
    return changes, added, updated


class Table:
    def __init__(self):
        m.load_env_file()
        self.app = m.env_first('FEISHU_APP_ID', 'appid')
        self.secret = m.env_first('FEISHU_APP_SECRET', 'app_secret')
        self.token = m.resolve_wiki_sheet(self.app, self.secret, WIKI)['spreadsheetToken']
        self.session = m.requests.Session()
        self.session.trust_env = False
        self.session.headers['Authorization'] = 'Bearer ' + m.feishu_tenant_access_token(self.app, self.secret)
        self.base = 'https://open.feishu.cn/open-apis'
        self.sheets = self.api('GET', f'/sheets/v3/spreadsheets/{self.token}/sheets/query')['sheets']

    def api(self, method, path, **kwargs):
        for attempt in range(4):
            response = self.session.request(method, self.base+path, timeout=60, **kwargs)
            data = response.json()
            if data.get('code') == 0:
                return data.get('data') or {}
            if data.get('code') == 90217 and attempt < 3:
                time.sleep(2 * (attempt+1))
                continue
            raise RuntimeError(f'Feishu {data.get("code")}: {data.get("msg")}')

    def read(self, sid, end='AZ'):
        return self.api('GET', f'/sheets/v2/spreadsheets/{self.token}/values/{sid}!A:{end}').get('valueRange', {}).get('values') or []

    def write_changes(self, sheet, changes, width):
        if not changes:
            return
        sid = sheet['sheet_id']
        required = max(changes)
        current = sheet['grid_properties']['row_count']
        if required > current:
            self.api('POST', f'/sheets/v2/spreadsheets/{self.token}/dimension_range', json={'dimension': {'sheetId': sid, 'majorDimension': 'ROWS', 'length': required-current}})
            time.sleep(1.2)
        items = sorted(changes.items())
        for offset in range(0, len(items), 50):
            batch = items[offset:offset+50]
            ranges = [{'range': f'{sid}!A{i}:{m.column_letter(width)}{i}', 'values': [row]} for i, row in batch]
            self.api('POST', f'/sheets/v2/spreadsheets/{self.token}/values_batch_update', json={'valueRanges': ranges})
            time.sleep(1.2)
        verify = self.read(sid)
        for index, row in items:
            if index > len(verify) or not all(equivalent(a, b) for a, b in zip(verify[index-1][:width], row)):
                raise RuntimeError(f'Readback mismatch: {sid} row {index}')


def resolve_order(sc, name, task_management=False):
    if not task_management:
        orders = m.FeishuOrderEffectExporter(sc).search_orders(keyword=name, page_size=100)
        matches = [o for o in orders if o.get('orderName') == name]
    else:
        orders = []
        for page in range(1, 51):
            data = sc.get_json('/api/one/order/list', {
                'saleType': 4, 'keyword': name, 'keywordType': 103,
                'pageNo': page, 'pageSize': 100})
            if data.get('success') is not True:
                raise RuntimeError(f'Task list failed: {data.get("msgInfo")}')
            rows, model = m.list_from_model(data.get('model'))
            orders.extend(rows)
            if not model.get('hasNext'):
                break
        else:
            raise RuntimeError('Task list pagination exceeded 50 pages')
        # Match the user-provided full name within the platform's generated name,
        # then verify the corresponding project and internal ID via current API.
        matches = [o for o in orders if o.get('orderName', '').startswith('自动生成_'+name)]
    if len(matches) != 1:
        raise ValueError(f'Expected one matching order, found {len(matches)}: {name}')
    order = matches[0]
    if task_management:
        detail = sc.get_json('/api/one/order/get', {'orderId': order['orderId']})
        if detail.get('success') is not True:
            raise RuntimeError(f'Task detail failed: {detail.get("msgInfo")}')
        model = detail.get('model') or {}
        project = str(model.get('projectName') or '')
        if not project or not (name == project or name == project+'（第一单）'):
            raise ValueError(f'Task project does not match configuration: {project}')
        if model.get('saleType') != 4 or model.get('settleSeqId') != order.get('settleSeqId'):
            raise ValueError('Task identity differs between list and detail')
        return model
    return order


def fetch(sc, order, batch, start, end):
    ext = json.loads(m.FeishuOrderEffectExporter(sc).build_detail_ext(order, cycle_days=30))
    ext['dataBatch'] = batch
    result = []
    for page in range(1, 501):
        data = sc.get_json('/api/report/multiscene/query/detail/data', {
            'bizType': 'selfOfficial_orderInfo_detail',
            'dataBatch': batch, 'ext': json.dumps(ext), 'startTime': f'{start} 00:00:00',
            'endTime': f'{end} 23:59:59', 'pageNo': page, 'pageSize': 100})
        if data.get('success') is not True:
            raise RuntimeError(f'Report failed: {data.get("msgCode")} {data.get("msgInfo")}')
        rows, model = m.list_from_model(data.get('model'))
        result.extend(rows)
        if not model.get('hasNext') and len(rows) < 100:
            return result
        if not rows:
            return result
        time.sleep(.2)
    raise RuntimeError('Report pagination exceeded 500 pages')


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--dry-run', action='store_true')
    args = args.parse_args()
    # This machine's local proxy breaks some platform requests.
    for name in list(os.environ):
        if name.lower().endswith('_proxy'):
            os.environ.pop(name)
    table = Table()
    by_title = {x['title']: x for x in table.sheets}
    configs = table.read(by_title['信息表']['sheet_id'], 'F')[1:]
    cookies, _ = m.load_cookies()
    sc = m.TaobaoXingheScraperV5(cookies=cookies, debug=False)
    cutoff = date.today()-timedelta(days=1)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = ROOT/'backups'/f'configured_{stamp}'
    backup.mkdir(parents=True)
    summaries = []
    for cfg in configs:
        if not cell(cfg[0]):
            continue
        name, dimension, title, start_value, _, location = map(cell, cfg[:6])
        summary = {'name': name, 'sheet': title, 'dimension': dimension}
        try:
            sheet = by_title[title]
            old = table.read(sheet['sheet_id'])
            (backup/f'{sheet["sheet_id"]}.json').write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
            content = dimension == '内容'
            width = 32 if content else 29
            expected = ['日期', '内容ID' if content else '任务ID', '流量类型', '归因口径']
            if list(map(cell, old[0][:4])) != expected:
                raise ValueError('Unexpected worksheet headers')
            metrics = [x[0] for x in m.EFFECT_COLUMNS]
            actual_metrics = [cell(x).lower() for x in old[0][7 if content else 4:width]]
            if actual_metrics != [x.lower() for x in metrics]:
                raise ValueError('Metric column order differs from API mapping')
            dates = [day(r[0]) for r in old[1:] if cell(r[0])]
            start = max(day(start_value), max(dates)-timedelta(days=2)) if dates else day(start_value)
            task_management = location == '任务管理'
            order = resolve_order(sc, name, task_management)
            summary.update(internal_order_id=order['orderId'], report_order_id=order['settleSeqId'])
            if task_management:
                # Old exported IDs do not identify the current generated task.
                # Backfill a newly mapped ID from the configured start date.
                current_dates = [day(r[0]) for r in old[1:] if cell(r[0]) and cell(r[1]) == str(order['settleSeqId'])]
                start = max(day(start_value), max(current_dates)-timedelta(days=2)) if current_dates else day(start_value)
            source = fetch(sc, order, 'content' if content else 'order', start.isoformat(), cutoff.isoformat())
            rows = []
            for item in source:
                if str(item.get('orderId')) != str(order['settleSeqId']):
                    raise ValueError('API returned a different order ID')
                d = day(item.get('ds') or item.get('theDate'))
                if not start <= d <= cutoff:
                    raise ValueError('API returned a date outside requested range')
                rid = item.get('contentId') if content else item.get('orderId')
                if not rid:
                    raise ValueError('Missing row identifier')
                row = [int(d.strftime('%Y%m%d')), str(rid), '全部流量', 30]
                if content:
                    row += [item.get('kolName', ''), item.get('contentUrl', ''), item.get('orderName', name)]
                row += [item.get(key, '') for _, key in m.EFFECT_COLUMNS]
                rows.append(row)
            changes, added, updated = merge_changes(old, rows, width)
            summary.update(source_rows=len(rows), appended=added, updated=updated,
                           latest_source_date=max((day(r[0]).isoformat() for r in rows), default=None))
            if not rows:
                summary['note'] = '平台请求成功但无报表明细；保留历史数据，下次继续查询'
            if not args.dry_run:
                table.write_changes(sheet, changes, width)
            summary['status'] = 'dry-run' if args.dry_run else 'success'
        except Exception as exc:
            summary.update(status='failed', error=str(exc))
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    report = {'time': datetime.now().isoformat(), 'wiki': WIKI, 'dry_run': args.dry_run,
              'backup': str(backup), 'results': summaries}
    (ROOT/'logs').mkdir(exist_ok=True)
    (ROOT/'logs'/('configured_table_dry_run.json' if args.dry_run else 'configured_table_last_run.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 1 if any(x['status'] == 'failed' for x in summaries) else 0


if __name__ == '__main__':
    raise SystemExit(main())
