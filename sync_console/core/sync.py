import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import BACKUPS_DIR
from app.db import get_db
from core.business_time import latest_sync_cutoff_date, now_business_tz
from core.errors import (
    DataValidationError,
    FeishuWriteError,
    TaskNotFoundError,
)
from core.sync_runner import TaskRunGuard
from feishu.client import FeishuClient, column_letter
from feishu.notify import Notifier
from platforms.juguang import fetch_juguang_data
from platforms.jzt import fetch_jzt_data
from platforms.taobao import fetch_taobao_data

PROVIDER_CONCURRENCY = 3

def format_cell_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return str(val)
    return str(val).strip()

def sanitize_formula_injection(val: Any) -> Any:
    if isinstance(val, str) and val and val[0] in ('=', '+', '-', '@'):
        return f"'{val}"
    return val

def map_item_to_row(item: Dict[str, Any], headers: List[str], id_col: str, date_col: str) -> List[Any]:
    row = []
    for h in headers:
        if h in item:
            row.append(sanitize_formula_injection(format_cell_value(item[h])))
        else:
            found = False
            for k, v in item.items():
                if str(k).strip().lower() == str(h).strip().lower():
                    row.append(sanitize_formula_injection(format_cell_value(v)))
                    found = True
                    break
            if not found:
                row.append("")
    return row

def get_item_natural_key(platform: str, item: Dict[str, Any], entity_id: str, dimension: str) -> Optional[Tuple]:
    d_val = str(item.get("日期") or item.get("时间") or "").strip()[:10]
    if not d_val:
        return None

    if platform == "jzt":
        task_id_val = str(item.get("任务ID") or item.get("任务Id") or item.get("taskId") or "").strip()
        if not task_id_val:
            return None
        channel = str(item.get("平台") or item.get("渠道") or "").strip()
        return (task_id_val, d_val, channel)
    elif platform == "taobao":
        content_id_val = str(item.get("内容ID") or item.get("订单商品ID") or item.get("订单ID") or "").strip()
        if not content_id_val:
            return None
        flow_type = str(item.get("流量类型") or "").strip()
        return (content_id_val, d_val, dimension, flow_type)
    elif platform == "juguang":
        creativity_id = str(item.get("创意ID") or item.get("单元ID") or "").strip()
        if not creativity_id:
            return None
        placement = str(item.get("投放位置") or "").strip()
        target = str(item.get("精准定向") or "").strip()
        kw = str(item.get("关键词") or "").strip()
        return (creativity_id, d_val, placement, target, kw)

    id_val = str(entity_id).strip()
    if not id_val:
        return None
    return (id_val, d_val)

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
    conn = get_db()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            raise TaskNotFoundError(f"同步任务 #{task_id} 不存在")
        if task["status"] == "archived":
            raise TaskNotFoundError(f"任务 #{task_id} 已归档，无法同步")
        cursor.execute("SELECT * FROM task_sheets WHERE task_id = ?", (task_id,))
        sheets = cursor.fetchall()

    lease_key = f"sync_task_{task_id}"
    guard = TaskRunGuard(conn=conn, task_key=lease_key, task_id=task_id, module="sync", trigger_type=trigger_type, lease_seconds=900)

    with guard:
        feishu = FeishuClient()
        notifier = Notifier(feishu)
        total_fetched = 0
        total_appended = 0
        total_updated = 0
        warnings = []
        errors = []
        rollback_status: Optional[str] = None
        cutoff_date = latest_sync_cutoff_date(task["platform"])

        # ---------------- Phase 1: 有界并发抓取与预校验 ----------------
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

                # 动态根据表头长度读取
                col_width = len(headers) or 30
                end_col = column_letter(col_width)
                existing_values = feishu.read_values(task["spreadsheet_token"], worksheet_id, f"A1:{end_col}5000") or []

                dates_in_sheet = []
                if len(existing_values) > 1:
                    date_idx = headers.index(date_col) if (headers and date_col in headers) else 0
                    for r in existing_values[1:]:
                        if len(r) > date_idx and r[date_idx]:
                            d_str = str(r[date_idx]).strip()[:10].replace("/", "-")
                            if len(d_str) == 10:
                                dates_in_sheet.append(d_str)

                today_business = now_business_tz().date()
                if task["update_mode"] == "overwrite":
                    max_backfill = int(task["max_backfill_days"] or 90) if "max_backfill_days" in task.keys() else 90
                    earliest_date = (today_business - timedelta(days=max_backfill)).isoformat()
                    start_date = max(min(dates_in_sheet), earliest_date) if dates_in_sheet else earliest_date
                else:
                    calibration = int(task["calibration_days"]) if task["calibration_days"] else 2
                    if dates_in_sheet:
                        latest = max(dates_in_sheet)
                        try:
                            from datetime import datetime as dt
                            latest_dt = dt.strptime(latest, "%Y-%m-%d").date()
                            start_date = (latest_dt - timedelta(days=calibration)).isoformat()
                        except Exception:
                            start_date = (today_business - timedelta(days=calibration)).isoformat()
                    else:
                        start_date = (today_business - timedelta(days=calibration)).isoformat()

                start_date = min(start_date, cutoff_date)

                # 有界并发抓取实体数据 (PROVIDER_CONCURRENCY = 3)
                fetched_items = []
                sub_acc_id = task["sub_account_id"] if "sub_account_id" in task.keys() else None

                def fetch_entity(eid: str):
                    if task["platform"] == "jzt":
                        return fetch_jzt_data(eid, start_date, cutoff_date)
                    elif task["platform"] == "taobao":
                        return fetch_taobao_data(eid, dimension, start_date, cutoff_date)
                    elif task["platform"] == "juguang":
                        return fetch_juguang_data(eid, dimension, start_date, cutoff_date, sub_account_id=sub_acc_id)
                    else:
                        raise ValueError(f"未知平台类型: {task['platform']}")

                with ThreadPoolExecutor(max_workers=PROVIDER_CONCURRENCY) as executor:
                    future_to_eid = {executor.submit(fetch_entity, eid): eid for eid in entity_ids}
                    for fut in as_completed(future_to_eid):
                        res = fut.result()
                        rows = res.rows if hasattr(res, "rows") else res
                        fetched_items.extend(rows)

                prepared_sheets_data.append({
                    "sheet": s,
                    "existing_values": existing_values,
                    "fetched_items": fetched_items,
                    "headers": headers,
                    "id_col": id_col,
                    "date_col": date_col,
                    "dimension": dimension,
                    "col_width": col_width
                })
                total_fetched += len(fetched_items)

        except Exception as fetch_err:
            err_msg = f"Phase 1 数据抓取阶段失败: {str(fetch_err)}"
            guard.finish_run(status="failed", message="数据抓取校验未通过，中止写表", error_detail=err_msg, provider_status="error")
            notifier.notify_failure(task["name"], task["platform"], err_msg)
            raise fetch_err

        # ---------------- Phase 2: 数据写入与幂等更新 ----------------
        sheets_written = []
        try:
            for prep in prepared_sheets_data:
                # 续租
                guard.renew()

                s = prep["sheet"]
                sheet_title = s["sheet_title"]
                worksheet_id = s["worksheet_id"]
                existing_values = prep["existing_values"]
                fetched_items = prep["fetched_items"]
                headers = prep["headers"]
                id_col = prep["id_col"]
                date_col = prep["date_col"]
                dimension = prep["dimension"]
                col_width = prep["col_width"]

                # 1. 写前整表备份
                stamp = now_business_tz().strftime("%Y%m%d_%H%M%S")
                backup_file = BACKUPS_DIR / f"{task_id}_{worksheet_id}_{stamp}.json"
                backup_file.write_text(json.dumps(existing_values, ensure_ascii=False, indent=2), encoding="utf-8")
                with get_db() as db_conn:
                    db_conn.execute(
                        "INSERT INTO backups (task_id, worksheet_id, backup_path, row_count, created_at) VALUES (?, ?, ?, ?, ?)",
                        (task_id, worksheet_id, str(backup_file), len(existing_values), now_business_tz().isoformat())
                    )
                    db_conn.commit()
                clean_old_backups(task_id, worksheet_id, 30)
                sheets_written.append((worksheet_id, existing_values, col_width, headers))

                new_rows = [map_item_to_row(item, headers, id_col, date_col) for item in fetched_items]

                if task["update_mode"] == "overwrite":
                    # overwrite 空结果安全保护
                    if not new_rows:
                        allow_empty = bool(task["allow_empty_overwrite"]) if "allow_empty_overwrite" in task.keys() else False
                        if not allow_empty:
                            # 默认不清表，标记 empty_upstream 并跳过
                            warnings.append(f"Sheet [{sheet_title}] 上游返回空结果且未配置 allow_empty_overwrite，保持原表不变")
                            continue
                        else:
                            feishu.clear_rows_below(task["spreadsheet_token"], worksheet_id, keep_header_row=1, col_count=col_width)
                    else:
                        feishu.clear_rows_below(task["spreadsheet_token"], worksheet_id, keep_header_row=1, col_count=col_width)
                        feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=2, rows=new_rows)
                        total_updated += len(new_rows)
                else:
                    # append 模式：构建复合自然键进行精准 upsert
                    existing_key_map = {}
                    if len(existing_values) > 1:
                        for idx, r in enumerate(existing_values[1:], start=2):
                            row_dict = dict(zip(headers, r))
                            key = get_item_natural_key(task["platform"], row_dict, "", dimension)
                            if key:
                                existing_key_map[key] = idx

                    to_append = []
                    to_update_chunks = {}
                    seen_keys_this_batch = set()

                    for item in fetched_items:
                        mapped_row = map_item_to_row(item, headers, id_col, date_col)
                        key = get_item_natural_key(task["platform"], item, "", dimension)
                        if not key:
                            warnings.append(f"行缺少关键自然键字段，跳过: {mapped_row[:3]}")
                            continue

                        if key in seen_keys_this_batch:
                            # 发现重复自然键，暂停任务并报错
                            with get_db() as db_conn:
                                db_conn.execute("UPDATE tasks SET status = 'paused' WHERE id = ?", (task_id,))
                                db_conn.commit()
                            raise DataValidationError(f"批次内发现重复自然键 {key}，为防止数据覆盖已自动暂停任务")
                        seen_keys_this_batch.add(key)

                        if key in existing_key_map:
                            target_row_idx = existing_key_map[key]
                            to_update_chunks[target_row_idx] = mapped_row
                        else:
                            to_append.append(mapped_row)

                    # 原地更新
                    for r_idx, u_row in to_update_chunks.items():
                        feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=r_idx, rows=[u_row])
                        total_updated += 1

                    # 追加新行
                    if to_append:
                        try:
                            last_row = feishu.find_last_row_index(task["spreadsheet_token"], worksheet_id, col_count=col_width)
                        except TypeError:
                            last_row = feishu.find_last_row_index(task["spreadsheet_token"], worksheet_id)
                        start_row = max(last_row + 1, 2)
                        feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=start_row, rows=to_append)
                        total_appended += len(to_append)

                # 写后回读严密校验：表头完全一致、数据行数不丢失
                verify_rows = feishu.read_values(task["spreadsheet_token"], worksheet_id, f"A1:{column_letter(col_width)}5000")
                if not verify_rows or len(verify_rows) < 1:
                    raise FeishuWriteError(f"工作表【{sheet_title}】写后校验失败：表格为空或无表头")

                # 校验表头
                returned_headers = [str(c).strip() for c in verify_rows[0][:len(headers)]]
                expected_headers = [str(c).strip() for c in headers]
                if returned_headers != expected_headers:
                    raise FeishuWriteError(f"工作表【{sheet_title}】写后表头不一致: 预期 {expected_headers[:5]}，实际 {returned_headers[:5]}")

        except Exception as write_err:
            errors.append(f"写入阶段异常: {str(write_err)}")
            rollback_success = True
            for ws_id, old_backup, col_w, hdrs in sheets_written:
                try:
                    rb_ok = feishu.restore_sheet_values(task["spreadsheet_token"], ws_id, old_backup)
                    if not rb_ok:
                        rollback_success = False
                except Exception as rb_e:
                    rollback_success = False
                    errors.append(f"Sheet {ws_id} 回滚异常: {rb_e}")

            rollback_status = "rollback_success" if rollback_success else "rollback_failed"
            if not rollback_success:
                with get_db() as db_conn:
                    db_conn.execute("UPDATE tasks SET status = 'needs_attention' WHERE id = ?", (task_id,))
                    db_conn.commit()
                from core.scheduler_manager import SchedulerManager
                SchedulerManager.get_instance().remove_sync_task(task_id)

        status = "failed" if errors else ("empty_upstream" if (not total_fetched and task["update_mode"] == "overwrite") else "success")
        err_detail = "; ".join(errors) if errors else ("; ".join(warnings) if warnings else None)
        msg = f"抓取{total_fetched}行，追加{total_appended}行，更新{total_updated}行"
        if warnings:
            msg += f" (包含警告: {len(warnings)}条)"

        guard.finish_run(
            status=status,
            message=msg,
            error_detail=err_detail,
            rows_fetched=total_fetched,
            rows_appended=total_appended,
            rows_updated=total_updated,
            provider_status="ok" if not errors else "error",
            rollback_status=rollback_status
        )

        if status == "failed":
            notifier.notify_failure(task["name"], task["platform"], err_detail or "未知错误")

        return {
            "status": status,
            "rows_fetched": total_fetched,
            "rows_appended": total_appended,
            "rows_updated": total_updated,
            "rollback_status": rollback_status,
            "errors": errors
        }
