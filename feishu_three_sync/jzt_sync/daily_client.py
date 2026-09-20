"""Checked, bounded HTTP clients for unattended daily runs."""
import configparser
import io
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
REPORT_URL = 'https://jzt-api.jd.com/jrw/content/outside/demand/report/downloadGrassDailyData'
IDENTITY_URL = 'https://jzt-api.jd.com/common/getpin'


class SyncError(RuntimeError):
    pass


def session():
    s = requests.Session()
    # Local proxy breaks JD report POSTs. All recipients use ordinary verified HTTPS.
    s.trust_env = False
    s.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36'
    return s


def read_accounts():
    cfg = configparser.RawConfigParser()
    cfg.read(ROOT / 'token.txt', encoding='utf-8')
    for name in ('zhuorui', 'qicui'):
        if not cfg.has_section(name) or not cfg.get(name, 'pin', fallback=''):
            raise SyncError(f'Missing account configuration: {name}')
    return cfg


def identity(cookie):
    with session() as s:
        r = s.post(IDENTITY_URL, headers={'Cookie': cookie}, timeout=(10, 30), allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308, 401, 403):
            return None
        r.raise_for_status()
        try:
            d = r.json()
        except ValueError:
            return None
    return d.get('data') if d.get('success') is True and isinstance(d.get('data'), str) else None


def fetch_report(cookie, task_id):
    payload = dict(taskId=str(task_id), dataCycle='30', cateId='', brandId='6731', mediaTaskId='',
                   mediaOrderId='', contentId='', campaignId='', unitId='', creativeId='', type='2',
                   dataScope='2', dimension='2', dataCaliber='0', attributionTouchType='1', trafficSource='1', pageIndex='1')
    with session() as s:
        r = s.post(REPORT_URL, data=payload, headers={'Cookie': cookie}, timeout=(10, 60))
        r.raise_for_status()
    if r.content[:2] not in (b'PK', b'\xd0\xcf'):
        raise SyncError(f'Task {task_id}: report endpoint did not return an Excel workbook; check login/permissions')
    df = pd.read_excel(io.BytesIO(r.content))
    if len(df.columns) != 25 or df.columns[0] != '日期' or df.columns[1] != '任务ID':
        raise SyncError(f'Task {task_id}: unexpected report schema')
    if not df.empty and not all(str(int(v)) == str(task_id) for v in df.iloc[:, 1]):
        raise SyncError(f'Task {task_id}: returned task IDs do not match')
    return df


class Feishu:
    def __init__(self, app_id, secret):
        self.app_id, self.secret = app_id, secret
        self.token, self.expires = None, 0
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.last_write = 0

    def get_token(self):
        with self.lock:
            if self.token and time.time() < self.expires - 120:
                return self.token
            with session() as s:
                r = s.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                           json={'app_id': self.app_id, 'app_secret': self.secret}, timeout=(10, 30))
                r.raise_for_status()
                d = r.json()
            if d.get('code') != 0:
                raise SyncError(f'Feishu authentication rejected, code={d.get("code")}')
            self.token, self.expires = d['tenant_access_token'], time.time() + d['expire']
            return self.token

    def call(self, method, path, **kwargs):
        if method in ('PUT', 'POST'):
            with self.write_lock:
                for attempt in range(5):
                    time.sleep(max(0, 1.2 - (time.monotonic() - self.last_write)))
                    try:
                        return self._call(method, path, **kwargs)
                    except SyncError as exc:
                        if 'code=90217' not in str(exc) and 'code=99991400' not in str(exc):
                            raise
                        if attempt == 4:
                            raise
                        time.sleep(2 ** attempt)
                    finally:
                        self.last_write = time.monotonic()
        return self._call(method, path, **kwargs)

    def _call(self, method, path, **kwargs):
        with session() as s:
            r = s.request(method, 'https://open.feishu.cn/open-apis/' + path,
                          headers={'Authorization': 'Bearer ' + self.get_token()}, timeout=(10, 45), **kwargs)
            r.raise_for_status()
            d = r.json()
        if d.get('code') != 0:
            raise SyncError(f'Feishu {method} failed, code={d.get("code")}; no success recorded')
        return d['data']

    def resolve(self, value):
        if '/wiki/' in value:
            node = urlparse(value).path.split('/wiki/')[1].split('/')[0]
            return self.call('GET', 'wiki/v2/spaces/get_node', params={'token': node})['node']['obj_token']
        if '/sheets/' in value:
            return urlparse(value).path.split('/sheets/')[1].split('/')[0]
        return value

    def sheets(self, token):
        return self.call('GET', f'sheets/v2/spreadsheets/{token}/metainfo')['sheets']

    def read(self, token, range_):
        return self.call('GET', f'sheets/v2/spreadsheets/{token}/values/{range_}')['valueRange'].get('values', [])

    def write(self, token, range_, rows):
        return self.call('PUT', f'sheets/v2/spreadsheets/{token}/values',
                         json={'valueRange': {'range': range_, 'values': rows}})

    def append(self, token, sheet_id, rows):
        return self.call('POST', f'sheets/v2/spreadsheets/{token}/values_append',
                         json={'valueRange': {'range': f'{sheet_id}!A1:Y{len(rows)}', 'values': rows}})
