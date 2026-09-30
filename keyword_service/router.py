import os
import sys
import json
import hmac
import math
from pathlib import Path
from typing import Optional, List, Union, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from keyword_service.client import fetch_keywords_insight, load_token
from keyword_service.db import get_db
from keyword_service.sync_engine import (
    direct_create_feishu_sheet,
    create_keyword_task,
    run_keyword_task,
    append_keywords_to_task,
    remove_keywords_from_task
)
from core.scheduler_manager import SchedulerManager
from core.security import require_admin, require_auth, create_admin_session, is_admin_authenticated
from core.errors import (
    AppError,
    TaskNotFoundError,
    TaskAlreadyRunningError,
    DataValidationError,
    InvalidDateRangeError
)
from app.config import ACCESS_TOKEN

router = APIRouter()
private_router = APIRouter(prefix="/api/keyword")

HTML_PATH = Path(__file__).parent / "templates" / "keyword.html"
KEYWORD_LIBRARY_PATH = Path(__file__).parent / "all_keyword_trends.json"

class KeywordSearchRequest(BaseModel):
    keywords: Union[str, List[str]]
    start_date: Optional[str] = None
    end_date: Optional[str] = None

class DirectSheetRequest(BaseModel):
    title: Optional[str] = None
    keywords: List[str]
    start_date: Optional[str] = None
    end_date: Optional[str] = None

class CreateKeywordTaskRequest(BaseModel):
    task_name: str
    keywords: List[str]
    update_mode: str = "overwrite" # 'overwrite' 或 'append'
    rrule: str = "FREQ=DAILY;BYHOUR=12;BYMINUTE=30"
    days_range: int = 90

class AppendKeywordsRequest(BaseModel):
    keywords: Union[str, List[str]]
    sync_now: bool = False

class RemoveKeywordsRequest(BaseModel):
    keywords: Union[str, List[str]]

class CookieUpdateRequest(BaseModel):
    cookie: str
    v_seller_id: Optional[str] = "628b3a5056228a000189c0e4"

class KeywordLoginRequest(BaseModel):
    password: str

_CACHED_KEYWORD_HTML: Optional[str] = None
_CACHED_LIBRARY_DATA: Optional[dict] = None

@router.get("/keyword", response_class=HTMLResponse)
@router.get("/keyword/", response_class=HTMLResponse)
@router.get("/keyword/tasks", response_class=HTMLResponse)
@router.get("/keyword/tasks/", response_class=HTMLResponse)
@router.get("/keyword/runs", response_class=HTMLResponse)
@router.get("/keyword/runs/", response_class=HTMLResponse)
def keyword_page(request: Request):
    global _CACHED_KEYWORD_HTML
    if not HTML_PATH.exists():
        return HTMLResponse("<h1>Keyword module ready</h1>")
    if _CACHED_KEYWORD_HTML is None:
        _CACHED_KEYWORD_HTML = HTML_PATH.read_text(encoding="utf-8")
    return HTMLResponse(_CACHED_KEYWORD_HTML)

@router.get("/api/keyword/library")
def keyword_library():
    global _CACHED_LIBRARY_DATA
    if _CACHED_LIBRARY_DATA is not None:
        return _CACHED_LIBRARY_DATA

    if not KEYWORD_LIBRARY_PATH.exists():
        return {"categories": {}, "counts": {}, "all_keywords": []}

    try:
        raw_data = json.loads(KEYWORD_LIBRARY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"词库解析失败: {e}")

    def words(value):
        return [w.strip() for w in value.split() if w.strip()]

    def contains_any(keyword, terms):
        return any(t in keyword for t in terms)

    def unique(items):
        seen = set()
        out = []
        for x in items:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    categorized = {}
    rule_definitions = {
        "防晒衣": {
            "防晒品类": words("防晒衣 防晒服 凉感防晒衣 皮肤衣 户外防晒衣 透气防晒衣 防紫外线 UPF 原纱防晒"),
            "人群场景": words("男士防晒衣 女士防晒衣 儿童防晒衣 户外防晒 徒步防晒 露营 钓鱼 骑行 通勤"),
            "热门竞品": words("焦下 蕉下 伯希和 探路者 骆驼 迪卡侬 优衣库 蕉内 OhSunny 波司登 北面")
        },
        "冲锋衣": {
            "硬壳软壳": words("冲锋衣 硬壳 软壳 三合一 单层冲锋衣 抓绒 防水 透气 耐磨 防风 GORE-TEX 暴雨级"),
            "场景风格": words("登山 徒步 户外 山系 露营 滑雪 骑行 战术 机能 工装 城市户外"),
            "热门品牌": words("始祖鸟 北面 哥伦比亚 骆驼 探路者 伯希和 猛犸象 土拨鼠 迪卡侬 拓路者 牧高笛")
        },
        "户外鞋": {
            "鞋款类型": words("徒步鞋 登山鞋 越野跑鞋 溯溪鞋 户外工装鞋 露营鞋 防滑 耐磨 防水 V底 Vibram"),
            "功能场景": words("重装徒步 轻量徒步 越野 攀爬 涉水 雨天防滑 减震 支撑 护踝"),
            "热门品牌": words("萨洛蒙 迈乐 斯卡帕 赞贝拉 迈乐 哥伦比亚 探路者 骆驼 迪卡侬 极地")
        },
        "速干衣裤": {
            "衣物类型": words("速干衣 速干裤 速干T恤 速干衬衫 运动速干 排汗 透气 凉感 轻量 耐磨 弹力"),
            "户外运动": words("徒步 登山 越野 露营 跑步 健身 训练 骑行 马拉松"),
            "热门品牌": words("巴塔哥尼亚 始祖鸟 探路者 伯希和 骆驼 迪卡侬 耐克 阿迪达斯 安德玛")
        },
        "羽绒服": {
            "羽绒款式": words("羽绒服 排骨羽绒 鹅绒 鸭绒 轻薄羽绒 厚款羽绒 连帽 防风保暖 蓬松度 800蓬 700蓬 拒水羽绒"),
            "极寒高山": words("高山攀登 极寒 户外保暖 露营防寒 滑雪 零下 防泼水 抗湿冷 极地"),
            "热门品牌": words("大鹅 加拿大鹅 始祖鸟 北面 蒙口 波司登 高梵 黑冰 天石 迪卡侬 伯希和 探路者")
        },
        "背包配件": {
            "背包收纳": words("登山包 徒步包 冲顶包 越野跑背心 户外背包 防水袋 腰包 胸包 背负系统"),
            "户外配件": words("登山杖 头灯 营地灯 户外水壶 护膝 手套 遮阳帽 渔夫帽 飞巾 睡袋 防潮垫"),
            "热门品牌": words("格里高利 小鹰 多特 始祖鸟 黑钻 BD 迪卡侬 火枫 挪客 牧高笛 静态")
        }
    }

    all_kws = list(raw_data.keys())
    for prime, sub_dict in rule_definitions.items():
        categorized[prime] = {}
        for sub_cat, terms in sub_dict.items():
            matched = [k for k in all_kws if contains_any(k, terms)]
            categorized[prime][sub_cat] = unique(matched)

    counts = {"total": len(all_kws)}
    for p_name, subs in categorized.items():
        p_total = set()
        counts[p_name] = {}
        for s_name, k_list in subs.items():
            counts[p_name][s_name] = len(k_list)
            p_total.update(k_list)
        counts[p_name]["_total"] = len(p_total)

    _CACHED_LIBRARY_DATA = {
        "categories": categorized,
        "counts": counts,
        "all_keywords": all_kws
    }
    return _CACHED_LIBRARY_DATA

@private_router.post("/search")
def search_keywords(req: KeywordSearchRequest, _=Depends(require_auth)):
    if isinstance(req.keywords, str):
        kws = [k.strip() for k in req.keywords.replace(",", " ").split() if k.strip()]
    else:
        kws = [str(k).strip() for k in req.keywords if str(k).strip()]
        
    if not kws:
        raise HTTPException(status_code=400, detail="关键词不能为空")
        
    try:
        res = fetch_keywords_insight(
            keywords=kws,
            start_date=req.start_date,
            end_date=req.end_date,
            strict=False
        )
        return res
    except InvalidDateRangeError as de:
        raise HTTPException(status_code=400, detail=str(de))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")

@private_router.get("/cookie", dependencies=[Depends(require_admin)])
def get_current_cookie():
    try:
        token = load_token()
        c = token.get("cookie", "")
        return {
            "configured": bool(c.strip()),
            "v_seller_id": token.get("v_seller_id", "628b3a5056228a000189c0e4"),
            "cookie_length": len(c.strip())
        }
    except Exception:
        return {
            "configured": False,
            "v_seller_id": "628b3a5056228a000189c0e4",
            "cookie_length": 0
        }

@private_router.post("/cookie", dependencies=[Depends(require_admin)])
def update_keyword_cookie(req: CookieUpdateRequest):
    clean_cookie = req.cookie.strip()
    if not clean_cookie:
        raise HTTPException(status_code=400, detail="Cookie 不能为空")
    v_id = (req.v_seller_id or "").strip() or "628b3a5056228a000189c0e4"
    token_data = {
        "cookie": clean_cookie,
        "v_seller_id": v_id,
        "origin": "https://ad.xiaohongshu.com",
        "referer": f"https://ad.xiaohongshu.com/aurora/ad/tools/newKeywordTool?vSellerId={v_id}",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "xsecappid": "aurora-shell"
    }
    from keyword_service.client import DEFAULT_TOKEN_FILE
    DEFAULT_TOKEN_FILE.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")
    session_file = Path(__file__).parent.parent / "sync_console" / "tokens" / "session_headers.json"
    if session_file.parent.exists():
        session_file.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "message": "小红书聚光 Cookie 更新成功！已自动生效。"}

@private_router.post("/feishu/direct_create", dependencies=[Depends(require_admin)])
def create_feishu_sheet_directly(req: DirectSheetRequest):
    if not req.keywords:
        raise HTTPException(status_code=400, detail="关键词列表不能为空")
    try:
        res = direct_create_feishu_sheet(
            keywords=req.keywords,
            start_date=req.start_date,
            end_date=req.end_date,
            title=req.title
        )
        return res
    except AppError as ae:
        raise HTTPException(status_code=ae.status_code, detail=ae.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.get("/tasks")
def list_keyword_tasks():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM keyword_tasks WHERE status != 'archived' ORDER BY id DESC")
        tasks = []
        for r in cursor.fetchall():
            d = dict(r)
            d["keywords"] = json.loads(d.get("keywords_json") or "[]")
            d["removed_keywords"] = json.loads(d.get("removed_keywords_json") or "[]")
            d["keywords_count"] = len(d["keywords"])
            tasks.append(d)
        return tasks

@private_router.post("/tasks", dependencies=[Depends(require_admin)])
def add_keyword_task(req: CreateKeywordTaskRequest):
    if not req.keywords:
        raise HTTPException(status_code=400, detail="关键词列表不能为空")
    try:
        res = create_keyword_task(
            task_name=req.task_name,
            keywords=req.keywords,
            update_mode=req.update_mode,
            rrule_str=req.rrule,
            days_range=req.days_range
        )
        SchedulerManager.get_instance().schedule_keyword_task(res["task_id"])
        return res
    except AppError as ae:
        raise HTTPException(status_code=ae.status_code, detail=ae.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/append_keywords", dependencies=[Depends(require_admin)])
def append_words_endpoint(task_id: int, req: AppendKeywordsRequest):
    if isinstance(req.keywords, str):
        kws = [k.strip() for k in req.keywords.replace(",", " ").split() if k.strip()]
    else:
        kws = [str(k).strip() for k in req.keywords if str(k).strip()]
    if not kws:
        raise HTTPException(status_code=400, detail="追加的关键词不能为空")
    return append_keywords_to_task(task_id, kws, sync_now=req.sync_now)

@private_router.post("/tasks/{task_id}/remove_keywords", dependencies=[Depends(require_admin)])
def remove_words_endpoint(task_id: int, req: RemoveKeywordsRequest):
    if isinstance(req.keywords, str):
        kws = [k.strip() for k in req.keywords.replace(",", " ").split() if k.strip()]
    else:
        kws = [str(k).strip() for k in req.keywords if str(k).strip()]
    if not kws:
        raise HTTPException(status_code=400, detail="要移除的关键词不能为空")
    return remove_keywords_from_task(task_id, kws)

@private_router.post("/tasks/{task_id}/run_now", dependencies=[Depends(require_admin)])
def run_task_immediately(task_id: int):
    try:
        return run_keyword_task(task_id, trigger_type="manual")
    except AppError as ae:
        raise HTTPException(status_code=ae.status_code, detail=ae.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/toggle", dependencies=[Depends(require_admin)])
def toggle_task(task_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM keyword_tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        curr = row["status"]
        next_s = "paused" if curr == "active" else "active"
        conn.execute("UPDATE keyword_tasks SET status = ?, updated_at = ? WHERE id = ?", (next_s, datetime.now().isoformat(), task_id))
        conn.commit()
    if next_s == "active":
        SchedulerManager.get_instance().schedule_keyword_task(task_id)
    else:
        SchedulerManager.get_instance().remove_keyword_task(task_id)
    return {"status": next_s}

@private_router.delete("/tasks/{task_id}", dependencies=[Depends(require_admin)])
def delete_task(task_id: int):
    with get_db() as conn:
        conn.execute("UPDATE keyword_tasks SET status = 'archived', updated_at = ? WHERE id = ?", (datetime.now().isoformat(), task_id))
        conn.commit()
    SchedulerManager.get_instance().remove_keyword_task(task_id)
    return {"success": True}

@private_router.get("/runs")
def list_keyword_runs(task_id: Optional[int] = None, page: int = 1, page_size: int = 20):
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
        
    with get_db() as conn:
        cursor = conn.cursor()
        if task_id:
            cursor.execute("SELECT COUNT(*) FROM keyword_runs WHERE task_id = ?", (task_id,))
            total = cursor.fetchone()[0]
            offset = (page - 1) * page_size
            cursor.execute(
                "SELECT * FROM keyword_runs WHERE task_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (task_id, page_size, offset)
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM keyword_runs")
            total = cursor.fetchone()[0]
            offset = (page - 1) * page_size
            cursor.execute(
                "SELECT * FROM keyword_runs ORDER BY id DESC LIMIT ? OFFSET ?",
                (page_size, offset)
            )
        items = [dict(r) for r in cursor.fetchall()]
        
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 1
    }

router.include_router(private_router)

# 独立模式下的 FastAPI 入口保持向后兼容
app = FastAPI(title="关键词服务")
app.include_router(router)

@app.post("/api/auth/login")
def standalone_login(req: KeywordLoginRequest, response: Response):
    if not ACCESS_TOKEN or not hmac.compare_digest(req.password, ACCESS_TOKEN):
        raise HTTPException(status_code=401, detail="密码错误")
    token = create_admin_session()
    response.set_cookie("sync_session", token, max_age=86400 * 30, httponly=True, samesite="lax")
    return {"success": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090)

