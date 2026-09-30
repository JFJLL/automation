import sys
import os
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from feishu.client import FeishuClient, column_letter
from lingxi_service.client import fetch_lingxi_keywords, load_token, sync_token_from_oss
from lingxi_service.db import get_db
from core.database import acquire_task_lease, release_task_lease
from core.errors import (
    TaskNotFoundError,
    TaskAlreadyRunningError,
    DataValidationError,
    FeishuError
)

def build_lingxi_matrix(keywords: List[str], data: Dict[str, Dict[str, Any]], fetch_time_str: str) -> List[List[Any]]:
    """
    构建灵犀关键词数据矩阵：
    第一行：表头 [关键词, 覆盖人群数量, 统计时间]
    后续行：每个关键词的数据
    """
    header = ["关键词", "覆盖人群数量", "统计时间"]
    matrix = [header]
    for kw in keywords:
        item = data.get(kw) or {}
        cnt = item.get("user_cnt", 0)
        matrix.append([kw, cnt, fetch_time_str])
    return matrix

def write_matrix_to_sheet(feishu: FeishuClient, ss_token: str, sheet_id: str, matrix: List[List[Any]], col_chunk_size: int = 50):
    if not matrix:
        return
    total_cols = max(len(r) for r in matrix)
    total_rows = len(matrix)

    sheets = feishu.get_sheets(ss_token)
    curr_sheet = next((s for s in sheets if s["sheet_id"] == sheet_id), sheets[0])
    grid_props = curr_sheet.get("grid_properties", {})
    curr_cols = grid_props.get("column_count", 20)
    curr_rows = grid_props.get("row_count", 200)

    if total_cols > curr_cols:
        add_cols = total_cols - curr_cols + 10
        try:
            feishu.add_columns(ss_token, sheet_id, add_cols)
        except Exception as e:
            print(f"[Feishu] Add columns warning: {e}")

    if total_rows > curr_rows:
        add_rows = total_rows - curr_rows + 50
        try:
            feishu.add_rows(ss_token, sheet_id, add_rows)
        except Exception as e:
            print(f"[Feishu] Add rows warning: {e}")

    for start_c in range(0, total_cols, col_chunk_size):
        end_c = min(start_c + col_chunk_size, total_cols)
        sub_matrix = [row[start_c:end_c] for row in matrix]
        start_letter = column_letter(start_c + 1)
        end_letter = column_letter(end_c)
        chunk_range = f"{sheet_id}!{start_letter}1:{end_letter}{total_rows}"
        feishu.write_cells(ss_token, chunk_range, sub_matrix)

def direct_create_feishu_sheet(keywords: List[str], title: Optional[str] = None) -> Dict[str, Any]:
    """直接生成灵犀关键词飞书在线表格"""
    from app.config import SHARED_FOLDER_TOKEN
    feishu = FeishuClient()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet_title = title or f"小红书灵犀关键词覆盖人数分析_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    fetch_res = fetch_lingxi_keywords(keywords)
    matrix = build_lingxi_matrix(keywords, fetch_res["results"], now_str)

    meta = feishu.create_spreadsheet(title=sheet_title, folder_token=SHARED_FOLDER_TOKEN or None)
    ss_token = meta.get("spreadsheet_token") or meta.get("token")
    ss_url = meta.get("url")

    sheets = feishu.get_sheets(ss_token)
    sheet_id = sheets[0]["sheet_id"]

    write_matrix_to_sheet(feishu, ss_token, sheet_id, matrix)

    try:
        feishu.set_public_permission(ss_token, edit=True)
    except Exception as e:
        print(f"[Feishu Permission Error] {e}")

    return {
        "spreadsheet_token": ss_token,
        "spreadsheet_url": ss_url,
        "sheet_id": sheet_id,
        "title": sheet_title,
        "keywords_count": len(keywords),
        "successful_keywords": fetch_res["successful_keywords"],
        "failed_keywords": fetch_res["failed_keywords"]
    }

def create_lingxi_task(
    name: str,
    keywords: List[str],
    spreadsheet_token: str,
    spreadsheet_url: str,
    update_mode: str = "overwrite",
    rrule: str = "FREQ=DAILY;BYHOUR=9;BYMINUTE=30",
    folder_token: Optional[str] = None
) -> int:
    """创建灵犀关键词定时监控任务"""
    from core.scheduler_manager import SchedulerManager
    now_iso = datetime.now().isoformat()
    kw_json = json.dumps(list(dict.fromkeys(keywords)), ensure_ascii=False)

    conn = get_db()
    with conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO lingxi_tasks (
                name, keywords_json, removed_keywords_json, folder_token,
                spreadsheet_token, spreadsheet_url, update_mode,
                rrule, status, created_at, updated_at
            ) VALUES (?, ?, '[]', ?, ?, ?, ?, ?, 'active', ?, ?)
        """, (
            name, kw_json, folder_token, spreadsheet_token,
            spreadsheet_url, update_mode, rrule, now_iso, now_iso
        ))
        task_id = cur.lastrowid

    # 调度任务
    try:
        mgr = SchedulerManager.get_instance()
        mgr.schedule_lingxi_task(task_id)
    except Exception as e:
        print(f"[Scheduler] Schedule lingxi task {task_id} warning: {e}")

    return task_id

def run_lingxi_task(task_id: int, trigger_type: str = "manual") -> Dict[str, Any]:
    """执行灵犀关键词定时任务或手动运行"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM lingxi_tasks WHERE id = ?", (task_id,))
    task = cur.fetchone()
    if not task:
        raise TaskNotFoundError(f"未找到灵犀任务 ID={task_id}")

    task_dict = dict(task)
    task_name = task_dict["name"]
    task_key = f"lingxi_task_{task_id}"

    # 竞态锁防重
    if not acquire_task_lease(conn, task_key, owner=f"run_{trigger_type}", lease_seconds=600):
        raise TaskAlreadyRunningError(f"任务 [{task_name}] 当前正在运行中，请勿重复触发")

    keywords: List[str] = json.loads(task_dict["keywords_json"])
    update_mode = task_dict.get("update_mode", "overwrite")
    ss_token = task_dict["spreadsheet_token"]
    ss_url = task_dict["spreadsheet_url"]

    start_time = datetime.now()
    start_iso = start_time.isoformat()

    with conn:
        cur.execute("""
            INSERT INTO lingxi_runs (
                task_id, task_name, trigger_type, started_at, status, keywords_count, spreadsheet_url
            ) VALUES (?, ?, ?, ?, 'running', ?, ?)
        """, (task_id, task_name, trigger_type, start_iso, len(keywords), ss_url))
        run_id = cur.lastrowid

    feishu = FeishuClient()
    try:
        fetch_res = fetch_lingxi_keywords(keywords)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        matrix = build_lingxi_matrix(keywords, fetch_res["results"], now_str)

        sheets = feishu.get_sheets(ss_token)
        sheet_id = sheets[0]["sheet_id"]

        if update_mode == "append":
            # 追加模式：找到现有行数，跳过表头，向后追加
            grid_props = sheets[0].get("grid_properties", {})
            curr_rows = grid_props.get("row_count", 0)
            # 直接写入追加数据 (去掉表头)
            append_matrix = matrix[1:]
            if append_matrix:
                # 先检查飞书表格已填写的范围
                start_row = curr_rows + 1
                write_matrix_to_sheet(feishu, ss_token, sheet_id, append_matrix)
        else:
            # 覆盖模式：从 A1 开始重写完整数据
            write_matrix_to_sheet(feishu, ss_token, sheet_id, matrix)

        finish_time = datetime.now()
        duration_ms = int((finish_time - start_time).total_seconds() * 1000)

        with conn:
            cur.execute("""
                UPDATE lingxi_runs SET
                    finished_at = ?, status = 'success', duration_ms = ?,
                    successful_keywords = ?, failed_keywords = ?, message = '执行完成'
                WHERE id = ?
            """, (
                finish_time.isoformat(), duration_ms,
                json.dumps(fetch_res["successful_keywords"], ensure_ascii=False),
                json.dumps(fetch_res["failed_keywords"], ensure_ascii=False),
                run_id
            ))
            cur.execute("""
                UPDATE lingxi_tasks SET
                    last_run_at = ?, last_status = 'success', last_error = NULL, updated_at = ?
                WHERE id = ?
            """, (finish_time.isoformat(), finish_time.isoformat(), task_id))

        return {
            "run_id": run_id,
            "status": "success",
            "duration_ms": duration_ms,
            "successful_keywords": fetch_res["successful_keywords"],
            "failed_keywords": fetch_res["failed_keywords"]
        }
    except Exception as e:
        finish_time = datetime.now()
        duration_ms = int((finish_time - start_time).total_seconds() * 1000)
        err_msg = str(e)
        with conn:
            cur.execute("""
                UPDATE lingxi_runs SET
                    finished_at = ?, status = 'failed', duration_ms = ?,
                    message = '执行失败', error_detail = ?
                WHERE id = ?
            """, (finish_time.isoformat(), duration_ms, err_msg, run_id))
            cur.execute("""
                UPDATE lingxi_tasks SET
                    last_run_at = ?, last_status = 'failed', last_error = ?, updated_at = ?
                WHERE id = ?
            """, (finish_time.isoformat(), err_msg, finish_time.isoformat(), task_id))
        raise e
    finally:
        release_task_lease(conn, task_key)

def append_keywords_to_lingxi_task(task_id: int, new_keywords: List[str]) -> List[str]:
    conn = get_db()
    with conn:
        cur = conn.cursor()
        cur.execute("SELECT keywords_json FROM lingxi_tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if not row:
            raise TaskNotFoundError(f"未找到灵犀任务 ID={task_id}")
        existing: List[str] = json.loads(row["keywords_json"])
        merged = list(dict.fromkeys(existing + new_keywords))
        now_iso = datetime.now().isoformat()
        cur.execute("UPDATE lingxi_tasks SET keywords_json = ?, updated_at = ? WHERE id = ?", (json.dumps(merged, ensure_ascii=False), now_iso, task_id))
    return merged

def remove_keywords_from_lingxi_task(task_id: int, removed_keywords: List[str]) -> List[str]:
    conn = get_db()
    with conn:
        cur = conn.cursor()
        cur.execute("SELECT keywords_json, removed_keywords_json FROM lingxi_tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if not row:
            raise TaskNotFoundError(f"未找到灵犀任务 ID={task_id}")
        existing: List[str] = json.loads(row["keywords_json"])
        old_removed: List[str] = json.loads(row["removed_keywords_json"] or "[]")

        rem_set = set(removed_keywords)
        remaining = [k for k in existing if k not in rem_set]
        new_removed = list(dict.fromkeys(old_removed + removed_keywords))
        now_iso = datetime.now().isoformat()
        cur.execute("UPDATE lingxi_tasks SET keywords_json = ?, removed_keywords_json = ?, updated_at = ? WHERE id = ?", (
            json.dumps(remaining, ensure_ascii=False),
            json.dumps(new_removed, ensure_ascii=False),
            now_iso,
            task_id
        ))
    return remaining
