import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Union
from datetime import datetime
from fastapi import APIRouter, HTTPException, FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from keyword_service.client import fetch_keywords_insight, load_token
from keyword_service.db import get_db, init_db
from keyword_service.sync_engine import (
    direct_create_feishu_sheet,
    create_keyword_task,
    run_keyword_task,
    append_keywords_to_task
)
from keyword_service.scheduler import init_keyword_scheduler, reschedule_keyword_task, remove_keyword_job

router = APIRouter()
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

@router.get("/keyword", response_class=HTMLResponse)
def keyword_page():
    if not HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Page template not found")
    return HTMLResponse(content=HTML_PATH.read_text(encoding="utf-8"))

@router.post("/api/keyword/search")
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

@router.post("/api/keyword/feishu/direct_create")
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

@router.get("/api/keyword/tasks")
def list_keyword_tasks():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM keyword_tasks WHERE status != 'archived' ORDER BY id DESC")
        tasks = []
        for r in cursor.fetchall():
            item = dict(r)
            item["keywords"] = json.loads(item.get("keywords_json") or "[]")
            tasks.append(item)
    return tasks

@router.post("/api/keyword/tasks")
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

@router.post("/api/keyword/tasks/{task_id}/append_keywords")
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

@router.post("/api/keyword/tasks/{task_id}/run_now")
def run_task_immediately(task_id: int):
    try:
        res = run_keyword_task(task_id, trigger_type="manual")
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/keyword/tasks/{task_id}/toggle")
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

@router.delete("/api/keyword/tasks/{task_id}")
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

@router.get("/api/keyword/runs")
def list_keyword_runs(task_id: Optional[int] = None):
    with get_db() as conn:
        cursor = conn.cursor()
        if task_id:
            cursor.execute("SELECT * FROM keyword_runs WHERE task_id = ? ORDER BY id DESC LIMIT 50", (task_id,))
        else:
            cursor.execute("SELECT * FROM keyword_runs ORDER BY id DESC LIMIT 100")
        runs = [dict(r) for r in cursor.fetchall()]
    return runs

# 允许作为独立应用启动
app = FastAPI(title="关键词搜索指数服务")
app.include_router(router)

@app.on_event("startup")
def on_startup():
    init_keyword_scheduler()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090)

