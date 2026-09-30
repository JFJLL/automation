import io
import os
import requests
import configparser
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from platforms.registry import fetch_oss_token
from app.config import JZT_OSS_OBJECT_KEY, BASE_DIR
from core.models import ProviderFetchResult, ProviderFetchStatus
from core.errors import ProviderAuthError, ProviderUpstreamError

REPORT_URL = "https://jzt-api.jd.com/jrw/content/outside/demand/report/downloadGrassDailyData"

def normalize_date_str(val: Any) -> str:
    s = str(val).strip().replace("/", "-").split(" ")[0]
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return s

def get_all_jzt_cookies() -> List[Tuple[str, str]]:
    cookies = []
    # 1. 优先从 CredentialStore 读取
    from core.credentials import default_credential_store
    cred = default_credential_store.get("jzt")
    if cred:
        raw = cred.get("cookie") or cred.get("token") or ""
        if raw:
            try:
                cfg = configparser.RawConfigParser()
                cfg.read_string(raw)
                for sec in cfg.sections():
                    c = cfg.get(sec, "cookie", fallback="")
                    if c:
                        cookies.append((sec, c))
            except Exception as e:
                print(f"[JZT] Parse credential token failed: {e}")

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

def fetch_jzt_data(task_id: str, start_date: str, end_date: str, cookie: Optional[str] = None) -> ProviderFetchResult:
    cookie_list = [(None, cookie)] if cookie else get_all_jzt_cookies()
    
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
            taskId=str(task_id), dataCycle="30", cateId="", brandId="6731", mediaTaskId="",
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

