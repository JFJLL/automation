import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from app.config import (
    ACCESS_TOKEN, BASE_DIR, SHARED_FOLDER_TOKEN, SHARED_FOLDER_NAME,
    FEISHU_CHAT_ID, NOTIFICATION_WEBHOOK, NOTIFICATION_POLICY
)
from app.db import get_db, init_db
from feishu.client import FeishuClient
from feishu.notify import Notifier
from platforms.registry import PLATFORMS
from core.ingest import parse_excel_sheets, analyze_sheet_for_platform
from core.sync import preview_fetch, execute_task_sync
from core.scheduler import init_scheduler, reschedule_task, remove_job, parse_next_run

app = FastAPI(title="飞书数据自动同步中心")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web")), name="static")

automation_root = str(BASE_DIR.parent)
if automation_root not in sys.path:
    sys.path.insert(0, automation_root)

from keyword_service.router import router as keyword_router
from keyword_service.scheduler import init_keyword_scheduler
app.include_router(keyword_router)

def verify_admin_token(request: Request) -> bool:
    token = request.headers.get("X-Access-Token") or request.cookies.get("access_token")
    if not token or token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="未授权，需要管理员权限")
    return True

def verify_token(request: Request) -> bool:
    return True

@app.on_event("startup")
def on_startup():
    init_db()
    init_scheduler()
    init_keyword_scheduler()

@app.get("/", response_class=HTMLResponse)
@app.get("/import", response_class=HTMLResponse)
@app.get("/tasks", response_class=HTMLResponse)
@app.get("/runs", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
def index_page():
    html_path = BASE_DIR / "web" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

@app.get("/favicon.svg")
def favicon_svg():
    candidates = [
        BASE_DIR / "web" / "favicon.svg",
        BASE_DIR / "sync_console" / "web" / "favicon.svg",
        Path(__file__).parent.parent / "web" / "favicon.svg",
        Path(__file__).parent.parent / "sync_console" / "web" / "favicon.svg"
    ]
    for p in candidates:
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/svg+xml")
    return Response(status_code=404)

@app.get("/favicon.ico")
def favicon_ico():
    candidates = [
        BASE_DIR / "web" / "favicon.ico",
        BASE_DIR / "sync_console" / "web" / "favicon.ico",
        Path(__file__).parent.parent / "web" / "favicon.ico",
        Path(__file__).parent.parent / "sync_console" / "web" / "favicon.ico"
    ]
    for p in candidates:
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/x-icon")
    return favicon_svg()

@app.post("/api/auth/login")
def login(payload: Dict[str, str], response: Response):
    pwd = payload.get("password", "")
    if pwd == ACCESS_TOKEN:
        response.set_cookie(key="access_token", value=ACCESS_TOKEN, max_age=86400 * 30, httponly=True)
        return {"success": True, "token": ACCESS_TOKEN}
    raise HTTPException(status_code=400, detail="口令错误")

@app.get("/api/auth/check")
def auth_check(request: Request):
    token = request.headers.get("X-Access-Token") or request.cookies.get("access_token")
    return {"authenticated": bool(token and token == ACCESS_TOKEN)}

@app.get("/api/platforms")
def get_platforms(_=Depends(verify_token)):
    return {
        code: {"name": p["name"], "vocab_count": len(p["vocab"])}
        for code, p in PLATFORMS.items()
    }

@app.get("/api/settings")
def get_settings(_=Depends(verify_admin_token)):
    feishu = FeishuClient()
    folder_token = feishu.get_or_create_shared_folder()
    return {
        "shared_folder_token": folder_token,
        "shared_folder_name": SHARED_FOLDER_NAME,
        "feishu_chat_id": FEISHU_CHAT_ID,
        "notification_webhook": NOTIFICATION_WEBHOOK,
        "notification_policy": NOTIFICATION_POLICY
    }

@app.post("/api/feishu/create_chat")
def create_feishu_chat(payload: Dict[str, str], _=Depends(verify_token)):
    name = payload.get("name", "数据同步告警群")
    notifier = Notifier()
    chat_id = notifier.create_chat_group(name)
    return {"chat_id": chat_id}

@app.post("/api/upload")
async def upload_excel(
    file: UploadFile = File(...),
    selected_platform: str = Form(...),
    _=Depends(verify_token)
):
    content = await file.read()
    raw_sheets = parse_excel_sheets(content, file.filename)
    if not raw_sheets:
        raise HTTPException(status_code=400, detail="未能从文件中读取到有效工作表或表头")
        
    analyzed_sheets = []
    for s in raw_sheets:
        analysis = analyze_sheet_for_platform(s, selected_platform)
        analyzed_sheets.append(analysis)
        
    return {
        "filename": file.filename,
        "selected_platform": selected_platform,
        "sheets": analyzed_sheets
    }

class PreviewRequest(BaseModel):
    platform: str
    sheet_title: str
    headers: List[str]
    entity_ids: List[str]
    id_column: str
    date_column: str
    dimension: str
    start_date: str
    end_date: str

@app.post("/api/preview")
def fetch_preview(req: PreviewRequest, _=Depends(verify_token)):
    res = preview_fetch(
        platform=req.platform,
        entity_ids=req.entity_ids,
        dimension=req.dimension,
        start_date=req.start_date,
        end_date=req.end_date,
        headers=req.headers,
        id_col=req.id_column,
        date_col=req.date_column
    )
    return res

class SheetConfig(BaseModel):
    sheet_title: str
    dimension: str
    id_column: str
    date_column: str
    headers: List[str]
    entity_ids: List[str]
    column_mapping: List[Dict[str, Any]]
    initial_rows: Optional[List[List[Any]]] = None

class CreateTaskRequest(BaseModel):
    task_name: str
    platform: str
    update_mode: str  # 'append' or 'overwrite'
    calibration_days: int
    rrule: str
    sheets: List[SheetConfig]
    write_initial_data: bool = True

@app.post("/api/create_task")
def create_task(req: CreateTaskRequest, _=Depends(verify_token)):
    if not req.sheets:
        raise HTTPException(status_code=400, detail="至少需要选择一个有效工作表")
        
    feishu = FeishuClient()
    folder_token = feishu.get_or_create_shared_folder()
    
    # 1. 自动在飞书共享文件夹创建表格
    ss_meta = feishu.create_spreadsheet(title=req.task_name, folder_token=folder_token)
    ss_token = ss_meta["spreadsheet_token"]
    ss_url = ss_meta["url"]
    
    # 2. 读取默认第一个 sheet 并重命名，或按需建表
    existing_sheets = feishu.get_sheets(ss_token)
    first_sheet_id = existing_sheets[0]["sheet_id"] if existing_sheets else "0"
    
    sheet_records = []
    for idx, sc in enumerate(req.sheets):
        if idx == 0:
            # 复用首张 sheet
            ws_id = first_sheet_id
        else:
            ws_id = feishu.add_worksheet(ss_token, title=sc.sheet_title)
            
        # 写入表头
        feishu.write_rows(ss_token, ws_id, start_row=1, rows=[sc.headers])
        
        # 写入初始预览数据
        if req.write_initial_data and sc.initial_rows:
            feishu.write_rows(ss_token, ws_id, start_row=2, rows=sc.initial_rows)
            
        sheet_records.append({
            "sheet_title": sc.sheet_title,
            "worksheet_id": ws_id,
            "dimension": sc.dimension,
            "id_column": sc.id_column,
            "date_column": sc.date_column,
            "headers": sc.headers,
            "column_mapping": sc.column_mapping,
            "entity_ids": sc.entity_ids
        })
        
    # 3. 记录任务至数据库
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (
                name, platform, folder_token, spreadsheet_token, spreadsheet_url,
                update_mode, calibration_days, rrule, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                req.task_name, req.platform, folder_token, ss_token, ss_url,
                req.update_mode, req.calibration_days, req.rrule, now, now
            )
        )
        task_id = cursor.lastrowid
        
        for sr in sheet_records:
            cursor.execute(
                """
                INSERT INTO task_sheets (
                    task_id, sheet_title, worksheet_id, dimension, id_column, date_column,
                    header_json, column_map_json, entity_ids_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id, sr["sheet_title"], sr["worksheet_id"], sr["dimension"],
                    sr["id_column"], sr["date_column"], json.dumps(sr["headers"], ensure_ascii=False),
                    json.dumps(sr["column_mapping"], ensure_ascii=False),
                    json.dumps(sr["entity_ids"], ensure_ascii=False), now
                )
            )
        conn.commit()
        
    # 4. 注册调度
    reschedule_task(task_id)
    
    return {
        "success": True,
        "task_id": task_id,
        "spreadsheet_token": ss_token,
        "spreadsheet_url": ss_url
    }

@app.get("/api/tasks")
def list_tasks(_=Depends(verify_token)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks ORDER BY id DESC")
        tasks = [dict(r) for r in cursor.fetchall()]
        for t in tasks:
            cursor.execute("SELECT sheet_title, worksheet_id, dimension, id_column, entity_ids_json FROM task_sheets WHERE task_id = ?", (t["id"],))
            t["sheets"] = [dict(s) for s in cursor.fetchall()]
    return tasks

@app.post("/api/tasks/{task_id}/run_now")
def run_task_now(task_id: int, _=Depends(verify_token)):
    res = execute_task_sync(task_id, trigger_type="manual")
    return res

@app.post("/api/tasks/{task_id}/toggle_status")
def toggle_task_status(task_id: int, _=Depends(verify_token)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
        r = cursor.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Task not found")
        new_status = "paused" if r["status"] == "active" else "active"
        cursor.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (new_status, datetime.now().isoformat(), task_id))
        conn.commit()
    if new_status == "active":
        reschedule_task(task_id)
    else:
        remove_job(task_id)
    return {"status": new_status}

@app.delete("/api/tasks/{task_id}")
def archive_task(task_id: int, _=Depends(verify_token)):
    with get_db() as conn:
        conn.execute("UPDATE tasks SET status = 'archived', updated_at = ? WHERE id = ?", (datetime.now().isoformat(), task_id))
        conn.commit()
    remove_job(task_id)
    return {"success": True}

@app.get("/api/runs")
def list_runs(
    task_id: Optional[int] = None,
    page: Optional[int] = None,
    page_size: int = 20,
    _=Depends(verify_token)
):
    import math
    if page is not None and page < 1:
        page = 1
    if page_size < 1:
        page_size = 20

    with get_db() as conn:
        cursor = conn.cursor()
        if task_id:
            cursor.execute("SELECT COUNT(*) FROM runs WHERE task_id = ?", (task_id,))
            total = cursor.fetchone()[0]
            if page is not None:
                offset = (page - 1) * page_size
                cursor.execute(
                    "SELECT r.*, t.name as task_name, t.platform FROM runs r JOIN tasks t ON r.task_id = t.id WHERE r.task_id = ? ORDER BY r.id DESC LIMIT ? OFFSET ?",
                    (task_id, page_size, offset)
                )
            else:
                cursor.execute(
                    "SELECT r.*, t.name as task_name, t.platform FROM runs r JOIN tasks t ON r.task_id = t.id WHERE r.task_id = ? ORDER BY r.id DESC LIMIT 50",
                    (task_id,)
                )
        else:
            cursor.execute("SELECT COUNT(*) FROM runs")
            total = cursor.fetchone()[0]
            if page is not None:
                offset = (page - 1) * page_size
                cursor.execute(
                    "SELECT r.*, t.name as task_name, t.platform FROM runs r JOIN tasks t ON r.task_id = t.id ORDER BY r.id DESC LIMIT ? OFFSET ?",
                    (page_size, offset)
                )
            else:
                cursor.execute(
                    "SELECT r.*, t.name as task_name, t.platform FROM runs r JOIN tasks t ON r.task_id = t.id ORDER BY r.id DESC LIMIT 100"
                )
        runs = [dict(row) for row in cursor.fetchall()]

    if page is not None:
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size) if page_size > 0 else 1,
            "items": runs
        }
    return runs
