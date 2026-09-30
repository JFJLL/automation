import sys
import os
import json
import time
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from feishu.client import FeishuClient, column_letter
from keyword_service.client import fetch_keywords_insight
from keyword_service.db import get_db
from core.business_time import latest_keyword_available_date, validate_keyword_date_range, now_business_tz
from core.database import acquire_task_lease, release_task_lease
from core.errors import (
    TaskNotFoundError,
    TaskAlreadyRunningError,
    DataValidationError,
    FeishuError,
    KeywordError
)

def build_sheet_matrix(keywords: List[str], dates: List[str], data: Dict[str, Dict[str, Any]]) -> List[List[Any]]:
    row1 = ["关键词"]
    row2 = [""]
    for d in dates:
        row1.extend([d, "", "", ""])
        row2.extend(["搜索指数", "广告曝光量", "广告笔记数", "平均市场出价"])
        
    matrix = [row1, row2]
    for kw in keywords:
        kw_daily = data.get(kw) or {}
        row = [kw]
        for d in dates:
            item = kw_daily.get(d)
            if item:
                row.append(item.get("search_num", 0))
                row.append(item.get("imp_num", 0))
                row.append(item.get("note_num", 0))
                row.append(item.get("bid", 0.0))
            else:
                row.extend([0, 0, 0, 0.0])
        matrix.append(row)
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
        add_cols = total_cols - curr_cols + 20
        try:
            feishu.request("POST", f"sheets/v2/spreadsheets/{ss_token}/dimension_range", json={
                "dimension": {
                    "sheetId": sheet_id,
                    "majorDimension": "COLUMNS",
                    "length": add_cols
                }
            })
        except Exception as e:
            print(f"[Feishu] Dimension expand cols warning: {e}")
            
    if total_rows > curr_rows:
        add_rows = total_rows - curr_rows + 50
        try:
            feishu.request("POST", f"sheets/v2/spreadsheets/{ss_token}/dimension_range", json={
                "dimension": {
                    "sheetId": sheet_id,
                    "majorDimension": "ROWS",
                    "length": add_rows
                }
            })
        except Exception as e:
            print(f"[Feishu] Dimension expand rows warning: {e}")

    for c_start in range(1, total_cols + 1, col_chunk_size):
        c_end = min(c_start + col_chunk_size - 1, total_cols)
        start_letter = column_letter(c_start)
        end_letter = column_letter(c_end)
        range_str = f"{sheet_id}!{start_letter}1:{end_letter}{total_rows}"
        
        chunk_rows = []
        for r in matrix:
            sub = r[c_start - 1 : c_end]
            if len(sub) < (c_end - c_start + 1):
                sub = sub + [""] * ((c_end - c_start + 1) - len(sub))
            chunk_rows.append(sub)
            
        feishu.request("PUT", f"sheets/v2/spreadsheets/{ss_token}/values", json={
            "valueRange": {"range": range_str, "values": chunk_rows}
        })

def merge_date_headers(feishu: FeishuClient, ss_token: str, sheet_id: str, num_dates: int, retry_limit: int = 3):
    if num_dates <= 0:
        return
        
    required_cols = 1 + num_dates * 4
    try:
        sheets = feishu.get_sheets(ss_token)
        curr_sheet = next((s for s in sheets if s["sheet_id"] == sheet_id), None)
        if curr_sheet:
            curr_cols = curr_sheet.get("grid_properties", {}).get("column_count", 20)
            if curr_cols < required_cols:
                feishu.request("POST", f"sheets/v2/spreadsheets/{ss_token}/dimension_range", json={
                    "dimension": {"sheetId": sheet_id, "majorDimension": "COLUMNS", "length": required_cols - curr_cols + 20}
                })
    except Exception as e:
        print(f"[Feishu] Ensure column count warning: {e}")
        
    # 合并 A1:A2 为 "关键词"
    for attempt in range(retry_limit):
        try:
            feishu.merge_cells(ss_token, f"{sheet_id}!A1:A2")
            break
        except Exception as e:
            time.sleep(0.1 * (attempt + 1))
        
    # 依序合并每个日期的 4 个字段单元格 (B1:E1, F1:I1, J1:M1...)
    for idx in range(num_dates):
        c_start = 2 + idx * 4
        c_end = c_start + 3
        rng = f"{sheet_id}!{column_letter(c_start)}1:{column_letter(c_end)}1"
        for attempt in range(retry_limit):
            try:
                feishu.merge_cells(ss_token, rng)
                break
            except Exception:
                time.sleep(0.08 * (attempt + 1))

def parse_existing_sheet_history(
    existing_rows: List[List[Any]]
) -> Tuple[List[str], Dict[str, Dict[str, List[Any]]]]:
    """
    解析飞书现有表格历史数据：
    返回：
      existing_dates: [date_str1, date_str2, ...] 按列出现顺序
      keyword_date_metrics: { kw: { date_str: [search, imp, note, bid] } }
    核心目的：按【日期 key】而非【列物理索引】对齐指标，杜绝减词或日期滚动导致的严重数据错位！
    """
    if not existing_rows or len(existing_rows) < 2:
        return [], {}
        
    row0 = existing_rows[0]
    existing_dates = []
    date_col_indices = {} # date_str -> col_idx in row
    
    col_idx = 1
    while col_idx < len(row0):
        cell_val = str(row0[col_idx]).strip() if col_idx < len(row0) and row0[col_idx] else ""
        if len(cell_val) == 10 and cell_val[4] == "-" and cell_val[7] == "-":
            existing_dates.append(cell_val)
            date_col_indices[cell_val] = col_idx
            col_idx += 4
        else:
            col_idx += 1
            
    keyword_date_metrics: Dict[str, Dict[str, List[Any]]] = {}
    for r in existing_rows[2:]:
        if not r or not str(r[0]).strip():
            continue
        kw_name = str(r[0]).strip()
        kw_dict = {}
        for d_str, c_idx in date_col_indices.items():
            metrics = []
            for offset in range(4):
                val_idx = c_idx + offset
                if val_idx < len(r) and r[val_idx] not in (None, ""):
                    metrics.append(r[val_idx])
                else:
                    metrics.append(0 if offset < 3 else 0.0)
            kw_dict[d_str] = metrics
        keyword_date_metrics[kw_name] = kw_dict
        
    return existing_dates, keyword_date_metrics

def direct_create_feishu_sheet(
    keywords: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    title: Optional[str] = None
) -> Dict[str, Any]:
    started_at = datetime.now().isoformat()
    t0 = time.time()
    if not title:
        title = f"关键词搜索指数监控_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
    # 1. 优先抓取数据并校验 (严格模式：任意词失败直接报错，不创建表格)
    insight_res = fetch_keywords_insight(keywords, start_date, end_date, strict=True)
    kws = insight_res["keywords"]
    dates = insight_res["dates"]
    data = insight_res["data"]
    
    # 2. 构建飞书表格内容
    matrix = build_sheet_matrix(kws, dates, data)
    
    # 3. 只有全部拉取成功后，才创建飞书表格并写入
    feishu = FeishuClient()
    folder_token = feishu.get_or_create_shared_folder()
    ss_meta = feishu.create_spreadsheet(title=title, folder_token=folder_token)
    ss_token = ss_meta["spreadsheet_token"]
    ss_url = ss_meta["url"]
    
    sheets = feishu.get_sheets(ss_token)
    first_sheet_id = sheets[0]["sheet_id"] if sheets else "0"
    
    write_matrix_to_sheet(feishu, ss_token, first_sheet_id, matrix)
    merge_date_headers(feishu, ss_token, first_sheet_id, len(dates))
    feishu.set_sheet_public_editable(ss_token)
    
    finished_at = datetime.now().isoformat()
    duration_ms = int((time.time() - t0) * 1000)
    
    with get_db() as conn:
        conn.execute("""
            INSERT INTO keyword_runs (
                task_id, task_name, trigger_type, started_at, finished_at,
                status, keywords_count, days_count, spreadsheet_url, message,
                duration_ms, successful_keywords, empty_keywords, failed_keywords
            ) VALUES (?, ?, 'direct_create', ?, ?, 'success', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            None, title, started_at, finished_at, len(kws), len(dates),
            ss_url, f"成功直接生成飞书表格，写入 {len(kws)} 个词、{len(dates)} 天数据并合并日期表头",
            duration_ms, json.dumps(insight_res["successful_keywords"], ensure_ascii=False),
            json.dumps(insight_res["empty_keywords"], ensure_ascii=False),
            json.dumps(insight_res["failed_keywords"], ensure_ascii=False)
        ))
        conn.commit()
        
    return {
        "success": True,
        "spreadsheet_title": title,
        "spreadsheet_token": ss_token,
        "spreadsheet_url": ss_url,
        "keywords_count": len(kws),
        "days_count": len(dates),
        "rows_count": len(matrix)
    }

def create_keyword_task(
    task_name: str,
    keywords: List[str],
    update_mode: str = "overwrite",
    rrule_str: str = "FREQ=DAILY;BYHOUR=12;BYMINUTE=30",
    days_range: int = 90
) -> Dict[str, Any]:
    started_at = datetime.now().isoformat()
    t0 = time.time()
    
    clean_name = task_name.strip()
    if not clean_name:
        raise DataValidationError("任务名称不能为空")
    if not keywords:
        raise DataValidationError("关键词列表不能为空")
    if update_mode not in ("overwrite", "append"):
        raise DataValidationError(f"不支持的 update_mode: {update_mode}，必须为 'overwrite' 或 'append'")
    if days_range < 1 or days_range > 90:
        raise DataValidationError(f"days_range 必须在 1~90 天之间 (请求: {days_range})")
        
    max_avail = latest_keyword_available_date()
    end_date_str = max_avail.isoformat()
    start_date_str = (max_avail - timedelta(days=days_range - 1)).isoformat()
    
    # 1. 优先拉取真实数据 (strict=True: 任何词失败不创建孤儿表格)
    insight_res = fetch_keywords_insight(keywords, start_date_str, end_date_str, strict=True)
    matrix = build_sheet_matrix(insight_res["keywords"], insight_res["dates"], insight_res["data"])
    
    # 2. 抓取全部成功后，再创建飞书表格
    feishu = FeishuClient()
    folder_token = feishu.get_or_create_shared_folder()
    ss_meta = feishu.create_spreadsheet(title=clean_name, folder_token=folder_token)
    ss_token = ss_meta["spreadsheet_token"]
    ss_url = ss_meta["url"]
    
    sheets = feishu.get_sheets(ss_token)
    first_sheet_id = sheets[0]["sheet_id"] if sheets else "0"
    
    write_matrix_to_sheet(feishu, ss_token, first_sheet_id, matrix)
    merge_date_headers(feishu, ss_token, first_sheet_id, len(insight_res["dates"]))
    feishu.set_sheet_public_editable(ss_token)
    
    now_str = datetime.now().isoformat()
    duration_ms = int((time.time() - t0) * 1000)
    
    # 3. 写入数据库
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO keyword_tasks (
                name, keywords_json, folder_token, spreadsheet_token, spreadsheet_url,
                removed_keywords_json, update_mode, days_range, rrule, status, last_run_at, last_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, '[]', ?, ?, ?, 'active', ?, 'success', ?, ?)
        """, (
            clean_name, json.dumps(insight_res["keywords"], ensure_ascii=False),
            folder_token, ss_token, ss_url, update_mode, days_range, rrule_str,
            now_str, now_str, now_str
        ))
        task_id = cursor.lastrowid
        
        cursor.execute("""
            INSERT INTO keyword_runs (
                task_id, task_name, trigger_type, started_at, finished_at,
                status, keywords_count, days_count, spreadsheet_url, message,
                duration_ms, successful_keywords, empty_keywords, failed_keywords
            ) VALUES (?, ?, 'task_init', ?, ?, 'success', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id, clean_name, started_at, now_str, len(insight_res["keywords"]),
            len(insight_res["dates"]), ss_url, "任务创建初始化数据写入成功",
            duration_ms, json.dumps(insight_res["successful_keywords"], ensure_ascii=False),
            json.dumps(insight_res["empty_keywords"], ensure_ascii=False),
            json.dumps(insight_res["failed_keywords"], ensure_ascii=False)
        ))
        conn.commit()
        
    return {
        "success": True,
        "task_id": task_id,
        "task_name": clean_name,
        "spreadsheet_url": ss_url,
        "spreadsheet_token": ss_token
    }

def run_keyword_task(task_id: int, trigger_type: str = "manual") -> Dict[str, Any]:
    started_at = datetime.now().isoformat()
    t0 = time.time()
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM keyword_tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            raise TaskNotFoundError(f"关键词任务 #{task_id} 不存在")
            
        lease_key = f"keyword_task_{task_id}"
        if not acquire_task_lease(conn, lease_key, owner=f"run_{trigger_type}", lease_seconds=900):
            raise TaskAlreadyRunningError(f"任务 #{task_id} 正在执行中，请勿重复运行")
            
        task_name = task["name"]
        keywords = json.loads(task["keywords_json"] or "[]")
        task_dict = dict(task)
        removed_keywords = json.loads(task_dict.get("removed_keywords_json") or "[]")
        ss_token = task["spreadsheet_token"]
        ss_url = task["spreadsheet_url"]
        update_mode = task_dict.get("update_mode", "overwrite")
        days_range = task["days_range"] or 90
        
        cursor.execute("""
            INSERT INTO keyword_runs (
                task_id, task_name, trigger_type, started_at, status,
                keywords_count, days_count, spreadsheet_url, message
            ) VALUES (?, ?, ?, ?, 'running', ?, 0, ?, '任务开始同步中...')
        """, (task_id, task_name, trigger_type, started_at, len(keywords), ss_url))
        run_id = cursor.lastrowid
        conn.commit()

    try:
        max_avail = latest_keyword_available_date()
        end_date_str = max_avail.isoformat()
        start_date_str = (max_avail - timedelta(days=days_range - 1)).isoformat()
        
        feishu = FeishuClient()
        sheets = feishu.get_sheets(ss_token)
        first_sheet_id = sheets[0]["sheet_id"] if sheets else "0"
        
        insight_res = fetch_keywords_insight(keywords, start_date_str, end_date_str, strict=True)
        new_dates = insight_res["dates"]
        new_data = insight_res["data"]
        
        last_row = feishu.find_last_row_index(ss_token, first_sheet_id)
        existing_rows = []
        if last_row >= 2:
            existing_rows = feishu.read_values(ss_token, first_sheet_id, f"A1:ZZ{last_row}") or []
            
        existing_dates, old_kw_history = parse_existing_sheet_history(existing_rows)
        
        if update_mode == "append" and existing_dates:
            combined_date_set = set(existing_dates) | set(new_dates)
            target_dates = sorted(list(combined_date_set))
        else:
            target_dates = new_dates
            
        row1 = ["关键词"]
        row2 = [""]
        for d in target_dates:
            row1.extend([d, "", "", ""])
            row2.extend(["搜索指数", "广告曝光量", "广告笔记数", "平均市场出价"])
        matrix = [row1, row2]
        
        all_target_keywords = []
        if existing_rows and len(existing_rows) >= 3:
            for r in existing_rows[2:]:
                if r and str(r[0]).strip():
                    kw = str(r[0]).strip()
                    if kw not in all_target_keywords:
                        all_target_keywords.append(kw)
                        
        for kw in keywords:
            if kw not in all_target_keywords:
                all_target_keywords.append(kw)
                
        for kw in all_target_keywords:
            row = [kw]
            is_removed = kw in removed_keywords
            kw_hist = old_kw_history.get(kw, {})
            kw_new = new_data.get(kw, {}) if not is_removed else {}
            
            for d in target_dates:
                if not is_removed and kw in new_data and kw_new and d in kw_new:
                    item = kw_new[d]
                    row.extend([item.get("search_num", 0), item.get("imp_num", 0), item.get("note_num", 0), item.get("bid", 0.0)])
                elif d in kw_hist:
                    m = kw_hist[d]
                    row.extend(m)
                else:
                    row.extend([0, 0, 0, 0.0] if not is_removed else ["", "", "", ""])
            matrix.append(row)
            
        write_matrix_to_sheet(feishu, ss_token, first_sheet_id, matrix)
        merge_date_headers(feishu, ss_token, first_sheet_id, len(target_dates))
        
        finished_at = datetime.now().isoformat()
        duration_ms = int((time.time() - t0) * 1000)
        
        with get_db() as conn:
            conn.execute("""
                UPDATE keyword_tasks SET last_run_at = ?, last_status = 'success', last_error = NULL, updated_at = ? WHERE id = ?
            """, (finished_at, finished_at, task_id))
            conn.execute("""
                UPDATE keyword_runs SET
                    finished_at = ?, status = 'success', keywords_count = ?, days_count = ?,
                    duration_ms = ?, message = '同步更新成功',
                    successful_keywords = ?, empty_keywords = ?, failed_keywords = ?
                WHERE id = ?
            """, (
                finished_at, len(keywords), len(target_dates), duration_ms,
                json.dumps(insight_res["successful_keywords"], ensure_ascii=False),
                json.dumps(insight_res["empty_keywords"], ensure_ascii=False),
                json.dumps(insight_res["failed_keywords"], ensure_ascii=False),
                run_id
            ))
            conn.commit()
            
        return {
            "success": True,
            "task_id": task_id,
            "status": "success",
            "keywords_count": len(keywords),
            "days_count": len(target_dates),
            "duration_ms": duration_ms
        }
    except Exception as e:
        finished_at = datetime.now().isoformat()
        duration_ms = int((time.time() - t0) * 1000)
        err_msg = str(e)
        with get_db() as conn:
            conn.execute("""
                UPDATE keyword_tasks SET last_run_at = ?, last_status = 'failed', last_error = ?, updated_at = ? WHERE id = ?
            """, (finished_at, err_msg, finished_at, task_id))
            conn.execute("""
                UPDATE keyword_runs SET
                    finished_at = ?, status = 'failed', duration_ms = ?,
                    message = '同步执行异常', error_detail = ?
                WHERE id = ?
            """, (finished_at, duration_ms, err_msg, run_id))
            conn.commit()
        raise e
    finally:
        with get_db() as conn:
            release_task_lease(conn, f"keyword_task_{task_id}")

def append_keywords_to_task(task_id: int, new_keywords: List[str], sync_now: bool = False) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM keyword_tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            raise TaskNotFoundError(f"关键词任务 #{task_id} 不存在")
            
        current_kws = json.loads(task["keywords_json"] or "[]")
        task_dict = dict(task)
        removed_kws = json.loads(task_dict.get("removed_keywords_json") or "[]")
        
        added = []
        for kw in new_keywords:
            k = kw.strip()
            if k:
                if k in removed_kws:
                    removed_kws.remove(k)
                if k not in current_kws:
                    current_kws.append(k)
                    added.append(k)
                    
        now_str = datetime.now().isoformat()
        conn.execute("""
            UPDATE keyword_tasks SET keywords_json = ?, removed_keywords_json = ?, updated_at = ? WHERE id = ?
        """, (json.dumps(current_kws, ensure_ascii=False), json.dumps(removed_kws, ensure_ascii=False), now_str, task_id))
        conn.commit()
        
    if sync_now and added:
        run_keyword_task(task_id, trigger_type="append_sync")
        
    return {
        "success": True,
        "task_id": task_id,
        "added": added,
        "total_keywords": len(current_kws)
    }

def remove_keywords_from_task(task_id: int, remove_keywords: List[str]) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM keyword_tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            raise TaskNotFoundError(f"关键词任务 #{task_id} 不存在")
            
        current_kws = json.loads(task["keywords_json"] or "[]")
        task_dict = dict(task)
        removed_kws = json.loads(task_dict.get("removed_keywords_json") or "[]")
        
        removed = []
        for kw in remove_keywords:
            k = kw.strip()
            if k in current_kws:
                current_kws.remove(k)
                removed.append(k)
                if k not in removed_kws:
                    removed_kws.append(k)
                    
        now_str = datetime.now().isoformat()
        conn.execute("""
            UPDATE keyword_tasks SET keywords_json = ?, removed_keywords_json = ?, updated_at = ? WHERE id = ?
        """, (json.dumps(current_kws, ensure_ascii=False), json.dumps(removed_kws, ensure_ascii=False), now_str, task_id))
        conn.commit()
        
    return {
        "success": True,
        "task_id": task_id,
        "removed": removed,
        "remaining_keywords": len(current_kws)
    }

