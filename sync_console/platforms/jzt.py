import io
import os
import requests
import configparser
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from platforms.registry import fetch_oss_token
from app.config import JZT_OSS_OBJECT_KEY, BASE_DIR

LOCAL_FALLBACK = BASE_DIR.parent / "feishu_three_sync" / "jzt_sync" / "token.txt"
REPORT_URL = "https://jzt-api.jd.com/jrw/content/outside/demand/report/downloadGrassDailyData"

def normalize_date_str(val: Any) -> str:
    s = str(val).strip().replace("/", "-").split(" ")[0]
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return s

def get_all_jzt_cookies() -> List[Tuple[str, str]]:
    cookies = []
    # 1. 优先从 OSS 读取
    if JZT_OSS_OBJECT_KEY:
        try:
            raw = fetch_oss_token(JZT_OSS_OBJECT_KEY)
            cfg = configparser.RawConfigParser()
            cfg.read_string(raw)
            for sec in cfg.sections():
                c = cfg.get(sec, "cookie", fallback="")
                if c:
                    cookies.append((sec, c))
        except Exception as e:
            print(f"[JZT] Read OSS token failed: {e}")

    # 2. 从本地降级读取
    if not cookies and LOCAL_FALLBACK.exists():
        try:
            cfg = configparser.RawConfigParser()
            cfg.read(LOCAL_FALLBACK, encoding="utf-8")
            for sec in cfg.sections():
                c = cfg.get(sec, "cookie", fallback="")
                if c:
                    cookies.append((sec, c))
        except Exception as e:
            print(f"[JZT] Read local fallback token failed: {e}")

    if not cookies:
        raise RuntimeError("京准通 Cookie 未配置或无法从 OSS / 本地获取")
    return cookies

def fetch_jzt_data(task_id: str, start_date: str, end_date: str, cookie: Optional[str] = None) -> List[Dict[str, Any]]:
    cookie_list = [(None, cookie)] if cookie else get_all_jzt_cookies()
    
    # 格式化日期参数为统一格式
    start_norm = normalize_date_str(start_date)
    end_norm = normalize_date_str(end_date)
    
    last_error = None
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
            if r.status_code == 200 and r.content[:2] in (b"PK", b"\xd0\xcf"):
                df = pd.read_excel(io.BytesIO(r.content))
                if not df.empty:
                    # 归一化日期列
                    records = df.to_dict(orient="records")
                    clean_records = []
                    for row in records:
                        d_val = normalize_date_str(row.get("日期", ""))
                        if start_norm <= d_val <= end_norm:
                            row["日期"] = d_val
                            clean_records.append(row)
                    # 命中返回有效数据
                    return clean_records
        except Exception as e:
            last_error = e

    return []
