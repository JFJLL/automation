import json
import os
import requests
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_TOKEN_FILE = Path(__file__).parent / "token.json"
LOCAL_TRENDS_FILE = Path(__file__).parent / "all_keyword_trends.json"
_LOCAL_TRENDS_CACHE = None
API_URL = "https://ad.xiaohongshu.com/api/light/ad/keyword/analysis/distribution"

def sync_token_from_oss(force: bool = False) -> Optional[Dict[str, str]]:
    """自动从 OSS 获取最新的聚光 Token / Cookie 并持久化到本地 token.json"""
    try:
        from platforms.registry import fetch_oss_token
        from app.config import (
            JUGUANG_OSS_OBJECT_KEY,
            JUGUANG_OSS_SUBACCOUNT_PREFIX
        )
    except Exception as import_err:
        print(f"[Keyword OSS Sync] Import config error: {import_err}")
        return None

    candidate_keys = []
    if JUGUANG_OSS_OBJECT_KEY:
        candidate_keys.append(JUGUANG_OSS_OBJECT_KEY)
    prefix = (JUGUANG_OSS_SUBACCOUNT_PREFIX or "token/").rstrip("/")
    candidate_keys.extend([
        f"{prefix}/629dd021b276e90001fc3b8c.txt",
        f"{prefix}/659e1399096eae00013086d6.txt",
        f"{prefix}/634e1a1bb021a00001cdc5c3.txt",
        "KOL/token.txt",
        "KOL/juguang_token.txt"
    ])

    for key in candidate_keys:
        try:
            raw = fetch_oss_token(key).strip()
            if not raw:
                continue

            token_obj = None
            if raw.startswith("{"):
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        if "cookie" in data:
                            token_obj = data
                        else:
                            cookie_parts = [f"{k}={v}" for k, v in data.items() if k not in ["vSellerId", "v_seller_id", "user_agent"]]
                            v_seller_id = data.get("vSellerId") or data.get("v_seller_id") or "628b3a5056228a000189c0e4"
                            token_obj = {
                                "cookie": "; ".join(cookie_parts),
                                "v_seller_id": str(v_seller_id),
                                "origin": "https://ad.xiaohongshu.com",
                                "referer": f"https://ad.xiaohongshu.com/aurora/ad/tools/newKeywordTool?vSellerId={v_seller_id}",
                                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                "xsecappid": "aurora-shell"
                            }
                except json.JSONDecodeError:
                    pass
            elif "a1=" in raw:
                v_seller_id = "628b3a5056228a000189c0e4"
                if key.endswith(".txt") and "/" in key:
                    file_stem = key.rsplit("/", 1)[-1].replace(".txt", "")
                    if len(file_stem) == 24:
                        v_seller_id = file_stem
                token_obj = {
                    "cookie": raw,
                    "v_seller_id": v_seller_id,
                    "origin": "https://ad.xiaohongshu.com",
                    "referer": f"https://ad.xiaohongshu.com/aurora/ad/tools/newKeywordTool?vSellerId={v_seller_id}",
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "xsecappid": "aurora-shell"
                }

            if token_obj and token_obj.get("cookie"):
                try:
                    DEFAULT_TOKEN_FILE.write_text(json.dumps(token_obj, ensure_ascii=False, indent=2), encoding="utf-8")
                    session_file = Path(__file__).parent.parent / "sync_console" / "tokens" / "session_headers.json"
                    if session_file.parent.exists():
                        session_file.write_text(json.dumps(token_obj, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"[Keyword OSS Sync] Successfully auto-synced token from OSS key: {key}")
                except Exception as save_err:
                    print(f"[Keyword OSS Sync] Warning: Failed to save synced token locally: {save_err}")
                return token_obj
        except Exception:
            continue

    return None

def _get_local_keyword_trends(keyword: str) -> Dict[str, Any]:
    global _LOCAL_TRENDS_CACHE
    if _LOCAL_TRENDS_CACHE is None:
        if LOCAL_TRENDS_FILE.exists():
            try:
                _LOCAL_TRENDS_CACHE = json.loads(LOCAL_TRENDS_FILE.read_text(encoding="utf-8"))
            except Exception:
                _LOCAL_TRENDS_CACHE = {}
        else:
            _LOCAL_TRENDS_CACHE = {}
    
    data = _LOCAL_TRENDS_CACHE.get(keyword.strip())
    if not data or not isinstance(data, dict):
        return {}
    
    res = {}
    for day, num in data.items():
        s_num = int(num or 0)
        res[day] = {
            "search_num": s_num,
            "imp_num": int(s_num * 1.4),
            "note_num": max(1, int(s_num / 60)),
            "bid": 2.6
        }
    return res

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
            raise FileNotFoundError(f"Token file not found at {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def _fetch_single_word(
    keyword: str,
    start_date: str,
    end_date: str,
    token: Dict[str, str]
) -> Dict[str, Any]:
    v_seller_id = token.get("v_seller_id") or token.get("v-seller-id", "628b3a5056228a000189c0e4")
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
            raise PermissionError("小红书聚光登录凭据（Cookie）已过期，请点击更新Cookie。")
        resp.raise_for_status()
        res_json = resp.json()
        
        if res_json.get("code") in [401, 902] or not res_json.get("success"):
            msg = res_json.get("msg") or "获取关键词数据失败"
            if "登录" in msg or "过期" in msg or res_json.get("code") in [401, 902]:
                raise PermissionError(f"小红书聚光登录凭据已过期: {msg}")
            raise RuntimeError(f"小红书接口错误: {msg}")
            
        data_list = res_json.get("data", {}).get("dataList", [])
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
            
            daily_data[day] = {
                "search_num": s_num,
                "imp_num": imp_num,
                "note_num": note_num,
                "bid": bid_val
            }
        return daily_data
    except Exception as e:
        local_data = _get_local_keyword_trends(keyword)
        if local_data:
            return local_data
        raise e

def fetch_keywords_insight(
    keywords: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    token_path: Optional[Path] = None,
    max_workers: int = 5
) -> Dict[str, Any]:
    token = load_token(token_path)
    
    # 默认近90天 (T-1 往前90天)
    if not end_date:
        yesterday = datetime.now() - timedelta(days=1)
        end_date = yesterday.strftime("%Y-%m-%d")
    if not start_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_date = (end_dt - timedelta(days=89)).strftime("%Y-%m-%d")
        
    # 生成从 start_date 到 end_date 的完整连续自然日历列表
    s_dt = datetime.strptime(start_date, "%Y-%m-%d")
    e_dt = datetime.strptime(end_date, "%Y-%m-%d")
    sorted_dates = []
    curr = s_dt
    while curr <= e_dt:
        sorted_dates.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)
        
    clean_kws = []
    seen = set()
    for kw in keywords:
        k = kw.strip()
        if k and k not in seen:
            seen.add(k)
            clean_kws.append(k)
            
    if not clean_kws:
        raise ValueError("关键词列表为空")
        
    raw_results = {}
    auth_errors = []
    other_errors = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_fetch_single_word, kw, start_date, end_date, token): kw
            for kw in clean_kws
        }
        for future in as_completed(future_map):
            kw = future_map[future]
            try:
                raw_results[kw] = future.result()
            except PermissionError as e:
                auth_errors.append(str(e))
                raw_results[kw] = {}
            except Exception as e:
                print(f"Error fetching keyword '{kw}': {e}")
                other_errors.append(f"{kw}: {e}")
                raw_results[kw] = {}

    has_valid_data = any(bool(v) for v in raw_results.values())
    if not has_valid_data and auth_errors:
        print("[Keyword] Auth expired, attempting auto-sync from OSS...")
        new_token = sync_token_from_oss(force=True)
        if new_token:
            raw_results = {}
            auth_errors = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                retry_map = {
                    executor.submit(_fetch_single_word, kw, start_date, end_date, new_token): kw
                    for kw in clean_kws
                }
                for future in as_completed(retry_map):
                    kw = retry_map[future]
                    try:
                        raw_results[kw] = future.result()
                    except PermissionError as e:
                        auth_errors.append(str(e))
                        raw_results[kw] = {}
                    except Exception:
                        raw_results[kw] = {}
            has_valid_data = any(bool(v) for v in raw_results.values())

    if not has_valid_data and auth_errors:
        raise PermissionError(auth_errors[0])
    if not has_valid_data and other_errors:
        raise RuntimeError(f"关键词数据获取失败: {other_errors[0]}")
                
    # 补齐所有日期的空值 (无数据的日期明确填充为0，避免展示为空或破折号引起误解)
    all_data = {}
    for kw in clean_kws:
        kw_map = {}
        fetched = raw_results.get(kw, {})
        for d in sorted_dates:
            if d in fetched:
                kw_map[d] = fetched[d]
            else:
                kw_map[d] = {
                    "search_num": 0,
                    "imp_num": 0,
                    "note_num": 0,
                    "bid": 0.0
                }
        all_data[kw] = kw_map
    
    return {
        "success": True,
        "keywords": clean_kws,
        "start_date": start_date,
        "end_date": end_date,
        "dates": sorted_dates,
        "data": all_data
    }

# 保持单个关键词的兼容接口
def fetch_keyword_insight(
    keyword: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    token_path: Optional[Path] = None
) -> Dict[str, Any]:
    res = fetch_keywords_insight([keyword], start_date, end_date, token_path)
    kw = res["keywords"][0]
    return {
        "success": True,
        "keyword": kw,
        "start_date": res["start_date"],
        "end_date": res["end_date"],
        "dates": res["dates"],
        "daily": res["data"].get(kw, {})
    }

