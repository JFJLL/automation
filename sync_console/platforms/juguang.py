import json
import time
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path
from platforms.registry import fetch_oss_token
from app.config import JUGUANG_OSS_OBJECT_KEY, BASE_DIR

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
    if LOCAL_FALLBACK.exists():
        data = json.loads(LOCAL_FALLBACK.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    raise RuntimeError("聚光 会话配置未配置或无法从 OSS 获取")

def fetch_juguang_data(entity_id: str, split_type: str, start_date: str, end_date: str, headers_override: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    hdrs = headers_override or get_juguang_headers()
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
