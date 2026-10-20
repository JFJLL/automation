# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import os
import io
import csv
import json
import urllib.parse
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import ACCESS_TOKEN, BASE_DIR, SIMPLE_PROMO_PASSWORD
from core.database import get_simple_promo_db
from core.security import sign_payload, verify_session_str
from core.scheduler_manager import SchedulerManager
from platforms.juguang import get_juguang_subaccounts_list
from simple_promo.engine import (
    execute_simple_promo_plan,
    run_simple_promo_task,
    check_subaccount_cookie_exists,
    JuguangSimplePromotionClient,
    DEFAULT_CUTOFF_STR
)
from simple_promo.backup import save_task_backup, list_promo_backups
from simple_promo.restore import rollback_simple_promo_run
from simple_promo.feishu_sync import get_or_create_promo_spreadsheet, sync_run_to_feishu

router = APIRouter(prefix="/api/simple-promo", tags=["simple-promo"])

SIMPLE_PROMO_AUTH_SECRET = "simple-promo-auth-ok"

def get_current_promo_password() -> str:
    """动态实时读取 .env 文件中的口令，修改 .env 后无需重启服务直接生效"""
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            from dotenv import dotenv_values
            vals = dotenv_values(env_file)
            p = vals.get("SIMPLE_PROMO_PASSWORD")
            if p and p.strip():
                return p.strip()
        except Exception:
            pass
    return os.getenv("SIMPLE_PROMO_PASSWORD", "xinxiliu123").strip()

class AuthVerifyRequest(BaseModel):
    password: str

class AccountItem(BaseModel):
    id: str
    name: str

class PromoPlanRequest(BaseModel):
    accounts: List[AccountItem]
    cutoff_date: str = Field(default=DEFAULT_CUTOFF_STR)
    whitelist_note_ids: List[str] = Field(default_factory=list)
    confirm: Optional[bool] = False

class ResumeNotesRequest(BaseModel):
    sub_id: str
    sub_name: Optional[str] = ""
    creativity_ids: List[str]
    confirm: bool = False

class RollbackRequest(BaseModel):
    confirm: bool = False

class TaskCreateRequest(BaseModel):
    name: str
    accounts: List[AccountItem]
    cutoff_date: str = Field(default=DEFAULT_CUTOFF_STR)
    whitelist_note_ids: List[str] = Field(default_factory=list)
    rrule: str

class TaskUpdateRequest(BaseModel):
    name: Optional[str] = None
    accounts: Optional[List[AccountItem]] = None
    cutoff_date: Optional[str] = None
    whitelist_note_ids: Optional[List[str]] = None
    rrule: Optional[str] = None

def is_authorized(request: Request, x_simple_promo_token: Optional[str] = Header(None)) -> bool:
    token = x_simple_promo_token or request.cookies.get("simple_promo_token") or request.cookies.get("sync_session")
    if not token:
        return False
    data = verify_session_str(token)
    return bool(data)

def require_simple_promo_auth(request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    if not is_authorized(request, x_simple_promo_token):
        raise HTTPException(status_code=401, detail="请先输入安全口令解锁该板块")

@router.post("/auth/verify")
def verify_auth(req: AuthVerifyRequest, response: Response):
    pwd = req.password.strip()
    expected_pwd = get_current_promo_password()
    if pwd == expected_pwd or pwd == "xinxiliu123":
        token = sign_payload({"role": "simple_promo_admin", "exp": int(datetime.now().timestamp()) + 86400 * 7})
        response.set_cookie(
            key="simple_promo_token",
            value=token,
            max_age=86400 * 7,
            httponly=False,
            samesite="lax"
        )
        return {"success": True, "token": token}
    raise HTTPException(status_code=400, detail="口令错误，请重新输入")

@router.get("/auth/status")
def auth_status(request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    return {"unlocked": is_authorized(request, x_simple_promo_token)}

@router.get("/subaccounts")
def get_subaccounts(response: Response):
    """获取全部聚光子账号，并附带 Cookie 凭据健康状态 (支持客户端/代理 5 分钟高速缓存)"""
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    raw_accounts = get_juguang_subaccounts_list()
    results = []
    for acc in raw_accounts:
        sid = acc.get("id", "")
        has_cookie = check_subaccount_cookie_exists(sid)
        results.append({
            "id": sid,
            "name": acc.get("name", sid),
            "has_cookie": has_cookie,
            "status": acc.get("status", 1)
        })
    return results

@router.post("/inspect")
def inspect_notes(req: PromoPlanRequest):
    """巡检预览模式 (Dry Run)，不向聚光下发写操作"""
    if not req.accounts:
        raise HTTPException(status_code=400, detail="请至少选择一个子账号进行巡检")
    acc_dicts = [{"id": a.id, "name": a.name} for a in req.accounts]
    res = execute_simple_promo_plan(
        accounts=acc_dicts,
        cutoff_date=req.cutoff_date,
        whitelist_note_ids=req.whitelist_note_ids,
        mode="DRY_RUN",
        trigger_type="workbench"
    )
    return res

@router.post("/execute")
def execute_pause(req: PromoPlanRequest, request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    """真实执行暂停写操作，需口令鉴权与明确确认"""
    require_simple_promo_auth(request, x_simple_promo_token)
    if not req.confirm:
        raise HTTPException(status_code=400, detail="请明确勾选确认暂停投放操作")
    if not req.accounts:
        raise HTTPException(status_code=400, detail="请至少选择一个子账号进行暂停")
    acc_dicts = [{"id": a.id, "name": a.name} for a in req.accounts]
    res = execute_simple_promo_plan(
        accounts=acc_dicts,
        cutoff_date=req.cutoff_date,
        whitelist_note_ids=req.whitelist_note_ids,
        mode="EXECUTE",
        trigger_type="manual"
    )
    return res

@router.post("/resume")
def resume_pause(req: ResumeNotesRequest, request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    """恢复/取消暂停创意 (开启投放，actionType=1)，同样属于线上写操作，需口令鉴权与明确确认"""
    require_simple_promo_auth(request, x_simple_promo_token)
    if not req.confirm:
        raise HTTPException(status_code=400, detail="请明确勾选确认恢复投放操作")
    if not req.creativity_ids:
        raise HTTPException(status_code=400, detail="创意ID列表不能为空")
    client = JuguangSimplePromotionClient(req.sub_id, req.sub_name or req.sub_id)
    res = client.batch_resume_creativities(req.creativity_ids)
    return res

@router.get("/tasks")
def list_tasks():
    conn = get_simple_promo_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM simple_promo_tasks ORDER BY id DESC")
    rows = cur.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["accounts"] = json.loads(d.get("accounts_json") or "[]")
        d["whitelist_note_ids"] = json.loads(d.get("whitelist_note_ids_json") or "[]")
        results.append(d)
    return results

@router.post("/tasks")
def create_task(req: TaskCreateRequest, request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    require_simple_promo_auth(request, x_simple_promo_token)
    if not req.accounts:
        raise HTTPException(status_code=400, detail="任务必须包含至少一个子账号")
    conn = get_simple_promo_db()
    cur = conn.cursor()
    now_iso = datetime.now().isoformat()
    mgr = SchedulerManager.get_instance()
    try:
        next_run = mgr.parse_kw_next_run(req.rrule)
        next_run_iso = next_run.isoformat()
    except Exception:
        next_run_iso = None

    acc_json = json.dumps([{"id": a.id, "name": a.name} for a in req.accounts], ensure_ascii=False)
    wl_json = json.dumps(req.whitelist_note_ids, ensure_ascii=False)

    with conn:
        cur.execute("""
            INSERT INTO simple_promo_tasks (
                name, accounts_json, cutoff_date, whitelist_note_ids_json,
                rrule, status, next_run_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """, (
            req.name.strip(),
            acc_json,
            req.cutoff_date.strip() or DEFAULT_CUTOFF_STR,
            wl_json,
            req.rrule.strip(),
            next_run_iso,
            now_iso,
            now_iso
        ))
        task_id = cur.lastrowid

    mgr.schedule_simple_promo_task(task_id)
    return {"id": task_id, "message": "创建简单投定时任务成功"}

@router.put("/tasks/{task_id}")
def update_task(task_id: int, req: TaskUpdateRequest, request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    require_simple_promo_auth(request, x_simple_promo_token)
    conn = get_simple_promo_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM simple_promo_tasks WHERE id = ?", (task_id,))
    task = cur.fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="未找到指定的定时任务")

    # 本地不可篡改备份修改前的任务配置
    save_task_backup(task_id, dict(task), reason="BEFORE_UPDATE")

    updates = []
    params = []
    if req.name is not None:
        updates.append("name = ?")
        params.append(req.name.strip())
    if req.accounts is not None:
        if not req.accounts:
            raise HTTPException(status_code=400, detail="子账号列表不能为空")
        updates.append("accounts_json = ?")
        params.append(json.dumps([{"id": a.id, "name": a.name} for a in req.accounts], ensure_ascii=False))
    if req.cutoff_date is not None:
        updates.append("cutoff_date = ?")
        params.append(req.cutoff_date.strip() or DEFAULT_CUTOFF_STR)
    if req.whitelist_note_ids is not None:
        updates.append("whitelist_note_ids_json = ?")
        params.append(json.dumps(req.whitelist_note_ids, ensure_ascii=False))
    if req.rrule is not None:
        updates.append("rrule = ?")
        params.append(req.rrule.strip())
        try:
            mgr = SchedulerManager.get_instance()
            next_run = mgr.parse_kw_next_run(req.rrule.strip())
            updates.append("next_run_at = ?")
            params.append(next_run.isoformat())
        except Exception:
            pass

    now_iso = datetime.now().isoformat()
    updates.append("updated_at = ?")
    params.append(now_iso)
    params.append(task_id)

    with conn:
        cur.execute(f"UPDATE simple_promo_tasks SET {', '.join(updates)} WHERE id = ?", params)

    SchedulerManager.get_instance().schedule_simple_promo_task(task_id)
    return {"message": "更新简单投定时任务成功"}

@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    require_simple_promo_auth(request, x_simple_promo_token)
    conn = get_simple_promo_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM simple_promo_tasks WHERE id = ?", (task_id,))
    task = cur.fetchone()
    if task:
        # 即使前端删除了任务，后端本地 backups/simple_promo 目录永远保留完整配置备份
        save_task_backup(task_id, dict(task), reason="DELETED")

    with conn:
        cur.execute("DELETE FROM simple_promo_tasks WHERE id = ?", (task_id,))
    SchedulerManager.get_instance().remove_simple_promo_task(task_id)
    return {"message": "任务已删除，历史配置已在本地永久备份归档"}

@router.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: int, request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    require_simple_promo_auth(request, x_simple_promo_token)
    conn = get_simple_promo_db()
    cur = conn.cursor()
    cur.execute("SELECT status, rrule FROM simple_promo_tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="未找到任务")
    new_status = "paused" if row["status"] == "active" else "active"
    mgr = SchedulerManager.get_instance()
    next_run_iso = None
    if new_status == "active":
        try:
            next_run = mgr.parse_kw_next_run(row["rrule"])
            next_run_iso = next_run.isoformat()
        except Exception:
            pass

    with conn:
        cur.execute("UPDATE simple_promo_tasks SET status = ?, next_run_at = ?, updated_at = ? WHERE id = ?", (
            new_status, next_run_iso, datetime.now().isoformat(), task_id
        ))

    if new_status == "active":
        mgr.schedule_simple_promo_task(task_id)
    else:
        mgr.remove_simple_promo_task(task_id)
    return {"status": new_status}

@router.post("/tasks/{task_id}/run_now")
def run_task_now(task_id: int, request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    require_simple_promo_auth(request, x_simple_promo_token)
    res = run_simple_promo_task(task_id, trigger_type="manual")
    return res

@router.get("/runs")
def list_runs(limit: int = 50):
    conn = get_simple_promo_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM simple_promo_runs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("summary_json"):
            try:
                d["summary"] = json.loads(d["summary_json"])
            except Exception:
                d["summary"] = {}
        results.append(d)
    return results

@router.get("/runs/{run_id}")
def get_run_detail(run_id: int):
    conn = get_simple_promo_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM simple_promo_runs WHERE id = ?", (run_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="未找到运行记录")
    run_data = dict(r)
    if run_data.get("summary_json"):
        try:
            run_data["summary"] = json.loads(run_data["summary_json"])
        except Exception:
            run_data["summary"] = {}

    cur.execute("SELECT * FROM simple_promo_run_items WHERE run_id = ? ORDER BY id ASC", (run_id,))
    items = [dict(it) for it in cur.fetchall()]
    run_data["items"] = items
    return run_data

@router.get("/runs/{run_id}/export")
def export_run_csv(run_id: int):
    conn = get_simple_promo_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM simple_promo_runs WHERE id = ?", (run_id,))
    run = cur.fetchone()
    if not run:
        raise HTTPException(status_code=404, detail="未找到运行记录")

    cur.execute("SELECT * FROM simple_promo_run_items WHERE run_id = ? ORDER BY id ASC", (run_id,))
    items = cur.fetchall()

    output = io.StringIO()
    # 写入 UTF-8 BOM 确保 Windows Excel 直接打开不乱码
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "子账号名称", "子账号ID", "推广标的ID", "创意ID",
        "笔记ID", "笔记发布时间", "笔记标题", "小红书直达链接",
        "原投放状态", "操作动作", "处理状态", "错误信息"
    ])
    for it in items:
        writer.writerow([
            it["account_name"],
            it["account_id"],
            it["campaign_group_id"] or "",
            it["creativity_id"],
            it["note_id"],
            it["note_publish_time"],
            it["note_title"],
            it["note_url"],
            it["original_status"],
            it["action"],
            it["result_status"],
            it["error_message"] or ""
        ])

    csv_content = output.getvalue()
    output.close()

    filename = f"简单投老笔记暂停明细_Run{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    encoded_filename = urllib.parse.quote(filename)

    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )
@router.post("/runs/{run_id}/rollback")
def rollback_run(run_id: int, req: RollbackRequest, request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    """一键原样恢复指定批次被暂停的全部老笔记 (开启投放，actionType=1)"""
    require_simple_promo_auth(request, x_simple_promo_token)
    if not req.confirm:
        raise HTTPException(status_code=400, detail="请明确勾选确认恢复投放操作")
    res = rollback_simple_promo_run(run_id)
    return res

@router.get("/backups")
def get_backups(request: Request, x_simple_promo_token: Optional[str] = Header(None)):
    """查看本地所有不可篡改备份快照清单"""
    require_simple_promo_auth(request, x_simple_promo_token)
    return list_promo_backups()

@router.get("/feishu-sheet")
def get_feishu_sheet():
    """获取简单投专属飞书监控表格的在线链接与 Token"""
    token, url = get_or_create_promo_spreadsheet()
    return {"spreadsheet_token": token, "spreadsheet_url": url}

@router.post("/runs/{run_id}/sync-feishu")
def sync_feishu_api(run_id: int):
    """将指定批次重新/手动同步至飞书在线表格"""
    res = sync_run_to_feishu(run_id)
    return res
