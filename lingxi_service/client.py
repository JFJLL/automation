import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

DEFAULT_TOKEN_FILE = Path(__file__).parent / "token.json"
API_URL = "https://idea.xiaohongshu.com/api/idea/audience/group/tag/search"

def sync_token_from_oss(force: bool = False) -> Optional[Dict[str, str]]:
    """从 CredentialStore 获取最新的灵犀 Token / Cookie 并持久化到本地 token.json"""
    try:
        from core.credentials import calc_fingerprint, default_credential_store
    except Exception as import_err:
        print(f"[Lingxi OSS Sync] Import config error: {import_err}")
        return None

    data = default_credential_store.get("lingxi")
    if not data or not data.get("cookie"):
        return None

    token_obj = {
        "cookie": data.get("cookie", ""),
        "origin": data.get("origin", "https://idea.xiaohongshu.com"),
        "referer": data.get("referer", "https://idea.xiaohongshu.com/idea/creativity/audience/create"),
        "user_agent": data.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"),
        "xsecappid": data.get("xsecappid", "ads-idea")
    }
    try:
        DEFAULT_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_TOKEN_FILE.write_text(json.dumps(token_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        fp = calc_fingerprint(token_obj.get("cookie", ""))
        print(f"[Lingxi OSS Sync] Successfully synced token (fingerprint={fp}, length={len(token_obj.get('cookie', ''))})")
        return token_obj
    except Exception as e:
        print(f"[Lingxi OSS Sync] Write token error: {e}")
        return token_obj

def load_token(token_path: Optional[Path] = None) -> Dict[str, str]:
    path = token_path or DEFAULT_TOKEN_FILE
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("cookie"):
                    return data
        except Exception:
            pass

    oss_data = sync_token_from_oss()
    if oss_data and oss_data.get("cookie"):
        return oss_data

    return {
        "cookie": "",
        "origin": "https://idea.xiaohongshu.com",
        "referer": "https://idea.xiaohongshu.com/idea/creativity/audience/create",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "xsecappid": "ads-idea"
    }

def _fetch_single_word(kw: str, token_dict: Dict[str, str], timeout: int = 15) -> Dict[str, Any]:
    """
    调用小红书灵犀人群标签-搜索关键词接口
    返回该词自身覆盖人数，以及智能推荐的相关词和人数
    """
    cookie = token_dict.get("cookie", "")
    headers = {
        "Cookie": cookie,
        "Origin": token_dict.get("origin", "https://idea.xiaohongshu.com"),
        "Referer": token_dict.get("referer", "https://idea.xiaohongshu.com/idea/creativity/audience/create"),
        "xsecappid": token_dict.get("xsecappid", "ads-idea"),
        "User-Agent": token_dict.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
        "Content-Type": "application/json"
    }
    payload = {
        "encode": "17",
        "searchKey": kw,
        "extra": {
            "router": "keyword_rec",
            "encode": "17"
        }
    }

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return {
                "keyword": kw,
                "status": "upstream_error",
                "message": f"HTTP {resp.status_code}",
                "user_cnt": 0,
                "recommend_words": []
            }
        data = resp.json()
        AUTH_CODES = {401, 403, 601, 902, 100001}
        code = data.get("code")
        if resp.status_code in (401, 403) or code in AUTH_CODES:
            msg = data.get("msg") or "登录凭据已过期"
            return {
                "keyword": kw,
                "status": "auth_expired",
                "message": msg,
                "user_cnt": 0,
                "recommend_words": []
            }

        if data.get("code") != 0 or not data.get("success"):
            msg = data.get("msg") or "请求失败"
            return {
                "keyword": kw,
                "status": "failed",
                "message": msg,
                "user_cnt": 0,
                "recommend_words": []
            }

        items = data.get("data") or []
        target_user_cnt = 0
        found_exact = False
        rec_words = []

        for it in items:
            word_name = it.get("key") or it.get("value") or ""
            cnt_str = it.get("extra", {}).get("user_cnt", "0")
            try:
                cnt = int(cnt_str)
            except Exception:
                cnt = 0
            if word_name == kw:
                target_user_cnt = cnt
                found_exact = True
            else:
                rec_words.append({"keyword": word_name, "user_cnt": cnt})

        if not found_exact and items:
            # 若首项即为搜索词但空格/大小写有微小出入，取首项
            first_name = items[0].get("key") or items[0].get("value") or ""
            if first_name.strip() == kw.strip():
                try:
                    target_user_cnt = int(items[0].get("extra", {}).get("user_cnt", "0"))
                    found_exact = True
                except Exception:
                    pass

        return {
            "keyword": kw,
            "status": "success",
            "message": "ok",
            "user_cnt": target_user_cnt,
            "recommend_words": rec_words
        }
    except requests.Timeout:
        return {
            "keyword": kw,
            "status": "timeout",
            "message": "请求超时",
            "user_cnt": 0,
            "recommend_words": []
        }
    except Exception as e:
        return {
            "keyword": kw,
            "status": "error",
            "message": str(e),
            "user_cnt": 0,
            "recommend_words": []
        }

def fetch_lingxi_keywords(keywords: List[str], max_workers: int = 5) -> Dict[str, Any]:
    """批量抓取灵犀搜索关键词覆盖人群"""
    token = load_token()
    if not token.get("cookie"):
        # 尝试同步一次
        token = sync_token_from_oss() or token

    results: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_kw = {executor.submit(_fetch_single_word, kw, token): kw for kw in keywords}
        for future in as_completed(future_to_kw):
            kw = future_to_kw[future]
            try:
                res = future.result()
                results[kw] = res
            except Exception as e:
                results[kw] = {
                    "keyword": kw,
                    "status": "error",
                    "message": str(e),
                    "user_cnt": 0,
                    "recommend_words": []
                }

    # 统计成功与失败
    successful = [kw for kw, r in results.items() if r["status"] == "success"]
    failed = [kw for kw, r in results.items() if r["status"] != "success"]
    return {
        "results": results,
        "successful_keywords": successful,
        "failed_keywords": failed,
        "total": len(keywords)
    }
