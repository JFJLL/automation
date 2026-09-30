import json
import os
import requests
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.business_time import validate_keyword_date_range, now_business_tz
from core.models import KeywordFetchStatus, KeywordItemResult, KeywordBatchResult
from core.errors import (
    KeywordAuthExpiredError,
    KeywordUpstreamError,
    KeywordTimeoutError,
    KeywordInvalidResponseError,
    DataValidationError,
)

DEFAULT_TOKEN_FILE = Path(__file__).parent / "token.json"
API_URL = "https://ad.xiaohongshu.com/api/light/ad/keyword/analysis/distribution"

def sync_token_from_oss(force: bool = False) -> Optional[Dict[str, str]]:
    """通过 CredentialStore 获取最新的聚光 Token / Cookie 并持久化到本地 token.json"""
    try:
        from core.credentials import default_credential_store, calc_fingerprint
        from app.config import JUGUANG_V_SELLER_ID
    except Exception as import_err:
        print(f"[Keyword OSS Sync] Import config error: {import_err}")
        return None

    data = default_credential_store.get("juguang")
    if not data or not data.get("cookie"):
        data = default_credential_store.get("keyword_token")

    if not data or not data.get("cookie"):
        return None

    v_seller_id = data.get("v_seller_id") or data.get("vSellerId") or JUGUANG_V_SELLER_ID or os.getenv("JUGUANG_V_SELLER_ID", "")
    token_obj = {
        "cookie": data.get("cookie", ""),
        "v_seller_id": str(v_seller_id),
        "origin": "https://ad.xiaohongshu.com",
        "referer": f"https://ad.xiaohongshu.com/aurora/ad/tools/newKeywordTool?vSellerId={v_seller_id}",
        "user_agent": data.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
        "xsecappid": data.get("xsecappid", "aurora-shell")
    }
    try:
        DEFAULT_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_TOKEN_FILE.write_text(json.dumps(token_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        session_file = Path(__file__).parent.parent / "sync_console" / "tokens" / "session_headers.json"
        if session_file.parent.exists():
            session_file.write_text(json.dumps(token_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        fp = calc_fingerprint(token_obj.get("cookie", ""))
        print(f"[Keyword OSS Sync] Successfully auto-synced token (fingerprint={fp}, length={len(token_obj.get('cookie', ''))})")
        return token_obj
    except Exception as write_err:
        print(f"[Keyword OSS Sync] Write token error: {write_err}")
        return token_obj

def load_token(token_path: Optional[Path] = None) -> Dict[str, str]:
    path = token_path or DEFAULT_TOKEN_FILE
    if not path.exists():
        synced = sync_token_from_oss()
        if synced:
            return synced
        fallback = Path(__file__).parent.parent / "sync_console" / "tokens" / "session_headers.json"
        if fallback.exists():
            path = fallback
        else:
            raise KeywordAuthExpiredError(f"未找到聚光登录凭据文件 ({path})，且 OSS 自动同步未命中")
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def _fetch_single_word(
    keyword: str,
    start_date: str,
    end_date: str,
    token: Dict[str, str],
    dates: List[str]
) -> KeywordItemResult:
    v_seller_id = token.get("v_seller_id") or token.get("v-seller-id") or os.getenv("JUGUANG_V_SELLER_ID", "")
    cookie = token.get("cookie", "")
    
    headers = {
        "cookie": cookie,
        "origin": token.get("origin", "https://ad.xiaohongshu.com"),
        "referer": token.get("referer", f"https://ad.xiaohongshu.com/aurora/ad/tools/newKeywordTool?vSellerId={v_seller_id}"),
        "user-agent": token.get("user_agent") or token.get("user-agent", "Mozilla/5.0"),
        "content-type": "application/json",
        "xsecappid": token.get("xsecappid", "aurora-shell"),
        "v-seller-id": v_seller_id
    }
    
    columns = ["keywordSearchNum", "keywordAdsImpNum", "adsNoteNum", "keywordBid"]
    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "DAY",
        "columns": columns,
        "filters": [{
            "column": "searchWord",
            "operator": "in",
            "values": [keyword.strip()]
        }]
    }
    
    url = f"{API_URL}?vSellerId={v_seller_id}"
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 401:
            return KeywordItemResult(
                keyword=keyword,
                status=KeywordFetchStatus.AUTH_ERROR,
                error_code="401",
                error_message="小红书聚光登录凭据（Cookie）已过期"
            )
        if resp.status_code >= 500:
            return KeywordItemResult(
                keyword=keyword,
                status=KeywordFetchStatus.UPSTREAM_ERROR,
                error_code=str(resp.status_code),
                error_message=f"小红书服务器返回 HTTP {resp.status_code}"
            )
        resp.raise_for_status()
        try:
            res_json = resp.json()
        except Exception as json_err:
            return KeywordItemResult(
                keyword=keyword,
                status=KeywordFetchStatus.INVALID_RESPONSE,
                error_code="JSON_PARSE_ERROR",
                error_message=f"响应非合法 JSON: {json_err}"
            )
        
        code = res_json.get("code")
        if code in [401, 902]:
            msg = res_json.get("msg") or "登录凭据已过期"
            return KeywordItemResult(
                keyword=keyword,
                status=KeywordFetchStatus.AUTH_ERROR,
                error_code=str(code),
                error_message=f"小红书聚光登录凭据已过期: {msg}"
            )
            
        if not res_json.get("success"):
            msg = res_json.get("msg") or "获取关键词数据失败"
            if "登录" in msg or "过期" in msg:
                return KeywordItemResult(
                    keyword=keyword,
                    status=KeywordFetchStatus.AUTH_ERROR,
                    error_code=str(code or 401),
                    error_message=f"小红书聚光登录凭据已过期: {msg}"
                )
            return KeywordItemResult(
                keyword=keyword,
                status=KeywordFetchStatus.UPSTREAM_ERROR,
                error_code=str(code or 500),
                error_message=f"小红书接口错误: {msg}"
            )
            
        data_list = res_json.get("data", {}).get("dataList", [])
        if not data_list:
            # 官方接口请求成功，但该词在该日期范围内确实没有任何数据
            return KeywordItemResult(
                keyword=keyword,
                status=KeywordFetchStatus.EMPTY,
                data={},
                error_message=None
            )
            
        daily_data = {}
        for item in data_list:
            val_json = json.loads(item.get("dataValueJson") or "{}")
            day = val_json.get("detailDay") or val_json.get("time") or item.get("time")
            if not day:
                continue
                
            s_num = int(val_json.get("keywordSearchNum", 0) or 0)
            imp_num = int(val_json.get("keywordAdsImpNum", 0) or 0)
            note_num = int(val_json.get("adsNoteNum", 0) or 0)
            raw_bid = val_json.get("keywordBid")
            bid_val = float(raw_bid) if raw_bid not in (None, "", "-") else 0.0
            
            daily_data[str(day)[:10]] = {
                "search_num": s_num,
                "imp_num": imp_num,
                "note_num": note_num,
                "bid": bid_val
            }
            
        return KeywordItemResult(
            keyword=keyword,
            status=KeywordFetchStatus.SUCCESS,
            data=daily_data
        )
    except requests.Timeout:
        return KeywordItemResult(
            keyword=keyword,
            status=KeywordFetchStatus.TIMEOUT,
            error_code="TIMEOUT",
            error_message="请求小红书聚光超时"
        )
    except Exception as e:
        return KeywordItemResult(
            keyword=keyword,
            status=KeywordFetchStatus.UPSTREAM_ERROR,
            error_code="EXCEPTION",
            error_message=str(e)
        )

def fetch_keywords_insight(
    keywords: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    token_path: Optional[Path] = None,
    max_workers: int = 5,
    strict: bool = False
) -> Dict[str, Any]:
    """
    关键词深度分析检索（多关键词并发与可靠重试）：
    1. 通过统一 business_time.validate_keyword_date_range 验证日期范围
    2. 严格区分 success, empty, failed 状态，失败词绝不转换/填补成 0
    3. 遇到 401/902 自动从 OSS 刷新 Token 并重试一次，失败时抛出明确业务异常
    4. strict=True 用于定时同步和生成飞书表：只要任意关键词获取失败，整次直接报错，禁止部分成功覆盖
    """
    start_date_str, end_date_str, sorted_dates = validate_keyword_date_range(start_date, end_date)
    
    clean_kws = []
    seen = set()
    for kw in keywords:
        k = kw.strip()
        if k and k not in seen:
            seen.add(k)
            clean_kws.append(k)
            
    if not clean_kws:
        raise DataValidationError("关键词列表不能为空")
        
    token = load_token(token_path)
    
    def run_batch(token_dict: Dict[str, str], targets: List[str]) -> Dict[str, KeywordItemResult]:
        batch_res: Dict[str, KeywordItemResult] = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(targets))) as executor:
            future_map = {
                executor.submit(_fetch_single_word, kw, start_date_str, end_date_str, token_dict, sorted_dates): kw
                for kw in targets
            }
            for future in as_completed(future_map):
                kw = future_map[future]
                batch_res[kw] = future.result()
        return batch_res

    results = run_batch(token, clean_kws)
    
    # 如果有认证失败，触发一次 OSS 自动恢复重试
    auth_failed_words = [kw for kw, r in results.items() if r.status == KeywordFetchStatus.AUTH_ERROR]
    if auth_failed_words:
        print(f"[Keyword] Detected {len(auth_failed_words)} auth expired keywords, refreshing token from OSS...")
        new_token = sync_token_from_oss(force=True)
        if new_token:
            retry_res = run_batch(new_token, auth_failed_words)
            for kw, r in retry_res.items():
                results[kw] = r
        else:
            raise KeywordAuthExpiredError("小红书聚光登录凭据已过期，自动从 OSS 刷新失败")
            
    successful_kws = []
    empty_kws = []
    failed_kws = []
    all_data = {}
    
    for kw in clean_kws:
        item = results[kw]
        if item.status == KeywordFetchStatus.SUCCESS:
            successful_kws.append(kw)
            # 仅对于成功且有数据的关键词，缺失的日期填 0 (自然日补齐)
            kw_map = {}
            for d in sorted_dates:
                if d in item.data:
                    kw_map[d] = item.data[d]
                else:
                    kw_map[d] = {"search_num": 0, "imp_num": 0, "note_num": 0, "bid": 0.0}
            all_data[kw] = kw_map
        elif item.status == KeywordFetchStatus.EMPTY:
            empty_kws.append(kw)
            # 官方明确无数据的词，所有日期填 0
            all_data[kw] = {
                d: {"search_num": 0, "imp_num": 0, "note_num": 0, "bid": 0.0}
                for d in sorted_dates
            }
        else:
            failed_kws.append(kw)
            # 失败的词绝不写入 all_data，绝不填 0！
            all_data[kw] = None

    if strict and failed_kws:
        first_fail = results[failed_kws[0]]
        err_msg = f"关键词【{failed_kws[0]}】抓取失败 ({first_fail.error_message})，共 {len(failed_kws)} 个关键词失败，终止写入飞书"
        if first_fail.status == KeywordFetchStatus.AUTH_ERROR:
            raise KeywordAuthExpiredError(err_msg)
        elif first_fail.status == KeywordFetchStatus.TIMEOUT:
            raise KeywordTimeoutError(err_msg)
        else:
            raise KeywordUpstreamError(err_msg)
            
    if not successful_kws and not empty_kws:
        # 全部失败
        first_fail = results[failed_kws[0]] if failed_kws else None
        err_msg = f"所有关键词抓取均失败: {first_fail.error_message if first_fail else '未知错误'}"
        if first_fail and first_fail.status == KeywordFetchStatus.AUTH_ERROR:
            raise KeywordAuthExpiredError(err_msg)
        raise KeywordUpstreamError(err_msg)

    overall_status = "success" if not failed_kws else ("partial" if (successful_kws or empty_kws) else "failed")
    
    # 格式化 per-keyword 结果供前端展示
    keyword_statuses = {
        kw: {
            "status": results[kw].status.value,
            "error_message": results[kw].error_message,
            "error_code": results[kw].error_code
        }
        for kw in clean_kws
    }

    return {
        "success": bool(successful_kws or empty_kws),
        "overall_status": overall_status,
        "keywords": clean_kws,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "dates": sorted_dates,
        "data": all_data,
        "keyword_statuses": keyword_statuses,
        "successful_keywords": successful_kws,
        "empty_keywords": empty_kws,
        "failed_keywords": failed_kws
    }

def fetch_keyword_insight(
    keyword: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    token_path: Optional[Path] = None
) -> Dict[str, Any]:
    res = fetch_keywords_insight([keyword], start_date, end_date, token_path, strict=True)
    kw = res["keywords"][0]
    return {
        "success": True,
        "keyword": kw,
        "start_date": res["start_date"],
        "end_date": res["end_date"],
        "dates": res["dates"],
        "daily": res["data"].get(kw, {})
    }
