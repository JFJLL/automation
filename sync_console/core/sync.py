import json
import time
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

from app.config import BACKUPS_DIR
from app.db import get_db
from core.database import acquire_task_lease, release_task_lease
from core.business_time import latest_sync_cutoff_date, now_business_tz
from core.models import ProviderFetchResult, ProviderFetchStatus
from core.errors import (
    TaskNotFoundError,
    TaskAlreadyRunningError,
    ProviderError,
    ProviderAuthError,
    ProviderUpstreamError,
    FeishuWriteError
)
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
            found = False
            for k, v in item.items():
                if str(k).strip().lower() == str(h).strip().lower():
                    row.append(format_cell_value(v))
                    found = True
                    break
            if not found:
                row.append("")
    return row

def get_item_natural_key(platform: str, item: Dict[str, Any], entity_id: str, dimension: str) -> Tuple:
    d_val = str(item.get("日期") or item.get("时间") or "").strip()[:10]
    if platform == "jzt":
        task_id_val = str(item.get("任务ID") or entity_id or "").strip()
        channel = str(item.get("平台") or item.get("渠道") or "").strip()
        return (task_id_val, d_val, channel)
    elif platform == "taobao":
        content_id_val = str(item.get("内容ID") or item.get("订单商品ID") or entity_id or "").strip()
        flow_type = str(item.get("流量类型") or "").strip()
        return (content_id_val, d_val, dimension, flow_type)
    elif platform == "juguang":
        creativity_id = str(item.get("创意ID") or item.get("单元ID") or entity_id or "").strip()
        placement = str(item.get("投放位置") or "").strip()
        target = str(item.get("精准定向") or "").strip()
        kw = str(item.get("关键词") or "").strip()
        return (creativity_id, d_val, placement, target, kw)
    return (str(entity_id).strip(), d_val)

def preview_fetch(
    platform: str,
    entity_ids: List[str],
    dimension: str,
    start_date: str,
    end_date: str,
    headers: List[str],
    id_col: str,
    date_col: str,
    sub_account_id: Optional[str] = None
) -> Dict[str, Any]:
    all_raw_rows = []
    errors = []
    sample_ids = entity_ids[:5] if entity_ids else []
    
    for eid in sample_ids:
        try:
            if platform == "jzt":
                res = fetch_jzt_data(eid, start_date, end_date)
            elif platform == "taobao":
                res = fetch_taobao_data(eid, dimension, start_date, end_date)
            elif platform == "juguang":
                res = fetch_juguang_data(eid, dimension, start_date, end_date, sub_account_id=sub_account_id)
            else:
                raise ValueError(f"未知平台: {platform}")
            rows = res.rows if hasattr(res, "rows") else res
            all_raw_rows.extend(rows[:50])
        except Exception as e:
            errors.append(f"实体 {eid}: {str(e)}")
            
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
    """
    执行主数据同步：
    两阶段高可靠事务保证：
    Phase 1: 所有 Sheet 数据全量并发/串行抓取与校验，全部通过才进入 Phase 2；
             若任何 Sheet 出现鉴权失效或上游接口异常，整次中断抛错，绝不写入飞书！
    Phase 2: 严格区分 overwrite 与 append 语义：
             - overwrite: 写前备份，安全清表，全量写入，写后表头与行数回读校验；校验失败自动快照回滚
             - append: 按自然复合键执行精确 upsert，已存在的记录原地更新，新记录追加表尾，绝不重复生成冗余行！
    """
    started_at = datetime.now().isoformat()
    t0 = time.time()
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            raise TaskNotFoundError(f"同步任务 #{task_id} 不存在")
            
        # 并发排他锁
        lease_key = f"sync_task_{task_id}"
        if not acquire_task_lease(conn, lease_key, owner=f"sync_{trigger_type}", lease_seconds=900):
            raise TaskAlreadyRunningError(f"任务 #{task_id} 正在执行中，请勿重复运行")
            
        cursor.execute("SELECT * FROM task_sheets WHERE task_id = ?", (task_id,))
        sheets = cursor.fetchall()
        
        # 记录 running 状态
        cursor.execute("""
            INSERT INTO runs (
                task_id, trigger_type, started_at, status,
                rows_fetched, rows_appended, rows_updated, message
            ) VALUES (?, ?, ?, 'running', 0, 0, 0, '同步执行中...')
        """, (task_id, trigger_type, started_at))
        run_id = cursor.lastrowid
        conn.commit()

    feishu = FeishuClient()
    notifier = Notifier(feishu)
    total_fetched = 0
    total_appended = 0
    total_updated = 0
    errors = []
    rollback_status: Optional[str] = None
    
    cutoff_date = latest_sync_cutoff_date(task["platform"])
    
    # ---------------- Phase 1: 数据抓取与预校验 ----------------
    prepared_sheets_data = []
    try:
        for s in sheets:
            sheet_title = s["sheet_title"]
            worksheet_id = s["worksheet_id"]
            headers = json.loads(s["header_json"])
            entity_ids = json.loads(s["entity_ids_json"])
            id_col = s["id_column"]
            date_col = s["date_column"]
            dimension = s["dimension"] or ""
            
            # 读取现有表数据
            existing_values = feishu.read_values(task["spreadsheet_token"], worksheet_id, "A:AZ") or []
            
            # 计算拉取日期范围
            dates_in_sheet = []
            if len(existing_values) > 1:
                date_idx = headers.index(date_col) if (headers and date_col in headers) else 0
                for r in existing_values[1:]:
                    if len(r) > date_idx and r[date_idx]:
                        d_str = str(r[date_idx]).strip()[:10].replace("/", "-")
                        if len(d_str) == 10:
                            dates_in_sheet.append(d_str)
                            
            if task["update_mode"] == "overwrite":
                start_date = min(dates_in_sheet) if dates_in_sheet else (date.today() - timedelta(days=30)).isoformat()
            else:
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
            
            # 抓取各实体数据 (失败直接抛异常，绝不静默当作空数据)
            fetched_items = []
            sub_acc_id = task["sub_account_id"] if "sub_account_id" in task.keys() else None
            for eid in entity_ids:
                if task["platform"] == "jzt":
                    res = fetch_jzt_data(eid, start_date, cutoff_date)
                elif task["platform"] == "taobao":
                    res = fetch_taobao_data(eid, dimension, start_date, cutoff_date)
                elif task["platform"] == "juguang":
                    res = fetch_juguang_data(eid, dimension, start_date, cutoff_date, sub_account_id=sub_acc_id)
                else:
                    raise ValueError(f"未知平台类型: {task['platform']}")
                    
                rows = res.rows if hasattr(res, "rows") else res
                fetched_items.extend(rows)
                
            prepared_sheets_data.append({
                "sheet": s,
                "existing_values": existing_values,
                "fetched_items": fetched_items,
                "headers": headers,
                "id_col": id_col,
                "date_col": date_col,
                "dimension": dimension
            })
            total_fetched += len(fetched_items)
            
    except Exception as fetch_err:
        finished_at = datetime.now().isoformat()
        duration_ms = int((time.time() - t0) * 1000)
        err_msg = f"Phase 1 数据抓取阶段失败: {str(fetch_err)}"
        with get_db() as conn:
            conn.execute("""
                UPDATE tasks SET last_run_at = ?, last_status = 'failed', last_error = ?, updated_at = ? WHERE id = ?
            """, (finished_at, err_msg, finished_at, task_id))
            conn.execute("""
                UPDATE runs SET
                    finished_at = ?, status = 'failed', duration_ms = ?,
                    message = '数据抓取校验未通过，中止写表', error_detail = ?
                WHERE id = ?
            """, (finished_at, duration_ms, err_msg, run_id))
            conn.commit()
            release_task_lease(conn, f"sync_task_{task_id}")
        notifier.notify_failure(task["name"], task["platform"], err_msg)
        raise fetch_err

    # ---------------- Phase 2: 数据写入与幂等更新 ----------------
    sheets_written = []
    try:
        for prep in prepared_sheets_data:
            s = prep["sheet"]
            sheet_title = s["sheet_title"]
            worksheet_id = s["worksheet_id"]
            existing_values = prep["existing_values"]
            fetched_items = prep["fetched_items"]
            headers = prep["headers"]
            id_col = prep["id_col"]
            date_col = prep["date_col"]
            dimension = prep["dimension"]
            
            # 1. 写前整表备份
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
            sheets_written.append((worksheet_id, existing_values))
            
            new_rows = [map_item_to_row(item, headers, id_col, date_col) for item in fetched_items]
            
            if task["update_mode"] == "overwrite":
                # 全量覆盖写
                if not new_rows and not existing_values:
                    # 无论如何不破坏空表
                    pass
                else:
                    feishu.clear_rows_below(task["spreadsheet_token"], worksheet_id, keep_header_row=1, col_count=len(headers) or 30)
                    if new_rows:
                        feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=2, rows=new_rows)
                    total_updated += len(new_rows)
            else:
                # 增量追加/Upsert：杜绝重复追加！
                # 使用统一 get_item_natural_key 构建已有行与新抓取行的高可靠复合自然键
                existing_key_map = {}
                primary_entity_id = entity_ids[0] if entity_ids else ""
                if len(existing_values) > 1:
                    for idx, r in enumerate(existing_values[1:], start=2):
                        row_dict = dict(zip(headers, r))
                        key = get_item_natural_key(task["platform"], row_dict, primary_entity_id, dimension)
                        existing_key_map[key] = idx

                to_append = []
                to_update_chunks = {} # row_idx -> mapped_row
                for item in fetched_items:
                    mapped_row = map_item_to_row(item, headers, id_col, date_col)
                    key = get_item_natural_key(task["platform"], item, primary_entity_id, dimension)
                    if key in existing_key_map:
                        target_row_idx = existing_key_map[key]
                        to_update_chunks[target_row_idx] = mapped_row
                    else:
                        to_append.append(mapped_row)
                        
                # 执行原地更新
                for r_idx, u_row in to_update_chunks.items():
                    feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=r_idx, rows=[u_row])
                    total_updated += 1
                    
                # 执行追加新行
                if to_append:
                    last_row = feishu.find_last_row_index(task["spreadsheet_token"], worksheet_id)
                    start_row = max(last_row + 1, 2)
                    feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=start_row, rows=to_append)
                    total_appended += len(to_append)
                    
            # 6. 写后回读校验 (确保表头完整，且非全空)
            verify_rows = feishu.read_values(task["spreadsheet_token"], worksheet_id, "A:AZ")
            if len(verify_rows) < 1:
                raise FeishuWriteError(f"工作表【{sheet_title}】写后回读校验失败：表头或数据丢失")
                
    except Exception as write_err:
        errors.append(f"写入阶段异常: {str(write_err)}")
        # 尝试快照回滚
        rollback_success = True
        for ws_id, old_backup in sheets_written:
            try:
                feishu.restore_sheet_values(task["spreadsheet_token"], ws_id, old_backup)
            except Exception as rb_e:
                rollback_success = False
                errors.append(f"Sheet {ws_id} 回滚失败: {rb_e}")
        rollback_status = "rollback_success" if rollback_success else "rollback_failed"
        
    finished_at = datetime.now().isoformat()
    duration_ms = int((time.time() - t0) * 1000)
    status = "failed" if errors else "success"
    err_detail = "; ".join(errors) if errors else None
    
    with get_db() as conn:
        conn.execute(
            """
            UPDATE runs SET
                finished_at = ?, status = ?, rows_fetched = ?, rows_appended = ?,
                rows_updated = ?, duration_ms = ?, rollback_status = ?,
                message = ?, error_detail = ?
            WHERE id = ?
            """,
            (
                finished_at, status, total_fetched, total_appended, total_updated,
                duration_ms, rollback_status,
                f"抓取{total_fetched}行，追加{total_appended}行，更新{total_updated}行",
                err_detail, run_id
            )
        )
        conn.execute(
            """
            UPDATE tasks SET last_run_at = ?, last_status = ?, last_error = ?, updated_at = ? WHERE id = ?
            """,
            (finished_at, status, err_detail, finished_at, task_id)
        )
        conn.commit()
        release_task_lease(conn, f"sync_task_{task_id}")
        
    if status == "failed":
        notifier.notify_failure(task["name"], task["platform"], err_detail or "未知错误")
        
    return {
        "status": status,
        "rows_fetched": total_fetched,
        "rows_appended": total_appended,
        "rows_updated": total_updated,
        "rollback_status": rollback_status,
        "duration_ms": duration_ms,
        "errors": errors
    }

