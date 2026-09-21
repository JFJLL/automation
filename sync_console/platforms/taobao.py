import json
import time
import requests
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from pathlib import Path
from platforms.registry import fetch_oss_token
from app.config import ADSTAR_OSS_OBJECT_KEY, ADSTAR_OSS_BASE_URL, BASE_DIR

LOCAL_FALLBACK = BASE_DIR.parent / "feishu_three_sync" / "taobao" / "adstar.txt"
BASE_URL = "https://adstar.alimama.com"

EFFECT_COLUMNS = [
    ("阅读/播放UV", "readUv1d"),
    ("点赞UV", "likeUv1d"),
    ("评论UV", "commentUv1d"),
    ("收藏UV", "favoriteUv1d"),
    ("转发UV", "forwardUv1d"),
    ("互动UV", "engagementUv1d"),
    ("内容互动率", "contentEngagementRate"),
    ("搜索曝光UV", "slrAttrItmSeImpsUv1d"),
    ("搜索进店UV", "slrAttrSlrSeVstUv1d"),
    ("进店UV", "slrAttrSlrVstUv1d"),
    ("新客进店UV", "slrAttrSlrVstUv1dNew"),
    ("商品收藏UV", "slrAttrItmCltUv1d"),
    ("商品加购UV", "slrAttrItmCltCartUv1d"),
    ("关注店铺UV", "slrAttrSlrSubUv1d"),
    ("店铺会员UV", "slrAttrSlrMbrUv1d"),
    ("成交UV", "slrAttrItmOrdUv1d"),
    ("商家GMV", "slrAttrItmOrdGmv1d"),
    ("订单商品成交GMV", "slrAttrItmOrdGmv1d1bpOrd"),
    ("非订单商品成交GMV", "slrAttrItmOrdGmv1dNot1bpOrd"),
    ("新客成交UV", "slrAttrItmOrdUv1dNew"),
    ("订单商品新客成交GMV", "slrAttrItmOrdGmv1d1bpOrdNew"),
    ("预售付定GMV", "slrAttrItmOrdSubpayGmv1d"),
    ("预售整单预估GMV", "slrAttrItmOrdSubpayGmv1dPredAll"),
    ("预售付定UV", "slrAttrItmOrdSubpayUv1d"),
    ("成交转化率", "conversionRate"),
]

def parse_cookie_payload(raw: str) -> Dict[str, str]:
    raw = raw.strip()
    if raw.startswith("{") and raw.endswith("}"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass
    cookies = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies

def get_taobao_cookies() -> Dict[str, str]:
    if ADSTAR_OSS_OBJECT_KEY:
        try:
            raw = fetch_oss_token(ADSTAR_OSS_OBJECT_KEY, ADSTAR_OSS_BASE_URL)
            parsed = parse_cookie_payload(raw)
            if parsed:
                return parsed
        except Exception as e:
            print(f"[Taobao] Read OSS cookie failed: {e}")
    if LOCAL_FALLBACK.exists():
        raw = LOCAL_FALLBACK.read_text(encoding="utf-8").strip()
        parsed = parse_cookie_payload(raw)
        if parsed:
            return parsed
    raise RuntimeError("淘宝星河 Cookie 未配置或无法从 OSS 获取")

def fetch_taobao_data(entity_id: str, dimension: str, start_date: str, end_date: str, cookies: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    if not cookies:
        cookies = get_taobao_cookies()
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://adstar.alimama.com/portal/v2/pages/home/index.htm",
        "Origin": "https://adstar.alimama.com"
    })
    session.cookies.update(cookies)
    
    # 构造ext请求参数
    ext = {
        "settleSeqId": int(entity_id) if str(entity_id).isdigit() else entity_id,
        "projectId": 0,
        "media": "RED_BOOK",
        "saleType": 1,
        "businessMode": 88,
        "deliveryMode": "cptSeedDaily",
        "dataBatch": "content" if dimension == "内容" else "order",
        "flowType": "all",
        "cycleStr": "30",
    }
    
    rows = []
    for page in range(1, 101):
        payload = {
            "bizType": "selfOfficial_orderInfo_detail",
            "dataBatch": "content" if dimension == "内容" else "order",
            "ext": json.dumps(ext, ensure_ascii=False),
            "startTime": f"{start_date} 00:00:00",
            "endTime": f"{end_date} 23:59:59",
            "pageNo": page,
            "pageSize": 100
        }
        r = session.get(f"{BASE_URL}/api/report/multiscene/query/detail/data", params=payload, timeout=(10, 60))
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            break
        model = data.get("model") or {}
        items = model.get("list") if isinstance(model, dict) else (model if isinstance(model, list) else [])
        if not items:
            break
        for item in items:
            d_val = str(item.get("ds") or item.get("theDate") or "").strip().replace("/", "-")[:10]
            if start_date <= d_val <= end_date:
                item["日期"] = d_val
                # 规范指标字段
                for label, key in EFFECT_COLUMNS:
                    item[label] = item.get(key, "")
                rows.append(item)
        if len(items) < 100 or not model.get("hasNext"):
            break
        time.sleep(0.2)
    return rows
