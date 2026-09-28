import json
import time
import re
import os
import requests
import oss2
from typing import List, Dict, Any, Optional
from pathlib import Path
from platforms.registry import fetch_oss_token
from app.config import (
    JUGUANG_OSS_OBJECT_KEY, JUGUANG_OSS_SUBACCOUNT_PREFIX, BASE_DIR,
    OSS_ENDPOINT, OSS_BUCKET, OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET
)

LOCAL_FALLBACK = BASE_DIR.parent / "feishu_three_sync" / "jg_sync" / "session_headers.json"
REPORT_URL = "https://ad.xiaohongshu.com/api/leona/rtb/common/data/report"

METRICS = dict(zip(
    ['消费','展现量','点击量','点击率','平均点击成本','平均千次展示费用','点赞','评论','收藏','关注','分享','互动量','平均互动成本','行动按钮点击量','行动按钮点击率','截图','保存图片','小红星站外活跃UV(30日归因)','小红星站外活跃成本(30日归因)','小红星任务期消费','搜索组件点击量','搜索组件点击转化率','平均搜索后阅读笔记篇数','搜后阅读量','新增种草人群','新增种草人群成本','新增深度种草人群','新增深度种草人群成本'],
    ['fee','impression','click','ctr','acp','cpm','like','comment','collect','follow','share','interaction','cpi','actionButtonClick','actionButtonCtr','screenshot','picSave','outsideShopVisit','outsideShopVisitPrice','tbTaskFee','searchCmtClick','searchCmtClickCvr','searchCmtAfterReadAvg','searchCmtAfterRead','iUserNum','iUserPrice','tiUserNum','tiUserPrice']
))

IDENTITY = {
    '时间': 'time', '投放位置': 'placementName', '精准定向': 'targetDetail', '关键词': 'keyword',
    '创意名称': 'creativityName', '创意ID': 'creativityId', '笔记ID': 'noteId',
    '笔记跳转链接': 'noteJumpUrl', '单元名称': 'unitName', '单元ID': 'unitId',
    '计划名称': 'campaignName', '计划ID': 'campaignId'
}

PLACES = {'1': '信息流推广', '2': '搜索推广', '4': '全站智投', '7': '视频流推广'}

def get_juguang_headers() -> Dict[str, str]:
    if JUGUANG_OSS_OBJECT_KEY:
        try:
            raw = fetch_oss_token(JUGUANG_OSS_OBJECT_KEY)
            data = json.loads(raw)
            if isinstance(data, dict) and "cookie" in data:
                return data
        except Exception as e:
            print(f"[Juguang] Read OSS headers failed: {e}")
    candidates = [
        Path(os.getenv("JUGUANG_TOKEN_PATH", "")),
        BASE_DIR / "tokens" / "session_headers.json",
        BASE_DIR / "tokens" / "juguang_headers.json",
        BASE_DIR / "data" / "session_headers.json",
        BASE_DIR.parent / "feishu_three_sync" / "jg_sync" / "session_headers.json",
    ]
    for p in candidates:
        if p and p.exists() and p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    raise RuntimeError("聚光 会话配置未配置或无法从 OSS 获取")

def get_juguang_subaccount_headers(sub_account_id: str) -> Dict[str, str]:
    """从 OSS (或本地缓存) 读取指定聚光子账号的 Cookie 并组装请求头"""
    cookie_text = ""
    object_key = f"{JUGUANG_OSS_SUBACCOUNT_PREFIX.rstrip('/')}/{sub_account_id.strip()}.txt"
    try:
        cookie_text = fetch_oss_token(object_key).strip()
    except Exception as e:
        print(f"[Juguang] Read OSS subaccount token failed ({object_key}): {e}")
    
    if not cookie_text:
        local_candidates = [
            BASE_DIR / "tokens" / f"{sub_account_id}.txt",
            Path("D:/download/pic-vec/oss-upload/cookies") / f"{sub_account_id}.txt"
        ]
        for p in local_candidates:
            if p.exists() and p.is_file():
                cookie_text = p.read_text(encoding="utf-8").strip()
                break
                
    if not cookie_text:
        raise RuntimeError(f"未获取到聚光子账号 [{sub_account_id}] 的 Cookie，请检查 OSS 或 Cookie 同步状态")
        
    return {
        "cookie": cookie_text,
        "v-seller-id": sub_account_id.strip(),
        "origin": "https://ad.xiaohongshu.com",
        "referer": "https://ad.xiaohongshu.com/aurora/ad/datareports-b",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "content-type": "application/json"
    }

_subaccounts_cache = {"timestamp": 0.0, "data": []}

def get_juguang_subaccounts_list(force_refresh: bool = False) -> List[Dict[str, str]]:
    """动态从 OSS 获取最新的子账号元数据映射及 Token 列表，支持动态账号增减与状态识别，无需代码固化"""
    global _subaccounts_cache
    now = time.time()
    if not force_refresh and _subaccounts_cache["data"] and (now - _subaccounts_cache["timestamp"] < 60):
        return _subaccounts_cache["data"]

    known_meta = {}

    # 1. 优先从 OSS 动态实时拉取 subaccounts_meta.json 元数据映射
    meta_key = f"{JUGUANG_OSS_SUBACCOUNT_PREFIX.rstrip('/')}/subaccounts_meta.json"
    try:
        meta_raw = fetch_oss_token(meta_key).strip()
        if meta_raw:
            for item in json.loads(meta_raw):
                sid = item.get("id") or item.get("subId")
                sname = item.get("name")
                if sid and sname:
                    known_meta[sid] = {
                        "name": sname,
                        "status": item.get("status", 1)
                    }
    except Exception as e:
        print(f"[Juguang] Dynamic fetch OSS subaccounts_meta failed ({meta_key}): {e}")

    # 2. 运行时本地动态缓存兜底（仅在 OSS 偶发网络超时时应急，不入 Git 仓库）
    cache_candidates = [
        BASE_DIR / "data" / "juguang_subaccounts_cache.json",
        BASE_DIR / "tokens" / "juguang_subaccounts.json"
    ]
    for cf in cache_candidates:
        if cf.exists():
            try:
                for item in json.loads(cf.read_text(encoding="utf-8")):
                    sid = item.get("id") or item.get("subId")
                    sname = item.get("name")
                    if sid and sname and sid not in known_meta:
                        known_meta[sid] = {
                            "name": sname,
                            "status": item.get("status", 1)
                        }
            except Exception:
                pass

    oss_ids = set()
    if OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET and OSS_BUCKET:
        try:
            auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
            bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)
            prefix = JUGUANG_OSS_SUBACCOUNT_PREFIX.lstrip("/")
            for obj in oss2.ObjectIterator(bucket, prefix=prefix):
                if obj.key.endswith(".txt"):
                    sid = obj.key.split("/")[-1][:-4]
                    if len(sid) == 24:
                        oss_ids.add(sid)
        except Exception as e:
            print(f"[Juguang] List OSS subaccount tokens failed: {e}")

    target_ids = sorted(list(oss_ids)) if oss_ids else sorted(list(known_meta.keys()))

    subaccounts = []
    for sid in target_ids:
        info = known_meta.get(sid, {})
        raw_name = info.get("name") if isinstance(info, dict) else str(info)
        name = raw_name if raw_name and not raw_name.startswith("聚光子账号_") else f"聚光子账号_{sid[:8]}"
        status = info.get("status", 1) if isinstance(info, dict) else 1
        subaccounts.append({
            "id": sid,
            "name": name,
            "status": status
        })

    if subaccounts:
        # 仅将运行时状态保存在本地数据目录供离线兜底，不提交 Git
        try:
            cache_file = BASE_DIR / "data" / "juguang_subaccounts_cache.json"
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(subaccounts, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        _subaccounts_cache["timestamp"] = now
        _subaccounts_cache["data"] = subaccounts
        return subaccounts

    return _subaccounts_cache["data"]

def fetch_juguang_data(entity_id: str, split_type: str, start_date: str, end_date: str, headers_override: Optional[Dict[str, str]] = None, sub_account_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if headers_override:
        hdrs = headers_override
    elif sub_account_id:
        hdrs = get_juguang_subaccount_headers(sub_account_id)
    else:
        hdrs = get_juguang_headers()
    session = requests.Session()
    session.trust_env = False
    session.headers.update(hdrs)
    
    source = 'account' if split_type == 'account' else 'creativity'
    split = {'placement': ['placement'], 'target': ['targetDetail'], 'keyword': ['keyword']}.get(split_type, [])
    dims = ['time', 'placement'] if source == 'account' else ['time', 'creativityId', 'creativityName', 'noteId', 'unitId', 'unitName', 'campaignId', 'campaignName']
    columns = list(dict.fromkeys(dims + split + list(METRICS.values())))
    
    rows = []
    for page in range(1, 101):
        payload = {
            'pageNum': page, 'pageSize': 500, 'sorts': [{'column': 'time', 'sort': 'asc'}],
            'filters': [], 'dataCaliber': 0, 'timeUnit': 'DAY', 'splitColumns': split,
            'startDate': start_date, 'endDate': end_date, 'webModule': 'base_report_page',
            'dataSource': source, 'dataPattern': 'table', 'columns': columns
        }
        r = session.post(REPORT_URL, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get("success") is not True:
            break
        model = data.get("data") or {}
        batch = model.get("dataList") or []
        for item in batch:
            values = json.loads(item.get("dataValueJson") or "{}")
            row = {**item, **values}
            d_val = str(row.get("time", ""))[:10]
            if start_date <= d_val <= end_date:
                # 补充中文键
                row["时间"] = d_val
                row["日期"] = d_val
                if "placement" in row:
                    row["投放位置"] = PLACES.get(str(row["placement"]), str(row.get("placementName", "")))
                for cn, en in IDENTITY.items():
                    if en in row:
                        row[cn] = row[en]
                for cn, en in METRICS.items():
                    if en in row:
                        row[cn] = row[en]
                rows.append(row)
        total_page = int((model.get("page") or {}).get("totalPage", 1))
        if page >= total_page or not batch:
            break
        time.sleep(0.3)
    return rows
