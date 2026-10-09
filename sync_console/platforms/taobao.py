import json
import time
import requests
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from pathlib import Path
from platforms.registry import fetch_oss_token
from app.config import ADSTAR_OSS_OBJECT_KEY, ADSTAR_OSS_BASE_URL, BASE_DIR
from core.models import ProviderFetchResult, ProviderFetchStatus
from core.errors import ProviderAuthError, ProviderUpstreamError

REPORT_BASE_URL = "https://adstar.alimama.com"

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
    candidates = [
        Path(os.getenv("TAOBAO_TOKEN_PATH", "")),
        BASE_DIR / "tokens" / "adstar.txt",
        BASE_DIR / "tokens" / "taobao_token.txt",
        BASE_DIR / "data" / "adstar.txt",
        BASE_DIR.parent / "feishu_three_sync" / "taobao" / "adstar.txt",
    ]
    for p in candidates:
        if p and p.exists() and p.is_file():
            raw = p.read_text(encoding="utf-8").strip()
            parsed = parse_cookie_payload(raw)
            if parsed:
                return parsed
    raise ProviderAuthError("淘宝星河 Cookie 未配置或无法从 OSS 获取")

def resolve_taobao_order_info(
    entity_id: str,
    session: requests.Session,
    tb_token: str
) -> Dict[str, Any]:
    eid = str(entity_id).strip()
    try:
        p = {
            "bizCode": "adstar",
            "_tb_token_": tb_token,
            "keyword": eid,
            "keywordType": 101,
            "pageNo": 1,
            "pageSize": 10
        }
        r = session.get(f"{REPORT_BASE_URL}/api/one/order/list", params=p, timeout=10)
        data = r.json()
        model = data.get("model", {})
        results = model.get("result", []) if isinstance(model, dict) else []
        for o in results:
            if (str(o.get("settleSeqId")) == eid or 
                str(o.get("displayOrderId")) == eid or 
                str(o.get("orderId")) == eid or
                str(o.get("buyOrderId")) == eid):
                return o
    except Exception as e:
        print(f"[Taobao] Search order list failed: {e}")

    try:
        r_get = session.get(
            f"{REPORT_BASE_URL}/api/one/order/get",
            params={"bizCode": "adstar", "_tb_token_": tb_token, "orderId": eid},
            timeout=10
        )
        if r_get.status_code == 200 and r_get.json().get("success"):
            m = r_get.json().get("model", {})
            if m:
                return m
    except Exception as e:
        print(f"[Taobao] Get order detail failed: {e}")

    return {}


def fetch_taobao_data(
    entity_id: str,
    dimension: str,
    start_date: str,
    end_date: str,
    cookies: Optional[Dict[str, str]] = None
) -> ProviderFetchResult:
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
    tb_token = cookies.get("_tb_token_", "")

    order_info = resolve_taobao_order_info(entity_id, session, tb_token)
    settle_seq_id = order_info.get("settleSeqId") or entity_id
    project_id = order_info.get("projectId") or 0
    sale_type = order_info.get("saleType") or 1
    biz_mode = order_info.get("businessMode") or 88
    media = order_info.get("media") or "RED_BOOK"

    ext = {
        "settleSeqId": int(settle_seq_id) if str(settle_seq_id).isdigit() else settle_seq_id,
        "projectId": int(project_id) if str(project_id).isdigit() else project_id,
        "media": media,
        "saleType": sale_type,
        "businessMode": biz_mode,
        "deliveryMode": "cptSeedDaily",
        "dataBatch": "content" if dimension == "内容" else "order",
        "flowType": "all",
        "cycleStr": "30",
    }
    
    rows = []
    pages_fetched = 0
    expected_pages = 1
    
    for page in range(1, 101):
        pages_fetched = page
        payload = {
            "bizCode": "adstar",
            "_tb_token_": tb_token,
            "bizType": "selfOfficial_orderInfo_detail",
            "dataBatch": "content" if dimension == "内容" else "order",
            "ext": json.dumps(ext, ensure_ascii=False),
            "startTime": f"{start_date} 00:00:00",
            "endTime": f"{end_date} 23:59:59",
            "pageNo": page,
            "pageSize": 100
        }
        try:
            r = session.get(f"{REPORT_BASE_URL}/api/report/multiscene/query/detail/data", params=payload, timeout=(10, 60))
            if r.status_code in (401, 403):
                raise ProviderAuthError("淘宝星河未授权或 Cookie 失效 (HTTP 401/403)")
            r.raise_for_status()
            data = r.json()
        except requests.Timeout:
            raise ProviderUpstreamError(f"淘宝星河请求第 {page} 页超时")
        except Exception as e:
            if isinstance(e, (ProviderAuthError, ProviderUpstreamError)):
                raise e
            raise ProviderUpstreamError(f"淘宝星河网络异常: {e}")
            
        info = data.get("info") or {}
        if info.get("message") == "nologin" or data.get("code") == 601:
            raise ProviderAuthError("淘宝星河登录会话已过期 (nologin)，请刷新更新凭据")
            
        if not data.get("success"):
            err_msg = info.get("message") or data.get("message") or f"code={data.get('code')}"
            raise ProviderUpstreamError(f"淘宝星河接口错误: {err_msg}")
            
        model = data.get("model") or {}
        items = (model.get("result") or model.get("list")) if isinstance(model, dict) else (model if isinstance(model, list) else [])
        if not items and page == 1:
            return ProviderFetchResult(status=ProviderFetchStatus.EMPTY, rows=[], pages_fetched=1)
            
        for item in items:
            d_val_raw = str(item.get("ds") or item.get("theDate") or "").strip().replace("/", "-").split(" ")[0]
            digits = "".join(c for c in d_val_raw if c.isdigit())
            d_val = f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}" if len(digits) == 8 else d_val_raw[:10]
            if start_date <= d_val <= end_date:
                item["日期"] = d_val
                # 映射标识与维度列
                if "orderId" in item:
                    item["任务ID"] = str(item.get("orderId", "")).strip()
                    item["订单ID"] = str(item.get("orderId", "")).strip()
                if "contentId" in item and item["contentId"] != "NULL":
                    item["内容ID"] = str(item.get("contentId", "")).strip()
                if "flowType" in item:
                    item["流量类型"] = str(item.get("flowType", "")).strip()
                if "cycle" in item:
                    item["归因口径"] = str(item.get("cycle", "")).strip()
                    item["归因周期"] = str(item.get("cycle", "")).strip()
                if "orderName" in item:
                    item["任务组名称"] = str(item.get("orderName", "")).strip()
                    item["任务名称"] = str(item.get("orderName", "")).strip()

                for label, key in EFFECT_COLUMNS:
                    item[label] = item.get(key, "")
                    if label == "新客进店UV":
                        item["新客进店uv"] = item.get(key, "")
                rows.append(item)
                
        if len(items) < 100 or not model.get("hasNext"):
            break
        time.sleep(0.15)
        
    status = ProviderFetchStatus.SUCCESS if rows else ProviderFetchStatus.EMPTY
    return ProviderFetchResult(
        status=status,
        rows=rows,
        pages_fetched=pages_fetched,
        expected_pages=pages_fetched
    )
