import io
import os
import time
import json
import requests
import configparser
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from platforms.registry import fetch_oss_token
from app.config import JZT_OSS_OBJECT_KEY, JZT_OSS_SUBACCOUNT_PREFIX, BASE_DIR
from core.models import ProviderFetchResult, ProviderFetchStatus
from core.errors import ProviderAuthError, ProviderUpstreamError

REPORT_URL = "https://jzt-api.jd.com/jrw/content/outside/demand/report/downloadGrassDailyData"

_task_cookie_cache: Dict[str, Tuple[str, str]] = {}
_jzt_subaccounts_cache = {"timestamp": 0.0, "data": []}

def normalize_date_str(val: Any) -> str:
    s = str(val).strip().replace("/", "-").split(" ")[0]
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return s

def get_jzt_subaccount_cookie(sub_account_id: str) -> Optional[str]:
    sub_id = str(sub_account_id).strip()
    if not sub_id:
        return None
    # 1. 优先直接从 OSS 读取独立数字命名凭据 token/jzt/{sub_id}.txt
    prefix = (JZT_OSS_SUBACCOUNT_PREFIX or "token/jzt/").rstrip("/")
    for oss_k in [f"{prefix}/{sub_id}.txt", f"token/jzt/{sub_id}.txt"]:
        try:
            raw = fetch_oss_token(oss_k).strip()
            if raw:
                return raw
        except Exception:
            pass

    # 2. 从本地 tokens / data 读取
    for candidate in [BASE_DIR / "tokens" / f"{sub_id}.txt", BASE_DIR / "data" / f"{sub_id}.txt"]:
        if candidate.exists() and candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8").strip()
            except Exception:
                pass
    return None

def get_jzt_subaccounts_list(force_refresh: bool = False) -> List[Dict[str, Any]]:
    global _jzt_subaccounts_cache
    now = time.time()
    if not force_refresh and _jzt_subaccounts_cache["data"] and (now - _jzt_subaccounts_cache["timestamp"] < 60):
        return _jzt_subaccounts_cache["data"]

    prefix = (JZT_OSS_SUBACCOUNT_PREFIX or "token/jzt/").rstrip("/")
    for meta_key in [f"{prefix}/subaccounts_meta.json", "token/jzt/subaccounts_meta.json"]:
        try:
            raw = fetch_oss_token(meta_key).strip()
            if raw:
                items = json.loads(raw)
                subaccounts = []
                for it in items:
                    sid = str(it.get("userId") or it.get("id") or "").strip()
                    sname = str(it.get("nickname") or it.get("pin") or "").strip()
                    company = str(it.get("company") or "").strip()
                    if sid and sname:
                        subaccounts.append({
                            "id": sid,
                            "name": f"{sname} ({company})" if company and company != sname else sname,
                            "pin": it.get("pin"),
                            "company": company
                        })
                if subaccounts:
                    _jzt_subaccounts_cache = {"timestamp": now, "data": subaccounts}
                    return subaccounts
        except Exception:
            pass

    return _jzt_subaccounts_cache["data"]

def get_all_jzt_cookies() -> List[Tuple[str, str]]:
    cookies = []
    # 1. 优先从 OSS 读取汇总 INI 凭据文件 (token/jzt/jzt_token.txt)
    candidate_oss_keys = [
        JZT_OSS_OBJECT_KEY,
        "token/jzt/jzt_token.txt",
        "KOL/jzt_token.txt"
    ]
    for oss_k in candidate_oss_keys:
        if not oss_k:
            continue
        try:
            raw = fetch_oss_token(oss_k)
            if raw and raw.strip():
                cfg = configparser.RawConfigParser()
                cfg.read_string(raw)
                for sec in cfg.sections():
                    c = cfg.get(sec, "cookie", fallback="")
                    if c:
                        cookies.append((sec, c))
                if cookies:
                    break
        except Exception:
            pass

    # 2. 从本地规范凭据目录读取
    if not cookies:
        candidates = [
            Path(os.getenv("JZT_TOKEN_PATH", "")),
            BASE_DIR / "tokens" / "jzt_token.txt",
            BASE_DIR / "tokens" / "token.txt",
            BASE_DIR / "data" / "jzt_token.txt",
            BASE_DIR / "data" / "token.txt",
            BASE_DIR.parent / "feishu_three_sync" / "jzt_sync" / "token.txt",
        ]
        for p in candidates:
            if p and p.exists() and p.is_file():
                try:
                    cfg = configparser.RawConfigParser()
                    cfg.read(p, encoding="utf-8")
                    for sec in cfg.sections():
                        c = cfg.get(sec, "cookie", fallback="")
                        if c:
                            cookies.append((sec, c))
                    if cookies:
                        break
                except Exception as e:
                    print(f"[JZT] Read candidate {p} failed: {e}")

    if not cookies:
        raise ProviderAuthError("京准通 Cookie 未配置或无法从 OSS / 本地获取")
    return cookies

def fetch_jzt_data(
    task_id: str,
    start_date: str,
    end_date: str,
    cookie: Optional[str] = None,
    sub_account_id: Optional[str] = None
) -> ProviderFetchResult:
    clean_task_id = str(task_id).strip()
    if clean_task_id.endswith(".0"):
        clean_task_id = clean_task_id[:-2]

    if cookie:
        cookie_list = [(None, cookie)]
    elif sub_account_id:
        sub_c = get_jzt_subaccount_cookie(sub_account_id)
        if sub_c:
            cookie_list = [(str(sub_account_id), sub_c)]
        else:
            cookie_list = get_all_jzt_cookies()
    else:
        all_cookies = get_all_jzt_cookies()
        if clean_task_id in _task_cookie_cache:
            cached_pair = _task_cookie_cache[clean_task_id]
            cookie_list = [cached_pair] + [c for c in all_cookies if c[0] != cached_pair[0]]
        else:
            cookie_list = all_cookies
    
    start_norm = normalize_date_str(start_date)
    end_norm = normalize_date_str(end_date)
    
    last_error: Optional[Exception] = None
    for sec_name, c in cookie_list:
        session = requests.Session()
        session.trust_env = False
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
            "Cookie": c
        })
        payload = dict(
            taskId=clean_task_id, dataCycle="30", cateId="", brandId="6731", mediaTaskId="",
            mediaOrderId="", contentId="", campaignId="", unitId="", creativeId="", type="2",
            dataScope="2", dimension="2", dataCaliber="0", attributionTouchType="1",
            trafficSource="1", pageIndex="1"
        )
        try:
            r = session.post(REPORT_URL, data=payload, timeout=(10, 60))
            if r.status_code in (401, 403):
                last_error = ProviderAuthError(f"京准通返回 HTTP {r.status_code}，登录凭据已失效")
                continue
            if r.status_code >= 500:
                last_error = ProviderUpstreamError(f"京准通服务器返回 HTTP {r.status_code}")
                continue
            r.raise_for_status()
            
            # 判断返回内容是否为有效 Excel
            if r.content[:2] in (b"PK", b"\xd0\xcf"):
                df = pd.read_excel(io.BytesIO(r.content))
                if df.empty:
                    return ProviderFetchResult(status=ProviderFetchStatus.EMPTY, rows=[], pages_fetched=1)
                
                records = df.to_dict(orient="records")
                clean_records = []
                for row in records:
                    d_val = normalize_date_str(row.get("日期", ""))
                    if start_norm <= d_val <= end_norm:
                        row["日期"] = d_val
                        clean_records.append(row)
                
                if clean_records:
                    if sec_name and c:
                        _task_cookie_cache[clean_task_id] = (sec_name, c)
                    return ProviderFetchResult(status=ProviderFetchStatus.SUCCESS, rows=clean_records, pages_fetched=1)
                else:
                    return ProviderFetchResult(status=ProviderFetchStatus.EMPTY, rows=[], pages_fetched=1)
            else:
                # 响应为 HTML 或 JSON 错误信息
                text_prefix = r.text[:200].lower()
                if "<html" in text_prefix or "login" in text_prefix or "passport" in text_prefix:
                    last_error = ProviderAuthError("京准通返回登录跳转页面，Cookie 已过期")
                else:
                    last_error = ProviderUpstreamError(f"京准通返回非 Excel 内容: {r.text[:150]}")
        except Exception as e:
            last_error = e

    if last_error:
        if isinstance(last_error, (ProviderAuthError, ProviderUpstreamError)):
            raise last_error
        raise ProviderUpstreamError(f"京准通接口请求失败: {last_error}")
        
    return ProviderFetchResult(status=ProviderFetchStatus.EMPTY, rows=[], pages_fetched=0)
