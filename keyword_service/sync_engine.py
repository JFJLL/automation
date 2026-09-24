import sys
import os
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

console_dir = str(Path(__file__).parent.parent / "sync_console")
if console_dir not in sys.path:
    sys.path.insert(0, console_dir)

from feishu.client import FeishuClient, column_letter
from keyword_service.client import fetch_keywords_insight
from keyword_service.db import get_db

def build_sheet_matrix(keywords: List[str], dates: List[str], data: Dict[str, Dict[str, Any]]) -> List[List[Any]]:
    # Row 1: Dates header
    row1 = ["关键词"]
    # Row 2: 4 metrics header
    row2 = [""]
    for d in dates:
        row1.extend([d, "", "", ""])
        row2.extend(["搜索指数", "广告曝光量", "广告笔记数", "平均市场出价"])
        
    matrix = [row1, row2]
    
    # Rows 3+: Keyword data
    for kw in keywords:
        kw_daily = data.get(kw, {})
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
    
    # 检查并扩充列数与行数
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

    # 分块写入列，避免触发 Feishu 90202 范围越界
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

def merge_date_headers(feishu: FeishuClient, ss_token: str, sheet_id: str, num_dates: int, max_workers: int = 8):
    token = feishu.get_token()
    
    # 1. 合并 A1:A2 为 "关键词" 单元格
    try:
        feishu.session.post(
            f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{ss_token}/merge_cells",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"range": f"{sheet_id}!A1:A2", "mergeType": "MERGE_ALL"},
            timeout=10
        )
    except Exception as e:
        print(f"[Feishu] Merge A1:A2 warning: {e}")
        
    # 2. 依次合并每个日期的4个字段单元格 (B1:E1, F1:I1, J1:M1...)
    ranges = []
    for idx in range(num_dates):
        c_start = 2 + idx * 4
        c_end = c_start + 3
        ranges.append(f"{sheet_id}!{column_letter(c_start)}1:{column_letter(c_end)}1")
        
    def merge_one(rng):
        try:
            r = feishu.session.post(
                f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{ss_token}/merge_cells",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"range": rng, "mergeType": "MERGE_ALL"},
                timeout=10
            )
            return r.status_code == 200
        except Exception:
            return False
            
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        list(ex.map(merge_one, ranges))

def direct_create_feishu_sheet(
    keywords: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    title: Optional[str] = None
) -> Dict[str, Any]:
    started_at = datetime.now().isoformat()
    if not title:
        title = f"关键词搜索指数监控_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
    # 1. 抓取数据
    insight_res = fetch_keywords_insight(keywords, start_date, end_date)
    kws = insight_res["keywords"]
    dates = insight_res["dates"]
    data = insight_res["data"]
    
    # 2. 构建飞书表格内容
    matrix = build_sheet_matrix(kws, dates, data)
    
    # 3. 创建飞书在线表格
    feishu = FeishuClient()
    folder_token = feishu.get_or_create_shared_folder()
    ss_meta = feishu.create_spreadsheet(title=title, folder_token=folder_token)
    ss_token = ss_meta["spreadsheet_token"]
    ss_url = ss_meta["url"]
    
    sheets = feishu.get_sheets(ss_token)
    first_sheet_id = sheets[0]["sheet_id"] if sheets else "0"
    
    # 写入行数据 (按列分块写入)
    write_matrix_to_sheet(feishu, ss_token, first_sheet_id, matrix)
    
    # 合并第一行每个日期的四个字段单元格
    merge_date_headers(feishu, ss_token, first_sheet_id, len(dates))
        
    feishu.set_sheet_public_editable(ss_token)
    finished_at = datetime.now().isoformat()
    
    # 4. 记录运行日志
    with get_db() as conn:
        conn.execute("""
            INSERT INTO keyword_runs (
                task_id, task_name, trigger_type, started_at, finished_at,
                status, keywords_count, days_count, spreadsheet_url, message
            ) VALUES (?, ?, 'direct_create', ?, ?, 'success', ?, ?, ?, ?)
        """, (
            None, title, started_at, finished_at, len(kws), len(dates),
            ss_url, f"成功直接生成飞书表格，写入 {len(kws)} 个词、{len(dates)} 天数据并合并日期表头"
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
    feishu = FeishuClient()
    folder_token = feishu.get_or_create_shared_folder()
    
    # 1. 建立对应飞书表格
    ss_meta = feishu.create_spreadsheet(title=task_name, folder_token=folder_token)
    ss_token = ss_meta["spreadsheet_token"]
    ss_url = ss_meta["url"]
    
    # 2. 初始拉取数据并写入
    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days_range)).strftime("%Y-%m-%d")
    insight_res = fetch_keywords_insight(keywords, start_date, end_date)
    matrix = build_sheet_matrix(insight_res["keywords"], insight_res["dates"], insight_res["data"])
    
    sheets = feishu.get_sheets(ss_token)
    first_sheet_id = sheets[0]["sheet_id"] if sheets else "0"
    
    write_matrix_to_sheet(feishu, ss_token, first_sheet_id, matrix)
    merge_date_headers(feishu, ss_token, first_sheet_id, len(insight_res["dates"]))
        
    feishu.set_sheet_public_editable(ss_token)
    now = datetime.now().isoformat()
    
    # 3. 存入数据库
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO keyword_tasks (
                name, keywords_json, folder_token, spreadsheet_token, spreadsheet_url,
                update_mode, days_range, rrule, status, last_run_at, last_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, 'success', ?, ?)
        """, (
            task_name, json.dumps(insight_res["keywords"], ensure_ascii=False),
            folder_token, ss_token, ss_url, update_mode, days_range, rrule_str,
            now, now, now
        ))
        task_id = cursor.lastrowid
        
        cursor.execute("""
            INSERT INTO keyword_runs (
                task_id, task_name, trigger_type, started_at, finished_at,
                status, keywords_count, days_count, spreadsheet_url, message
            ) VALUES (?, ?, 'task_init', ?, ?, 'success', ?, ?, ?, ?)
        """, (
            task_id, task_name, started_at, now, len(insight_res["keywords"]),
            len(insight_res["dates"]), ss_url, "任务创建初始化数据写入成功"
        ))
        conn.commit()
        
    return {
        "success": True,
        "task_id": task_id,
        "task_name": task_name,
        "spreadsheet_url": ss_url,
        "spreadsheet_token": ss_token
    }

def run_keyword_task(task_id: int, trigger_type: str = "manual") -> Dict[str, Any]:
    started_at = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM keyword_tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        
    if not task:
        raise ValueError(f"Task #{task_id} not found")
        
    task_name = task["name"]
    keywords = json.loads(task["keywords_json"] or "[]")
    ss_token = task["spreadsheet_token"]
    ss_url = task["spreadsheet_url"]
    days_range = task["days_range"] or 90
    
    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days_range)).strftime("%Y-%m-%d")
    
    try:
        insight_res = fetch_keywords_insight(keywords, start_date, end_date)
        matrix = build_sheet_matrix(insight_res["keywords"], insight_res["dates"], insight_res["data"])
        
        feishu = FeishuClient()
        sheets = feishu.get_sheets(ss_token)
        first_sheet_id = sheets[0]["sheet_id"] if sheets else "0"
        
        write_matrix_to_sheet(feishu, ss_token, first_sheet_id, matrix)
        merge_date_headers(feishu, ss_token, first_sheet_id, len(insight_res["dates"]))
            
        finished_at = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute("""
                UPDATE keyword_tasks SET last_run_at = ?, last_status = 'success', last_error = NULL, updated_at = ? WHERE id = ?
            """, (finished_at, finished_at, task_id))
            conn.execute("""
                INSERT INTO keyword_runs (
                    task_id, task_name, trigger_type, started_at, finished_at,
                    status, keywords_count, days_count, spreadsheet_url, message
                ) VALUES (?, ?, ?, ?, ?, 'success', ?, ?, ?, ?)
            """, (
                task_id, task_name, trigger_type, started_at, finished_at,
                len(insight_res["keywords"]), len(insight_res["dates"]), ss_url, "同步更新成功"
            ))
            conn.commit()
            
        return {"success": True, "message": "同步成功", "url": ss_url}
    except Exception as e:
        finished_at = datetime.now().isoformat()
        err_msg = str(e)
        with get_db() as conn:
            conn.execute("""
                UPDATE keyword_tasks SET last_run_at = ?, last_status = 'failed', last_error = ?, updated_at = ? WHERE id = ?
            """, (finished_at, err_msg, finished_at, task_id))
            conn.execute("""
                INSERT INTO keyword_runs (
                    task_id, task_name, trigger_type, started_at, finished_at,
                    status, keywords_count, days_count, spreadsheet_url, message, error_detail
                ) VALUES (?, ?, ?, ?, ?, 'failed', ?, ?, ?, '同步失败', ?)
            """, (
                task_id, task_name, trigger_type, started_at, finished_at,
                len(keywords), 0, ss_url, err_msg
            ))
            conn.commit()
        raise

def append_keywords_to_task(task_id: int, new_keywords: List[str], sync_now: bool = True) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM keyword_tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        
    if not task:
        raise ValueError(f"Task #{task_id} not found")
        
    curr_kws = json.loads(task["keywords_json"] or "[]")
    clean_new = []
    seen = set(curr_kws)
    for k in new_keywords:
        w = k.strip()
        if w and w not in seen:
            seen.add(w)
            clean_new.append(w)
            
    if not clean_new:
        return {
            "success": True,
            "added_count": 0,
            "added": [],
            "total_count": len(curr_kws),
            "message": "输入的关键词已全部存在于该任务中",
            "spreadsheet_url": task["spreadsheet_url"]
        }
        
    updated_kws = curr_kws + clean_new
    now = datetime.now().isoformat()
    
    with get_db() as conn:
        conn.execute(
            "UPDATE keyword_tasks SET keywords_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(updated_kws, ensure_ascii=False), now, task_id)
        )
        conn.commit()
        
    if sync_now:
        run_keyword_task(task_id, trigger_type="append_words")
        
    return {
        "success": True,
        "added_count": len(clean_new),
        "added": clean_new,
        "total_count": len(updated_kws),
        "spreadsheet_url": task["spreadsheet_url"]
    }

