import json
import time
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

from app.config import BACKUPS_DIR
from app.db import get_db
from feishu.client import FeishuClient
from feishu.notify import Notifier
from platforms.jzt import fetch_jzt_data
from platforms.taobao import fetch_taobao_data
from platforms.juguang import fetch_juguang_data

def format_cell_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return str(val)
    return str(val).strip()

def map_item_to_row(item: Dict[str, Any], headers: List[str], id_col: str, date_col: str) -> List[Any]:
    row = []
    for h in headers:
        if h in item:
            row.append(format_cell_value(item[h]))
        else:
            # 兼容别名或映射
            found = False
            for k, v in item.items():
                if str(k).strip().lower() == str(h).strip().lower():
                    row.append(format_cell_value(v))
                    found = True
                    break
            if not found:
                row.append("")
    return row

def preview_fetch(
    platform: str,
    entity_ids: List[str],
    dimension: str,
    start_date: str,
    end_date: str,
    headers: List[str],
    id_col: str,
    date_col: str
) -> Dict[str, Any]:
    all_raw_rows = []
    errors = []
    
    # 取样实体 ID（最多5个避免耗时过长）
    sample_ids = entity_ids[:5] if entity_ids else []
    
    for eid in sample_ids:
        try:
            if platform == "jzt":
                data = fetch_jzt_data(eid, start_date, end_date)
            elif platform == "taobao":
                data = fetch_taobao_data(eid, dimension, start_date, end_date)
            elif platform == "juguang":
                data = fetch_juguang_data(eid, dimension, start_date, end_date)
            else:
                raise ValueError(f"未知平台: {platform}")
            all_raw_rows.extend(data[:50])
        except Exception as e:
            errors.append(f"实体 {eid}: {str(e)}")
            
    # 转为对齐 headers 的二维列表
    preview_table_rows = []
    for item in all_raw_rows[:50]:
        row = map_item_to_row(item, headers, id_col, date_col)
        preview_table_rows.append(row)
        
    return {
        "headers": headers,
        "rows": preview_table_rows,
        "total_fetched": len(all_raw_rows),
        "sample_entities_checked": sample_ids,
        "errors": errors
    }

def clean_old_backups(task_id: int, worksheet_id: str, keep_limit: int = 30):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, backup_path FROM backups WHERE task_id = ? AND worksheet_id = ? ORDER BY created_at DESC",
            (task_id, worksheet_id)
        )
        rows = cursor.fetchall()
        if len(rows) > keep_limit:
            to_delete = rows[keep_limit:]
            for r in to_delete:
                p = Path(r["backup_path"])
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
                cursor.execute("DELETE FROM backups WHERE id = ?", (r["id"],))
            conn.commit()

def execute_task_sync(task_id: int, trigger_type: str = "scheduled") -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            raise ValueError(f"Task {task_id} not found")
        cursor.execute("SELECT * FROM task_sheets WHERE task_id = ?", (task_id,))
        sheets = cursor.fetchall()
        
    feishu = FeishuClient()
    notifier = Notifier(feishu)
    started_at = datetime.now().isoformat()
    total_fetched = 0
    total_appended = 0
    total_updated = 0
    errors = []
    
    cutoff_date = (date.today() - timedelta(days=1)).isoformat()
    
    for s in sheets:
        sheet_title = s["sheet_title"]
        worksheet_id = s["worksheet_id"]
        headers = json.loads(s["header_json"])
        entity_ids = json.loads(s["entity_ids_json"])
        id_col = s["id_column"]
        date_col = s["date_column"]
        dimension = s["dimension"] or ""
        
        try:
            # 1. 读回现有行
            existing_values = feishu.read_values(task["spreadsheet_token"], worksheet_id, "A:AZ")
            
            # 2. 写前备份整表
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = BACKUPS_DIR / f"{task_id}_{worksheet_id}_{stamp}.json"
            backup_file.write_text(json.dumps(existing_values, ensure_ascii=False, indent=2), encoding="utf-8")
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO backups (task_id, worksheet_id, backup_path, row_count, created_at) VALUES (?, ?, ?, ?, ?)",
                    (task_id, worksheet_id, str(backup_file), len(existing_values), datetime.now().isoformat())
                )
                conn.commit()
            clean_old_backups(task_id, worksheet_id, 30)
            
            # 3. 计算拉取日期范围
            dates_in_sheet = []
            if len(existing_values) > 1:
                # 寻找日期列索引
                date_idx = 0
                if headers and date_col in headers:
                    date_idx = headers.index(date_col)
                for r in existing_values[1:]:
                    if len(r) > date_idx and r[date_idx]:
                        d_str = str(r[date_idx]).strip()[:10].replace("/", "-")
                        if len(d_str) == 10:
                            dates_in_sheet.append(d_str)
            
            if task["update_mode"] == "overwrite":
                # 全量覆盖：从现有最早日期或30天前开始
                start_date = min(dates_in_sheet) if dates_in_sheet else (date.today() - timedelta(days=30)).isoformat()
            else:
                # 增量追加：表内最新日期往前回溯 calibration_days
                if dates_in_sheet:
                    latest = max(dates_in_sheet)
                    try:
                        latest_dt = datetime.strptime(latest, "%Y-%m-%d").date()
                        start_date = (latest_dt - timedelta(days=int(task["calibration_days"]))).isoformat()
                    except Exception:
                        start_date = (date.today() - timedelta(days=int(task["calibration_days"]))).isoformat()
                else:
                    start_date = (date.today() - timedelta(days=int(task["calibration_days"]))).isoformat()
                    
            start_date = min(start_date, cutoff_date)
            
            # 4. 调接口抓取数据
            fetched_items = []
            for eid in entity_ids:
                if task["platform"] == "jzt":
                    items = fetch_jzt_data(eid, start_date, cutoff_date)
                elif task["platform"] == "taobao":
                    items = fetch_taobao_data(eid, dimension, start_date, cutoff_date)
                elif task["platform"] == "juguang":
                    items = fetch_juguang_data(eid, dimension, start_date, cutoff_date)
                else:
                    items = []
                fetched_items.extend(items)
            
            total_fetched += len(fetched_items)
            
            # 5. 转为二维行并写入
            new_rows = [map_item_to_row(item, headers, id_col, date_col) for item in fetched_items]
            
            if task["update_mode"] == "overwrite":
                # 全量覆盖写
                feishu.clear_rows_below(task["spreadsheet_token"], worksheet_id, keep_header_row=1)
                feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=2, rows=new_rows)
                total_updated += len(new_rows)
            else:
                # 增量追加：计算表尾有数据的最后一行
                last_row = feishu.find_last_row_index(task["spreadsheet_token"], worksheet_id)
                start_row = max(last_row + 1, 2)
                feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=start_row, rows=new_rows)
                total_appended += len(new_rows)
                
            # 6. 写后回读校验
            verify_rows = feishu.read_values(task["spreadsheet_token"], worksheet_id, "A:Z")
            if len(verify_rows) < 1:
                raise RuntimeError("写后回读校验失败：工作表为空")
                
        except Exception as e:
            err_msg = f"Sheet【{sheet_title}】同步失败: {str(e)}"
            errors.append(err_msg)
            
    finished_at = datetime.now().isoformat()
    status = "failed" if errors else "success"
    err_detail = "; ".join(errors) if errors else None
    
    # 记录运行日志
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO runs (
                task_id, trigger_type, started_at, finished_at, status,
                rows_fetched, rows_appended, rows_updated, message, error_detail
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id, trigger_type, started_at, finished_at, status,
                total_fetched, total_appended, total_updated,
                f"拉取{total_fetched}行，追加{total_appended}行，覆写{total_updated}行",
                err_detail
            )
        )
        conn.execute(
            """
            UPDATE tasks SET last_run_at = ?, last_status = ?, last_error = ?, updated_at = ? WHERE id = ?
            """,
            (finished_at, status, err_detail, finished_at, task_id)
        )
        conn.commit()
        
    if status == "failed":
        notifier.notify_failure(task["name"], task["platform"], err_detail or "未知错误")
        
    return {
        "status": status,
        "rows_fetched": total_fetched,
        "rows_appended": total_appended,
        "rows_updated": total_updated,
        "errors": errors
    }
