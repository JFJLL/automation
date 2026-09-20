"""Juguang daily Feishu sync, with validated web report fields and row-level writes."""
import argparse
import json
import msvcrt
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
TAOBAO = ROOT.parent / 'taobao'
sys.path.insert(0, str(TAOBAO))
import sync_configured_table as fs

WIKI = 'S1USwIVTJisg3EkPPBTcFLisnPh'
ACCOUNT = '659e1399096eae00013086d6'
METRICS = dict(zip(
    ['消费','展现量','点击量','点击率','平均点击成本','平均千次展示费用','点赞','评论','收藏','关注','分享','互动量','平均互动成本','行动按钮点击量','行动按钮点击率','截图','保存图片','小红星站外活跃UV(30日归因)','小红星站外活跃成本(30日归因)','小红星任务期消费','搜索组件点击量','搜索组件点击转化率','平均搜索后阅读笔记篇数','搜后阅读量','新增种草人群','新增种草人群成本','新增深度种草人群','新增深度种草人群成本'],
    ['fee','impression','click','ctr','acp','cpm','like','comment','collect','follow','share','interaction','cpi','actionButtonClick','actionButtonCtr','screenshot','picSave','outsideShopVisit','outsideShopVisitPrice','tbTaskFee','searchCmtClick','searchCmtClickCvr','searchCmtAfterReadAvg','searchCmtAfterRead','iUserNum','iUserPrice','tiUserNum','tiUserPrice']))
IDENTITY = {'时间':'time','投放位置':'placementName','精准定向':'targetDetail','关键词':'keyword','创意名称':'creativityName','创意ID':'creativityId','笔记ID':'noteId','笔记跳转链接':'noteJumpUrl','单元名称':'unitName','单元ID':'unitId','计划名称':'campaignName','计划ID':'campaignId'}
PLACES = {'1':'信息流推广','2':'搜索推广','4':'全站智投','7':'视频流推广'}
UNSUPPORTED_SPLIT = {'iUserNum','iUserPrice','tiUserNum','tiUserPrice'}


def date_value(value):
    if isinstance(value, (int,float)) or str(value).replace('.','',1).isdigit() and len(str(value)) < 8:
        return date(1899,12,30)+timedelta(days=int(float(value)))
    return datetime.strptime(str(value).strip()[:10].replace('/','-'),'%Y-%m-%d').date()


def format_date(value):
    d = date_value(value)
    return f'{d.year}/{d.month}/{d.day}'


def scalar(value):
    if value is None:
        return ''
    if isinstance(value,(int,float)):
        return value
    value = str(value).strip()
    if value in ('','-'):
        return value
    try:
        if value.endswith('%'):
            return float(Decimal(value[:-1])/100)
        n = Decimal(value)
        return int(n) if n == n.to_integral() else float(n)
    except InvalidOperation:
        return value


class ReportClient:
    def __init__(self):
        headers = json.loads((ROOT/'session_headers.json').read_text(encoding='utf-8'))
        if headers.get('v-seller-id') != ACCOUNT:
            raise ValueError('Saved session account differs from configured account')
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(headers)

    def fetch(self, source, split, start, end):
        dims = ['time','placement'] if source=='account' else ['time','creativityId','creativityName','noteId','unitId','unitName','campaignId','campaignName','noteMaterialType']
        columns = list(dict.fromkeys(dims+split+list(METRICS.values())))
        rows, expected = [], None
        for page in range(1,501):
            payload = {'pageNum':page,'pageSize':500,'sorts':[{'column':'time','sort':'asc'}],
                'filters':[],'dataCaliber':0,'timeUnit':'DAY','splitColumns':split,
                'startDate':start.isoformat(),'endDate':end.isoformat(),'webModule':'base_report_page',
                'dataSource':source,'dataPattern':'table','columns':columns}
            response = self.session.post('https://ad.xiaohongshu.com/api/leona/rtb/common/data/report',json=payload,timeout=60)
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError:
                raise RuntimeError('聚光返回登录页或非JSON内容，请更新后台登录Cookie')
            if data.get('success') is not True or data.get('code') != 0:
                raise RuntimeError(f'聚光请求失败 {data.get("code")}: {data.get("msg")}; 如登录过期请更新后台Cookie')
            model=data.get('data') or {}
            info=model.get('page') or {}
            if 'totalCount' not in info:
                raise RuntimeError('Report response lacks pagination metadata')
            if expected is None:
                expected=int(info['totalCount'])
            elif expected != int(info['totalCount']):
                raise RuntimeError('Report changed during pagination; rerun instead of incomplete writes')
            batch=model.get('dataList') or []
            for item in batch:
                values=json.loads(item.get('dataValueJson') or '{}')
                row={**item,**values}
                if not start <= date_value(row.get('time','')) <= end:
                    raise RuntimeError('Report returned date outside requested range')
                rows.append(row)
            if page>=int(info.get('totalPage',1)) or len(rows)>=expected:
                break
            if not batch:
                raise RuntimeError('Empty report page before total reached')
            time.sleep(.3)
        if len(rows)!=expected:
            raise RuntimeError(f'Incomplete pagination {len(rows)}/{expected}')
        return rows


def convert(row, headers, split):
    result=[]
    for label in headers:
        key=IDENTITY.get(label) or METRICS.get(label)
        if not key:
            raise ValueError(f'Unknown managed column: {label}')
        if label=='时间':
            result.append(format_date(row['time']))
        elif label=='投放位置':
            val=row.get(key) or PLACES.get(str(row.get('placement')))
            if not val: raise ValueError('Missing placement name')
            result.append(val)
        elif key in UNSUPPORTED_SPLIT and split and key not in row:
            result.append('-')
        elif key not in row or row[key] is None:
            raise ValueError(f'Missing required field {label}/{key}')
        else:
            result.append(scalar(row[key]) if label in METRICS else str(row[key]))
    return result


def row_key(row, headers):
    fields=['时间','投放位置'] if '投放位置' in headers else ['时间','创意ID']
    fields += [x for x in ['精准定向','关键词'] if x in headers]
    return tuple(date_value(row[headers.index(x)]).isoformat() if x=='时间' else fs.cell(row[headers.index(x)]) for x in fields)


def changes_for(old, new, headers):
    indices={}
    last=1
    for i,row in enumerate(old[1:],2):
        if any(fs.cell(v) for v in row):last=i
        if not row or not fs.cell(row[0]):continue
        if '精准定向' in headers and not fs.cell(row[headers.index('精准定向')]):
            # Placeholder rows repaired from unavailable historical source data
            # are retained physically but excluded from source-key matching.
            continue
        if '创意ID' in headers and not fs.cell(row[headers.index('创意ID')]).isdigit():
            # Some historical rows were pasted without the targeting column.
            # Keep them untouched instead of treating shifted note IDs as creative IDs.
            continue
        key=row_key(row,headers)
        if key in indices:
            # Full repairs can expose prior duplicate historical records. Keep the
            # first source-matched row; report rows will consolidate it safely.
            continue
        indices[key]=i
    changes={};seen=set();added=updated=0
    for row in new:
        key=row_key(row,headers)
        if key in seen:raise ValueError(f'Duplicate source key {key}')
        seen.add(key)
        i=indices.get(key)
        if i is None:
            last+=1;i=last;added+=1
        elif len(old[i-1])>=len(row) and all(fs.equivalent(a,b) for a,b in zip(old[i-1],row)):
            continue
        else:updated+=1
        changes[i]=row
    return changes,added,updated


def repair_misaligned_rows(old, source_rows, headers, split):
    """Repair historical targeting rows that were pasted without targetDetail."""
    if '精准定向' not in headers or '创意ID' not in headers or '笔记ID' not in headers:
        return {}, 0, 0
    width = len(headers)
    # Matching only needs identity fields plus managed metrics; source fixtures and
    # older reports may omit optional URL fields.
    repair_headers = [h for h in headers[:width] if h in {'时间','精准定向','创意名称','创意ID','笔记ID','消费','展现量','点击量','点击率','平均点击成本','平均千次展示费用','点赞','评论','收藏','关注','分享','互动量','平均互动成本','行动按钮点击量','行动按钮点击率','截图','保存图片','小红星站外活跃UV(30日归因)','小红星站外活跃成本(30日归因)','小红星任务期消费','搜索组件点击量','搜索组件点击转化率','平均搜索后阅读笔记篇数','搜后阅读量','新增种草人群','新增种草人群成本','新增深度种草人群','新增深度种草人群成本'}]
    converted = []
    for raw in source_rows:
        values = convert(raw, repair_headers, split)
        by_header = dict(zip(repair_headers, values))
        converted.append([by_header.get(h, '') for h in headers[:width]])
    by_key = {}
    for raw, row in zip(source_rows, converted):
        k = (date_value(raw['time']).isoformat(), str(raw.get('creativityId','')), str(raw.get('noteId','')))
        by_key.setdefault(k, []).append(row)
    fixed = 0; unresolved = 0
    repairs = {}
    for i, row in enumerate(old[1:], 2):
        if not row or not fs.cell(row[0]):
            continue
        # A valid creative ID is numeric. In malformed rows, the target column is absent,
        # so the values at creativeName/creativeId/noteId are shifted one position left.
        cid_idx = headers.index('创意ID'); nid_idx = headers.index('笔记ID')
        if fs.cell(row[cid_idx]) .isdigit():
            continue
        if len(row) <= nid_idx:
            continue
        key = (date_value(row[0]).isoformat(), fs.cell(row[cid_idx-1]), fs.cell(row[nid_idx-1]))
        matches = by_key.get(key, [])
        if not matches:
            # The platform may no longer return very old creatives. Repair the
            # physical shape conservatively by inserting the missing target cell;
            # retain all historical values for later audit.
            repairs[i] = ([row[0], ''] + list(row[1:]))[:width]
            fixed += 1
            continue
        if len(matches) == 1:
            managed = matches[0]
        else:
            # Every value after the missing targeting column was shifted left.
            # Identity fields usually tie, so use all retained report values to choose
            # the one historical record whose old snapshot best matches the candidate.
            old_shifted = row[1:width-1]
            scores = [sum(fs.equivalent(a, b) for a, b in zip(old_shifted, candidate[2:])) for candidate in matches]
            best = max(scores)
            if best == 0 or scores.count(best) != 1:
                unresolved += 1
                continue
            managed = matches[scores.index(best)]
        # Repaired values occupy the managed region exactly; malformed rows may
        # carry one extra shifted cell, which must not be sent to Feishu.
        repairs[i] = list(managed[:width])
        fixed += 1
    return repairs, fixed, unresolved


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dry-run',action='store_true');parser.add_argument('--start-date');parser.add_argument('--full-refresh',action='store_true');args=parser.parse_args()
    (ROOT/'logs').mkdir(exist_ok=True)
    lock=(ROOT/'daily.lock').open('a+b');lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise RuntimeError('Another Juguang daily sync is running')
    report={'started':datetime.now().isoformat(),'dry_run':args.dry_run,'results':[]}
    try:
        fs.WIKI=WIKI
        table=fs.Table();client=ReportClient()
        sheets={x['title']:x for x in table.sheets}
        configs=table.read(sheets['信息表']['sheet_id'],'J')[1:]
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S');backup=ROOT/'backups'/stamp;backup.mkdir(parents=True)
        cutoff=date.today()-timedelta(days=1)
        for cfg in configs:
            if not fs.cell(cfg[0]):continue
            title=fs.cell(cfg[3]);result={'sheet':title}
            try:
                if fs.cell(cfg[0])!='聚光' or fs.cell(cfg[2])!=ACCOUNT or fs.cell(cfg[8])!='T-1':
                    raise ValueError('Unexpected platform, account, or reporting period in information sheet')
                sheet=sheets[title];old=table.read(sheet['sheet_id'])
                (backup/(sheet['sheet_id']+'.json')).write_text(json.dumps(old,ensure_ascii=False),encoding='utf-8')
                headers=[fs.cell(x) for x in old[0]]
                source='account' if fs.cell(cfg[4])=='账户报表' else 'creativity'
                split={'投放位置':['placement'],'定向类型':['targetDetail'],'搜索主题名称':['keyword'],'':[]}[fs.cell(cfg[7])]
                width=30 if source=='account' else 38 if split else 37
                headers=headers[:width]
                if '创意ID' in headers:
                    malformed=[i for i,r in enumerate(old[1:],2) if r and fs.cell(r[0]) and not fs.cell(r[headers.index('创意ID')]).isdigit()]
                    if malformed:result['historical_misaligned_rows_preserved']=len(malformed)
                dates=[date_value(r[0]) for r in old[1:] if r and fs.cell(r[0])]
                # The current information sheet has no date-range column. Full refresh therefore
                # starts at the earliest date already present in each target sheet.
                configured_start = min(dates) if dates else cutoff
                # Full refresh covers every historical date already in the sheet; normal runs only reread T+2.
                start=date.fromisoformat(args.start_date) if args.start_date else configured_start if args.full_refresh else max(configured_start, max(dates)-timedelta(days=2)) if dates else configured_start
                start=min(start,cutoff)
                raw=client.fetch(source,split,start,cutoff)
                (backup/(sheet['sheet_id']+'_source.json')).write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
                repairs, fixed, unresolved = repair_misaligned_rows(old, raw, headers, split)
                if unresolved:
                    result['misaligned_rows_unresolved'] = unresolved
                new=[convert(r,headers,split) for r in raw]
                changes,added,updated=changes_for(old,new,headers)
                for row_number, row in repairs.items():
                    if row_number not in changes or not all(fs.equivalent(a,b) for a,b in zip(old[row_number-1],row)):
                        changes[row_number] = row
                        updated += 1
                result.update(start=start.isoformat(),end=cutoff.isoformat(),source_rows=len(raw),appended=added,updated=updated,misaligned_rows_fixed=fixed)
                if not args.dry_run:table.write_changes(sheet,changes,width)
                result['status']='dry-run' if args.dry_run else 'success'
                if not raw:result['note']='平台返回0条，未清除历史记录'
            except Exception as exc:
                result.update(status='failed',error=str(exc))
            report['results'].append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
    except Exception as exc:
        report['error']=str(exc);print(str(exc),flush=True)
    finally:
        report['finished']=datetime.now().isoformat()
        (ROOT/'logs'/('dry_run.json' if args.dry_run else 'last_run.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()
    return 1 if report.get('error') or any(x['status']=='failed' for x in report['results']) else 0


if __name__=='__main__':
    raise SystemExit(main())
