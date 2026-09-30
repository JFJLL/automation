import json
import os
import sys
import math
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware

from app.config import (
    ACCESS_TOKEN, BASE_DIR, SHARED_FOLDER_TOKEN, SHARED_FOLDER_NAME,
    FEISHU_CHAT_ID, NOTIFICATION_WEBHOOK, NOTIFICATION_POLICY
)
from app.db import get_db, init_db
from keyword_service.db import init_db as init_kw_db
from feishu.client import FeishuClient
from feishu.notify import Notifier
from platforms.registry import PLATFORMS
from platforms.juguang import get_juguang_subaccounts_list
from core.ingest import parse_excel_sheets, analyze_sheet_for_platform
from core.sync import preview_fetch, execute_task_sync
from core.scheduler_manager import SchedulerManager
from core.security import (
    require_admin,
    require_auth,
    is_admin_authenticated,
    create_admin_session,
    SESSION_COOKIE_NAME
)
from core.business_time import now_business_tz, latest_keyword_available_date
from core.errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    TaskNotFoundError,
    TaskAlreadyRunningError,
    DataValidationError,
    InvalidDateRangeError,
    FeishuError,
    ProviderError
)

# 确保根目录在 sys.path
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
automation_root = str(PROJECT_ROOT)
if automation_root not in sys.path:
    sys.path.insert(0, automation_root)

from keyword_service.router import router as keyword_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行数据库迁移与任务恢复
    init_db()
    init_kw_db()
    SchedulerManager.get_instance().start()
    yield
    # 优雅停机
    SchedulerManager.get_instance().shutdown()

app = FastAPI(title="飞书数据自动同步中心", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 全局业务异常处理
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}}
    )

@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": f"HTTP_{exc.status_code}", "message": msg}}
    )

# 挂载前端 React SPA 生产构建静态产物
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
if (BASE_DIR / "web").exists():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web")), name="static")


# 注册关键词路由
app.include_router(keyword_router)

# ---------------- 健康检查与就绪检查 (Section 六十一) ----------------
@app.get("/api/business-time")
def get_business_time():
    now_dt = now_business_tz()
    latest_dt = latest_keyword_available_date(now_dt)
    return {
        "timezone": "Asia/Shanghai",
        "now": now_dt.isoformat(),
        "latest_keyword_date": latest_dt.isoformat(),
        "is_after_noon": now_dt.hour >= 12
    }

@app.get("/api/health")
def health_check():
    """轻量存活检查，不访问任何外部服务"""
    return {"status": "ok", "timestamp": now_business_tz().isoformat()}

@app.get("/api/ready")
def readiness_check():
    """就绪检查：验证数据库可访问与调度器就绪"""
    db_ok = False
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
    except Exception:
        db_ok = False
        
    scheduler_ok = SchedulerManager.get_instance().scheduler.running
    if not (db_ok and scheduler_ok):
        raise HTTPException(status_code=503, detail="服务未就绪")
    return {
        "status": "ready",
        "database": "ok",
        "scheduler": "ok",
        "timestamp": now_business_tz().isoformat()
    }

def render_spa_index():
    if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
        return HTMLResponse((FRONTEND_DIST / "index.html").read_text(encoding="utf-8"))
    html_path = BASE_DIR / "web" / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>自动化中心前端构建未就绪，请在 frontend 目录执行 npm run build</h1>", status_code=503)

@app.get("/", response_class=HTMLResponse)
@app.get("/import", response_class=HTMLResponse)
@app.get("/tasks", response_class=HTMLResponse)
@app.get("/runs", response_class=HTMLResponse)
@app.get("/keyword", response_class=HTMLResponse)
@app.get("/keyword/", response_class=HTMLResponse)
@app.get("/keyword/tasks", response_class=HTMLResponse)
@app.get("/keyword/tasks/", response_class=HTMLResponse)
@app.get("/keyword/runs", response_class=HTMLResponse)
@app.get("/keyword/runs/", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
def index_page():
    return render_spa_index()

@app.get("/favicon.svg")
def favicon_svg():
    candidates = [
        FRONTEND_DIST / "favicon.svg",
        FRONTEND_DIST / "public" / "favicon.svg",
        BASE_DIR / "web" / "favicon.svg",
        BASE_DIR / "sync_console" / "web" / "favicon.svg"
    ]
    for p in candidates:
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/svg+xml")
    return Response(status_code=404)

@app.get("/favicon.ico")
def favicon_ico():
    candidates = [
        FRONTEND_DIST / "favicon.ico",
        FRONTEND_DIST / "public" / "favicon.ico",
        BASE_DIR / "web" / "favicon.ico",
        BASE_DIR / "sync_console" / "web" / "favicon.ico"
    ]
    for p in candidates:
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/x-icon")
    return favicon_svg()

# ---------------- 鉴权端点 (Section 十五, 十八) ----------------
@app.post("/api/auth/login")
def login(payload: Dict[str, str], request: Request, response: Response):
    pwd = payload.get("password", "")
    if not ACCESS_TOKEN or pwd != ACCESS_TOKEN:
        raise HTTPException(status_code=400, detail="口令错误")
        
    token = create_admin_session()
    is_secure = request.url.scheme == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=86400 * 30,
        httponly=True,
        samesite="lax",
        secure=is_secure
    )
    # 兼容过渡期 cookie
    response.set_cookie(
        key="access_token",
        value=ACCESS_TOKEN,
        max_age=86400 * 30,
        httponly=True,
        samesite="lax",
        secure=is_secure
    )
    # 绝不再向前端返回原始密码或 ACCESS_TOKEN！
    return {"success": True}

@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    response.delete_cookie(key="access_token")
    return {"success": True}

@app.get("/api/auth/check")
def auth_check(request: Request):
    return {"authenticated": is_admin_authenticated(request)}

# ---------------- 数据同步 API ----------------
@app.get("/api/platforms")
def get_platforms():
    return {
        code: {"name": p["name"], "vocab_count": len(p["vocab"])}
        for code, p in PLATFORMS.items()
    }

@app.get("/api/platforms/juguang/subaccounts")
def get_juguang_subaccounts(refresh: bool = False):
    return get_juguang_subaccounts_list(force_refresh=refresh)

@app.get("/api/settings", dependencies=[Depends(require_admin)])
def get_settings():
    feishu = FeishuClient()
    folder_token = feishu.get_or_create_shared_folder()
    return {
        "shared_folder_token": folder_token,
        "shared_folder_name": SHARED_FOLDER_NAME,
        "feishu_chat_id": FEISHU_CHAT_ID,
        "notification_webhook": NOTIFICATION_WEBHOOK,
        "notification_policy": NOTIFICATION_POLICY
    }

@app.post("/api/feishu/create_chat", dependencies=[Depends(require_admin)])
def create_feishu_chat(payload: Dict[str, str]):
    name = payload.get("name", "数据同步告警群")
    notifier = Notifier()
    chat_id = notifier.create_chat_group(name)
    return {"chat_id": chat_id}

@app.post("/api/upload", dependencies=[Depends(require_admin)])
async def upload_excel(
    file: UploadFile = File(...),
    selected_platform: str = Form(...)
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
    sub_account_id: Optional[str] = None

@app.post("/api/preview", dependencies=[Depends(require_admin)])
def fetch_preview(req: PreviewRequest):
    return preview_fetch(
        platform=req.platform,
        entity_ids=req.entity_ids,
        dimension=req.dimension,
        start_date=req.start_date,
        end_date=req.end_date,
        headers=req.headers,
        id_col=req.id_column,
        date_col=req.date_column,
        sub_account_id=req.sub_account_id
    )

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
    task_name: str = Field(..., min_length=1, max_length=120)
    platform: Literal["jzt", "taobao", "juguang"]
    update_mode: Literal["append", "overwrite"] = "append"
    calibration_days: int = Field(default=2, ge=0, le=30)
    rrule: str = Field(..., min_length=5, max_length=200)
    sheets: List[SheetConfig] = Field(..., min_length=1)
    write_initial_data: bool = True
    sub_account_id: Optional[str] = None
    sub_account_name: Optional[str] = None

@app.post("/api/create_task", dependencies=[Depends(require_admin)])
def create_task(req: CreateTaskRequest):
    if not req.sheets:
        raise HTTPException(status_code=400, detail="至少需要选择一个有效工作表")
    try:
        SchedulerManager.get_instance().parse_sync_next_run(req.rrule)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"非法 RRULE 调度表达式: {e}")
        
    feishu = FeishuClient()
    folder_token = feishu.get_or_create_shared_folder()
    
    ss_meta = feishu.create_spreadsheet(title=req.task_name, folder_token=folder_token)
    ss_token = ss_meta["spreadsheet_token"]
    ss_url = ss_meta["url"]
    
    existing_sheets = feishu.get_sheets(ss_token)
    first_sheet_id = existing_sheets[0]["sheet_id"] if existing_sheets else "0"
    
    sheet_records = []
    for idx, sc in enumerate(req.sheets):
        if idx == 0:
            ws_id = first_sheet_id
        else:
            ws_id = feishu.add_worksheet(ss_token, title=sc.sheet_title)
            
        feishu.write_rows(ss_token, ws_id, start_row=1, rows=[sc.headers])
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
        
    feishu.set_sheet_public_editable(ss_token)
    now = datetime.now().isoformat()
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (
                name, platform, sub_account_id, sub_account_name, folder_token, spreadsheet_token, spreadsheet_url,
                update_mode, calibration_days, rrule, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                req.task_name, req.platform, req.sub_account_id, req.sub_account_name, folder_token, ss_token, ss_url,
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
        
    SchedulerManager.get_instance().schedule_sync_task(task_id)
    
    return {
        "success": True,
        "task_id": task_id,
        "spreadsheet_token": ss_token,
        "spreadsheet_url": ss_url
    }

@app.get("/api/tasks")
def list_tasks():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE status != 'archived' ORDER BY id DESC")
        tasks = [dict(r) for r in cursor.fetchall()]
        for t in tasks:
            cursor.execute("SELECT sheet_title, worksheet_id, dimension, id_column, entity_ids_json FROM task_sheets WHERE task_id = ?", (t["id"],))
            t["sheets"] = [dict(s) for s in cursor.fetchall()]
    return tasks

@app.post("/api/tasks/{task_id}/run_now", dependencies=[Depends(require_admin)])
def run_task_now(task_id: int):
    return execute_task_sync(task_id, trigger_type="manual")

@app.post("/api/tasks/{task_id}/toggle_status", dependencies=[Depends(require_admin)])
def toggle_task_status(task_id: int):
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
        SchedulerManager.get_instance().schedule_sync_task(task_id)
    else:
        SchedulerManager.get_instance().remove_sync_task(task_id)
    return {"status": new_status}

@app.delete("/api/tasks/{task_id}", dependencies=[Depends(require_admin)])
def archive_task(task_id: int):
    with get_db() as conn:
        conn.execute("UPDATE tasks SET status = 'archived', updated_at = ? WHERE id = ?", (datetime.now().isoformat(), task_id))
        conn.commit()
    SchedulerManager.get_instance().remove_sync_task(task_id)
    return {"success": True}

@app.get("/api/runs")
def list_runs(
    task_id: Optional[int] = None,
    page: Optional[int] = None,
    page_size: int = 20
):
    if page is not None and page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > 100:
        page_size = 100

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

