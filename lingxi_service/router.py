import os
import sys
import json
import hmac
from pathlib import Path
from typing import Optional, List, Union, Dict, Any, Literal
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from lingxi_service.client import fetch_lingxi_keywords, load_token, sync_token_from_oss
from lingxi_service.db import get_db
from lingxi_service.sync_engine import (
    direct_create_feishu_sheet,
    create_lingxi_task,
    run_lingxi_task,
    append_keywords_to_lingxi_task,
    remove_keywords_from_lingxi_task
)
from core.scheduler_manager import SchedulerManager
from core.security import require_admin, require_auth, is_admin_authenticated
from core.errors import (
    AppError,
    TaskNotFoundError,
    TaskAlreadyRunningError,
    DataValidationError
)
from app.config import ACCESS_TOKEN

router = APIRouter()
private_router = APIRouter(prefix="/api/lingxi")

class LingxiSearchRequest(BaseModel):
    keywords: Union[str, List[str]]

class LingxiDirectSheetRequest(BaseModel):
    title: Optional[str] = None
    keywords: List[str]

class CreateLingxiTaskRequest(BaseModel):
    task_name: str = Field(..., min_length=1, max_length=120)
    keywords: List[str] = Field(..., min_items=1)
    spreadsheet_token: str = Field(..., min_length=1)
    spreadsheet_url: str = Field(..., min_length=1)
    update_mode: str = Field("overwrite", pattern="^(overwrite|append)$")
    rrule: str = Field("FREQ=DAILY;BYHOUR=9;BYMINUTE=30")

class TaskKeywordsMutation(BaseModel):
    keywords: List[str] = Field(..., min_items=1)

class CookieUpdateRequest(BaseModel):
    cookie: str

@private_router.post("/search")
def search_lingxi_keywords(req: LingxiSearchRequest):
    """查询灵犀关键词的即时覆盖人数及推荐词"""
    raw_kw = req.keywords
    if isinstance(raw_kw, str):
        kw_list = [k.strip() for k in raw_kw.replace(",", " ").split() if k.strip()]
    else:
        kw_list = [str(k).strip() for k in raw_kw if str(k).strip()]

    if not kw_list:
        raise HTTPException(status_code=400, detail="至少需要输入一个关键词")

    # 去重
    kw_list = list(dict.fromkeys(kw_list))
    if len(kw_list) > 100:
        raise HTTPException(status_code=400, detail="单次最多支持查询 100 个关键词")

    res = fetch_lingxi_keywords(kw_list)
    return JSONResponse(content={
        "code": 0,
        "msg": "success",
        "data": res
    })

@private_router.get("/cookie", dependencies=[Depends(require_admin)])
def get_lingxi_cookie():
    token = load_token()
    cookie_val = token.get("cookie", "")
    masked = f"{cookie_val[:10]}...{cookie_val[-10:]}" if len(cookie_val) > 20 else cookie_val
    return {
        "has_cookie": bool(cookie_val),
        "masked_cookie": masked,
        "origin": token.get("origin"),
        "referer": token.get("referer")
    }

@private_router.post("/cookie", dependencies=[Depends(require_admin)])
def update_lingxi_cookie(req: CookieUpdateRequest):
    new_cookie = req.cookie.strip()
    if not new_cookie:
        raise HTTPException(status_code=400, detail="Cookie 不能为空")
    token = load_token()
    token["cookie"] = new_cookie
    token_path = Path(__file__).parent / "token.json"
    token_path.write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"code": 0, "msg": "灵犀 Cookie 更新成功"}

@private_router.post("/cookie/sync_oss", dependencies=[Depends(require_admin)])
def sync_lingxi_cookie_oss():
    token = sync_token_from_oss(force=True)
    if not token or not token.get("cookie"):
        raise HTTPException(status_code=500, detail="未能从 OSS 同步到灵犀 Cookie 文件")
    return {"code": 0, "msg": "已从 OSS 同步最新灵犀 Cookie"}

@private_router.post("/feishu/direct_create", dependencies=[Depends(require_admin)])
def direct_create_sheet(req: LingxiDirectSheetRequest):
    kw_list = list(dict.fromkeys([k.strip() for k in req.keywords if k.strip()]))
    if not kw_list:
        raise HTTPException(status_code=400, detail="至少需要一个有效关键词")

    try:
        res = direct_create_feishu_sheet(keywords=kw_list, title=req.title)
        return {"code": 0, "msg": "飞书表格创建成功", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建飞书表格失败: {str(e)}")

@private_router.get("/tasks")
def list_lingxi_tasks():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM lingxi_tasks ORDER BY id DESC")
    tasks = [dict(r) for r in cur.fetchall()]
    for t in tasks:
        try:
            t["keywords"] = json.loads(t.get("keywords_json") or "[]")
            t["removed_keywords"] = json.loads(t.get("removed_keywords_json") or "[]")
        except Exception:
            t["keywords"] = []
            t["removed_keywords"] = []
    return tasks

@private_router.post("/tasks", dependencies=[Depends(require_admin)])
def create_task_endpoint(req: CreateLingxiTaskRequest):
    try:
        task_id = create_lingxi_task(
            name=req.task_name,
            keywords=req.keywords,
            spreadsheet_token=req.spreadsheet_token,
            spreadsheet_url=req.spreadsheet_url,
            update_mode=req.update_mode,
            rrule=req.rrule
        )
        return {"code": 0, "msg": "灵犀任务创建成功", "task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/append_keywords", dependencies=[Depends(require_admin)])
def append_keywords_endpoint(task_id: int, req: TaskKeywordsMutation):
    try:
        updated = append_keywords_to_lingxi_task(task_id, req.keywords)
        return {"code": 0, "msg": "关键词追加成功", "keywords": updated}
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/remove_keywords", dependencies=[Depends(require_admin)])
def remove_keywords_endpoint(task_id: int, req: TaskKeywordsMutation):
    try:
        updated = remove_keywords_from_lingxi_task(task_id, req.keywords)
        return {"code": 0, "msg": "关键词移除成功", "keywords": updated}
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/run_now", dependencies=[Depends(require_admin)])
def run_task_now_endpoint(task_id: int):
    try:
        res = run_lingxi_task(task_id, trigger_type="manual")
        return {"code": 0, "msg": "任务执行完成", "data": res}
    except TaskAlreadyRunningError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"任务执行失败: {str(e)}")

@private_router.post("/tasks/{task_id}/toggle", dependencies=[Depends(require_admin)])
def toggle_task_endpoint(task_id: int):
    conn = get_db()
    with conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM lingxi_tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="未找到任务")
        new_status = "paused" if row["status"] == "active" else "active"
        cur.execute("UPDATE lingxi_tasks SET status = ?, updated_at = ? WHERE id = ?", (new_status, datetime.now().isoformat(), task_id))

    mgr = SchedulerManager.get_instance()
    if new_status == "active":
        mgr.schedule_lingxi_task(task_id)
    else:
        mgr.remove_lingxi_task(task_id)

    return {"code": 0, "msg": "状态切换成功", "new_status": new_status}

@private_router.delete("/tasks/{task_id}", dependencies=[Depends(require_admin)])
def delete_task_endpoint(task_id: int):
    conn = get_db()
    with conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM lingxi_tasks WHERE id = ?", (task_id,))
    mgr = SchedulerManager.get_instance()
    mgr.remove_lingxi_task(task_id)
    return {"code": 0, "msg": "任务删除成功"}

@private_router.get("/runs")
def list_lingxi_runs(limit: int = 50):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM lingxi_runs ORDER BY id DESC LIMIT ?", (limit,))
    runs = [dict(r) for r in cur.fetchall()]
    for r in runs:
        try:
            r["successful_keywords"] = json.loads(r.get("successful_keywords") or "[]")
            r["failed_keywords"] = json.loads(r.get("failed_keywords") or "[]")
        except Exception:
            r["successful_keywords"] = []
            r["failed_keywords"] = []
    return runs

router.include_router(private_router)
