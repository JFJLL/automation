import os
import sys
import json
import hmac
from pathlib import Path
from typing import Optional, List, Union
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from keyword_service.client import fetch_keywords_insight, load_token
from keyword_service.db import get_db, init_db
from keyword_service.sync_engine import (
    direct_create_feishu_sheet,
    create_keyword_task,
    run_keyword_task,
    append_keywords_to_task,
    remove_keywords_from_task
)
from keyword_service.scheduler import init_keyword_scheduler, reschedule_keyword_task, remove_keyword_job
from app.config import ACCESS_TOKEN

router = APIRouter()

private_router = APIRouter(prefix="/api/keyword")
HTML_PATH = Path(__file__).parent / "templates" / "keyword.html"

# 初始化数据库
init_db()

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
    sync_now: bool = True

class RemoveKeywordsRequest(BaseModel):
    keywords: Union[str, List[str]]

class KeywordLoginRequest(BaseModel):
    password: str

@router.get("/keyword", response_class=HTMLResponse)
def keyword_page():
    if not HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Page template not found")
    return HTMLResponse(content=HTML_PATH.read_text(encoding="utf-8"))

@router.get("/favicon.svg")
def keyword_favicon_svg():
    candidates = [
        Path(__file__).parent.parent / "sync_console" / "web" / "favicon.svg",
        Path(__file__).parent.parent / "web" / "favicon.svg"
    ]
    for p in candidates:
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/svg+xml")
    return Response(status_code=404)

@router.get("/favicon.ico")
def keyword_favicon_ico():
    candidates = [
        Path(__file__).parent.parent / "sync_console" / "web" / "favicon.ico",
        Path(__file__).parent.parent / "web" / "favicon.ico"
    ]
    for p in candidates:
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/x-icon")
    return keyword_favicon_svg()

@private_router.post("/search")
def search_keywords(req: KeywordSearchRequest):
    if isinstance(req.keywords, str):
        kw_list = [w.strip() for w in req.keywords.split() if w.strip()]
    else:
        kw_list = [w.strip() for w in req.keywords if w.strip()]
        
    if not kw_list:
        raise HTTPException(status_code=400, detail="关键词不能为空，请至少输入一个关键词")
        
    try:
        data = fetch_keywords_insight(
            keywords=kw_list,
            start_date=req.start_date,
            end_date=req.end_date
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/feishu/direct_create")
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.get("/tasks")
def list_keyword_tasks():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM keyword_tasks WHERE status != 'archived' ORDER BY id DESC")
        tasks = []
        for r in cursor.fetchall():
            item = dict(r)
            item["keywords"] = json.loads(item.get("keywords_json") or "[]")
            item["removed_keywords"] = json.loads(item.get("removed_keywords_json") or "[]")
            tasks.append(item)
    return tasks

@private_router.post("/tasks")
def add_keyword_task(req: CreateKeywordTaskRequest):
    if not req.keywords:
        raise HTTPException(status_code=400, detail="任务至少需要包含一个关键词")
    try:
        res = create_keyword_task(
            task_name=req.task_name,
            keywords=req.keywords,
            update_mode=req.update_mode,
            rrule_str=req.rrule,
            days_range=req.days_range
        )
        reschedule_keyword_task(res["task_id"])
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/append_keywords")
def append_words_endpoint(task_id: int, req: AppendKeywordsRequest):
    if isinstance(req.keywords, str):
        kw_list = [w.strip() for w in req.keywords.split() if w.strip()]
    else:
        kw_list = [w.strip() for w in req.keywords if w.strip()]
        
    if not kw_list:
        raise HTTPException(status_code=400, detail="请至少输入一个要添加的关键词")
        
    try:
        res = append_keywords_to_task(task_id, kw_list, sync_now=req.sync_now)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/remove_keywords")
def remove_words_endpoint(task_id: int, req: RemoveKeywordsRequest):
    if isinstance(req.keywords, str):
        kw_list = [w.strip() for w in req.keywords.split() if w.strip()]
    else:
        kw_list = [w.strip() for w in req.keywords if w.strip()]
        
    if not kw_list:
        raise HTTPException(status_code=400, detail="请至少提供一个要减掉的关键词")
        
    try:
        res = remove_keywords_from_task(task_id, kw_list)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/run_now")
def run_task_immediately(task_id: int):
    try:
        res = run_keyword_task(task_id, trigger_type="manual")
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@private_router.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM keyword_tasks WHERE id = ?", (task_id,))
        r = cursor.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Task not found")
        new_status = "paused" if r["status"] == "active" else "active"
        conn.execute("UPDATE keyword_tasks SET status = ?, updated_at = ? WHERE id = ?", (new_status, datetime.now().isoformat(), task_id))
        conn.commit()
        
    reschedule_keyword_task(task_id)
    return {"status": new_status}

@private_router.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM keyword_tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute("UPDATE keyword_tasks SET status = 'archived', updated_at = ? WHERE id = ?", (datetime.now().isoformat(), task_id))
        conn.commit()
    remove_keyword_job(task_id)
    return {"success": True, "message": f"任务 #{task_id} 已成功删除"}

@private_router.get("/runs")
def list_keyword_runs(task_id: Optional[int] = None):
    with get_db() as conn:
        cursor = conn.cursor()
        if task_id:
            cursor.execute("SELECT * FROM keyword_runs WHERE task_id = ? ORDER BY id DESC LIMIT 50", (task_id,))
        else:
            cursor.execute("SELECT * FROM keyword_runs ORDER BY id DESC LIMIT 100")
        runs = [dict(r) for r in cursor.fetchall()]
    return runs

router.include_router(private_router)

# 允许作为独立应用启动
app = FastAPI(title="关键词搜索指数服务")
app.include_router(router)

@app.post("/api/auth/login")
def standalone_login(req: KeywordLoginRequest, response: Response):
    if not hmac.compare_digest(req.password, ACCESS_TOKEN):
        raise HTTPException(status_code=401, detail="密码错误")
    response.set_cookie("access_token", ACCESS_TOKEN, max_age=86400, httponly=True, samesite="lax")
    return {"success": True}

@app.on_event("startup")
def on_startup():
    init_keyword_scheduler()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090)

