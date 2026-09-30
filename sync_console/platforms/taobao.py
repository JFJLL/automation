import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

import requests
from app.config import BASE_DIR
from core.errors import ProviderAuthError, ProviderUpstreamError
from core.models import ProviderFetchResult, ProviderFetchStatus

REPORT_BASE_URL = "https://adstar.alimama.com"

EFFECT_COLUMNS = [
    ("阅读/播放UV", "readUv1d"),
    ("点赞UV", "likeUv1d"),
    ("评论UV", "commentUv1d"),
    ("收藏UV", "favorUv1d"),
    ("转发UV", "forwardUv1d"),
    ("互动UV", "interactiveUv1d"),
    ("内容互动率", "interactiveRate1d"),
    ("搜索曝光UV", "searchIpvUv1d"),
    ("搜索进店UV", "searchGuideShopUv1d"),
    ("进店UV", "guideShopUv1d"),
    ("新客进店uv", "guideShopNewUv1d"),
    ("商品收藏UV", "favorItemUv1d"),
    ("商品加购UV", "cartItemUv1d"),
    ("关注店铺UV", "followShopUv1d"),
    ("店铺会员UV", "memberShopUv1d"),
    ("成交UV", "tradeUv1d"),
    ("商家GMV", "alipayShopAmt1d"),
    ("订单商品成交GMV", "alipayItemAmt1d"),
    ("非订单商品成交GMV", "alipayOtherItemAmt1d"),
    ("新客成交UV", "alipayShopNewUv1d"),
    ("订单商品新客成交GMV", "alipayItemNewAmt1d"),
    ("预售付定GMV", "alipayPreAmt1d"),
    ("预售整单预估GMV", "alipayPreAllAmt1d"),
    ("预售付定UV", "alipayPreUv1d"),
    ("成交转化率", "alipayRate1d"),
    ("达人昵称", "kolNick"),
    ("内容链接", "detailUrl"),
    ("订单名称", "orderName")
]

def parse_cookie_payload(raw: str) -> Dict[str, str]:
    if not raw or not raw.strip():
        return {}
    raw = raw.strip()
    if raw.startswith("{") and raw.endswith("}"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if "cookie" in data:
                    raw = data["cookie"]
                else:
                    return data
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
    from core.credentials import default_credential_store
    cred = default_credential_store.get("adstar")
    if cred:
        raw = cred.get("cookie") or cred.get("token") or ""
        parsed = parse_cookie_payload(raw)
        if parsed:
            return parsed
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
    pages_fetched = 0
    seen_page_fingerprints = set()
    MAX_PAGES = 100

    for page in range(1, MAX_PAGES + 1):
        pages_fetched = page
        payload = {
            "bizType": "selfOfficial_orderInfo_detail",
            "dataBatch": "content" if dimension == "内容" else "order",
            "ext": json.dumps(ext, ensure_ascii=False),
            "startTime": f"{start_date} 00:00:00",
            "endTime": f"{end_date} 23:59:59",
            "pageNo": page,
            "pageSize": 100
        }

        data = None
        for attempt in range(3):
            try:
                r = session.get(f"{REPORT_BASE_URL}/api/report/multiscene/query/detail/data", params=payload, timeout=(10, 60))
                if r.status_code in (401, 403):
                    raise ProviderAuthError("淘宝星河未授权或 Cookie 失效 (HTTP 401/403)")
                r.raise_for_status()
                data = r.json()
                break
            except requests.Timeout:
                if attempt == 2:
                    raise ProviderUpstreamError(f"淘宝星河请求第 {page} 页超时")
            except Exception as e:
                if isinstance(e, ProviderAuthError):
                    raise e
                if attempt == 2:
                    raise ProviderUpstreamError(f"淘宝星河网络异常: {e}")
            time.sleep(0.3 * (attempt + 1))

        if not data:
            raise ProviderUpstreamError(f"淘宝星河第 {page} 页未获取到有效数据")

        info = data.get("info") or {}
        if info.get("message") == "nologin" or data.get("code") in (401, 403, 601):
            raise ProviderAuthError("淘宝星河登录会话已过期 (nologin)，请刷新更新凭据")

        if not data.get("success"):
            err_msg = info.get("message") or data.get("message") or f"code={data.get('code')}"
            raise ProviderUpstreamError(f"淘宝星河接口错误: {err_msg}")

        model = data.get("model") or {}
        items = model.get("list") if isinstance(model, dict) else (model if isinstance(model, list) else [])
        if not items and page == 1:
            return ProviderFetchResult(status=ProviderFetchStatus.EMPTY, rows=[], pages_fetched=1)

        # 重复页检测
        page_fp = hashlib.sha256(json.dumps(items, sort_keys=True).encode("utf-8")).hexdigest()
        if page_fp in seen_page_fingerprints and items:
            return ProviderFetchResult(status=ProviderFetchStatus.PARTIAL, rows=rows, pages_fetched=pages_fetched, error_message="检测到重复页数据，判定为异常并返回 PARTIAL")
        seen_page_fingerprints.add(page_fp)

        for item in items:
            d_val = str(item.get("ds") or item.get("theDate") or "").strip().replace("/", "-")[:10]
            if start_date <= d_val <= end_date:
                item["日期"] = d_val
                for label, key in EFFECT_COLUMNS:
                    item[label] = item.get(key, "")
                rows.append(item)

        has_next = model.get("hasNext", False) if isinstance(model, dict) else False
        total = model.get("total", 0) if isinstance(model, dict) else 0

        # 达到上限且仍有数据未拉取完整
        if page == MAX_PAGES and (has_next or (total and len(rows) < total)):
            return ProviderFetchResult(
                status=ProviderFetchStatus.PARTIAL,
                rows=rows,
                pages_fetched=pages_fetched,
                expected_pages=MAX_PAGES,
                error_message=f"分页达到上限 {MAX_PAGES} 且仍有后续数据，返回 PARTIAL"
            )

        if len(items) < 100 or not has_next:
            break
        time.sleep(0.15)

    status = ProviderFetchStatus.SUCCESS if rows else ProviderFetchStatus.EMPTY
    return ProviderFetchResult(
        status=status,
        rows=rows,
        pages_fetched=pages_fetched,
        expected_pages=pages_fetched
    )
