import json
import re
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
from platforms.registry import detect_best_platform
from feishu.client import column_letter

EXCEL_DATE_EPOCH = date(1899, 12, 30)


def _excel_serial_to_date(value: Any) -> Optional[date]:
    try:
        serial = int(float(value))
    except (TypeError, ValueError):
        return None
    # Modern Feishu date serials sit in this range; this avoids mistaking
    # small numeric IDs or years for dates.
    if 20000 <= serial <= 80000:
        try:
            return EXCEL_DATE_EPOCH + timedelta(days=serial)
        except OverflowError:
            return None
    return None


def date_to_excel_serial(value: Any) -> Optional[int]:
    """Convert supported date text to a real Excel/Feishu date serial."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        # Already a serial; keep it stable across syncs.
        parsed = _excel_serial_to_date(value)
        return int(float(value)) if parsed else None
    text = str(value).strip()
    if not text:
        return None
    digits = "".join(c for c in text.replace("/", "-").split(" ")[0] if c.isdigit())
    if len(digits) != 8:
        return None
    try:
        parsed_date = datetime.strptime(digits, "%Y%m%d").date()
    except ValueError:
        return None
    return (parsed_date - EXCEL_DATE_EPOCH).days

def sort_sheet_data_rows(
    rows: List[List[Any]],
    headers: List[str],
    id_col: str,
    date_col: str,
    entity_ids: List[str]
) -> List[List[Any]]:
    if not rows or not headers:
        return rows
    id_idx = headers.index(id_col) if (headers and id_col in headers) else 1
    date_idx = headers.index(date_col) if (headers and date_col in headers) else 0
    clean_entity_ids = [str(eid).strip()[:-2] if str(eid).strip().endswith(".0") else str(eid).strip() for eid in (entity_ids or [])]

    def row_sort_key(r):
        row_id = str(r[id_idx] if len(r) > id_idx else "").strip()
        if row_id.endswith(".0"):
            row_id = row_id[:-2]
        task_order = clean_entity_ids.index(row_id) if row_id in clean_entity_ids else 999999
        raw_d = str(r[date_idx] if len(r) > date_idx else "").strip()
        d_compact = normalize_date_compact(raw_d)[:8]
        channel = ""
        for col_name in ["平台", "渠道", "流量类型"]:
            if col_name in headers:
                c_idx = headers.index(col_name)
                channel = str(r[c_idx] if len(r) > c_idx else "")
                break
        return (task_order, row_id, d_compact, channel)

    return sorted(rows, key=row_sort_key)

def format_cell_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return str(val)
    return str(val).strip()

def normalize_date_compact(val: Any) -> str:
    serial_date = _excel_serial_to_date(val)
    if serial_date:
        return serial_date.strftime("%Y%m%d")
    s = str(val).strip().replace('/', '-').split(' ')[0]
    digits = ''.join(c for c in s if c.isdigit())
    if len(digits) == 8:
        return digits
    return s

def normalize_date_str(val: Any) -> str:
    s = str(val).strip().replace('/', '-').split(' ')[0]
    digits = ''.join(c for c in s if c.isdigit())
    if len(digits) == 8:
        return digits
    return s

def map_item_to_row(
    item: Dict[str, Any],
    headers: List[str],
    id_col: str,
    date_col: str,
    date_as_serial: bool = True,
) -> List[Any]:
    row = []
    for h in headers:
        if h in item:
            val = item[h]
            if h == date_col:
                serial = date_to_excel_serial(val) if date_as_serial else None
                row.append(serial if serial is not None else normalize_date_compact(val))
            else:
                row.append(format_cell_value(val))
        else:
            found = False
            for k, v in item.items():
                if str(k).strip().lower() == str(h).strip().lower():
                    val = v
                    if h == date_col:
                        serial = date_to_excel_serial(val) if date_as_serial else None
                        row.append(serial if serial is not None else normalize_date_compact(val))
                    else:
                        row.append(format_cell_value(val))
                    found = True
                    break
            if not found:
                row.append("")
    return row


def apply_date_column_format(
    feishu: FeishuClient,
    spreadsheet_token: str,
    worksheet_id: str,
    headers: List[str],
    date_col: str,
    last_row: int,
    formatter: str = "yyyy/MM/dd",
) -> None:
    """Format the date column so numeric serials render as yyyy/MM/dd."""
    if not headers or date_col not in headers or last_row < 2:
        return
    col = column_letter(headers.index(date_col) + 1)
    try:
        feishu.set_number_format(
            spreadsheet_token,
            worksheet_id,
            f"{col}2:{col}{last_row}",
            formatter,
        )
    except Exception as exc:
        # Formatting is cosmetic; never fail a data sync because of it.
        print(f"[DateFormat] {worksheet_id} {col}: {exc}")


def normalize_row_date_value(row: List[Any], date_idx: int) -> List[Any]:
    """Convert an 8-digit date text cell in a row to a real date serial."""
    if date_idx >= len(row):
        return row
    current = row[date_idx]
    if isinstance(current, str) and current.strip().startswith("="):
        return row
    serial = date_to_excel_serial(current)
    if serial is None:
        compact = normalize_date_compact(current)
        if len(compact) != 8 or not compact.isdigit():
            return row
        serial = date_to_excel_serial(compact)
    if serial is not None:
        row[date_idx] = serial
    return row


def is_entity_assigned_to_sheet(
    entity_id: str,
    sheet_entity_ids: List[str],
    row_task_id: Any,
) -> bool:
    """Prevent one child sheet from ingesting another sheet's task rows."""
    normalized = [str(eid).strip() for eid in (sheet_entity_ids or []) if str(eid).strip()]
    if not normalized:
        return True
    row_id = str(row_task_id or "").strip()
    if row_id.endswith(".0"):
        row_id = row_id[:-2]
    return row_id in normalized


def narrow_entity_ids_from_existing_rows(
    entity_ids: List[str],
    existing_values: List[List[Any]],
    headers: List[str],
    id_col: str,
) -> List[str]:
    """Infer a sheet's single owning task when legacy config lists several tasks."""
    configured = [
        str(eid).strip()[:-2]
        if str(eid).strip().endswith(".0")
        else str(eid).strip()
        for eid in (entity_ids or [])
        if str(eid).strip()
    ]
    if len(configured) <= 1 or id_col not in headers:
        return configured
    id_idx = headers.index(id_col)
    observed = set()
    for row in existing_values[1:]:
        if id_idx >= len(row):
            continue
        row_id = str(row[id_idx] or "").strip()
        if row_id.endswith(".0"):
            row_id = row_id[:-2]
        if row_id in configured:
            observed.add(row_id)
    return [next(iter(observed))] if len(observed) == 1 else configured

def get_item_natural_key(platform: str, item: Dict[str, Any], entity_id: str, dimension: str) -> Tuple:
    raw_date = item.get("日期") or item.get("时间") or ""
    d_val = normalize_date_compact(raw_date)[:8]
    if platform == "jzt":
        task_id_val = str(item.get("任务ID") or entity_id or "").strip()
        if task_id_val.endswith(".0"):
            task_id_val = task_id_val[:-2]
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
        rows = []
        try:
            if platform == "jzt":
                res = fetch_jzt_data(eid, start_date, end_date, sub_account_id=sub_account_id)
            elif platform == "taobao":
                res = fetch_taobao_data(eid, dimension, start_date, end_date)
            elif platform == "juguang":
                res = fetch_juguang_data(eid, dimension, start_date, end_date, sub_account_id=sub_account_id)
            else:
                raise ValueError(f"未知平台: {platform}")
            rows = res.rows if hasattr(res, "rows") else res

            # 第四步用于核对真实数据：若按起始日期抓取为空（例如当日或离线 T+1 报表未出），
            # 自动向前回退取最近 3 天有数据的历史区间，供用户直观核验字段映射与具体数据
            if not rows:
                try:
                    d_obj = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
                    fb_end = (d_obj - timedelta(days=1)).isoformat()
                    fb_start = (d_obj - timedelta(days=3)).isoformat()
                    if platform == "jzt":
                        res_fb = fetch_jzt_data(eid, fb_start, fb_end)
                    elif platform == "taobao":
                        res_fb = fetch_taobao_data(eid, dimension, fb_start, fb_end)
                    elif platform == "juguang":
                        res_fb = fetch_juguang_data(eid, dimension, fb_start, fb_end, sub_account_id=sub_account_id)
                    rows_fb = res_fb.rows if hasattr(res_fb, "rows") else res_fb
                    if rows_fb:
                        rows = rows_fb
                except Exception:
                    pass

            all_raw_rows.extend(rows[:50])
        except Exception as e:
            errors.append(f"实体 {eid}: {str(e)}")
            
    merged_headers = list(headers)
    preview_table_rows = []
    for item in all_raw_rows[:50]:
        row = map_item_to_row(item, merged_headers, id_col, date_col, date_as_serial=False)
        preview_table_rows.append(row)

    # 用表头特征反推真实来源平台，前端据此提示"平台选错"并支持一键切换
    detected_platform = platform
    try:
        detected_platform, _ = detect_best_platform(merged_headers)
    except Exception:
        pass

    return {
        "headers": merged_headers,
        "rows": preview_table_rows,
        "total_fetched": len(all_raw_rows),
        "sample_entities_checked": sample_ids,
        "errors": errors,
        "detected_platform": detected_platform,
        "platform_mismatch": detected_platform != platform
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

def _is_empty_cell(val: Any) -> bool:
    return val is None or (isinstance(val, str) and not val.strip())


def _cell_equivalent(old: Any, new: Any) -> bool:
    """数值容差比较：避免 2 与 "2"、0 与 "0.0" 被误判为变更而反复回写。"""
    if _is_empty_cell(old) and _is_empty_cell(new):
        return True
    # 飞书富文本/超链接单元格读回是对象数组，写成纯文本会丢失可点击链接，视为等价跳过
    if isinstance(old, (list, dict)):
        return True
    if str(old).strip() == str(new).strip():
        return True
    try:
        return float(str(old).strip()) == float(str(new).strip())
    except (TypeError, ValueError):
        return False


_FORMULA_REF_RE = re.compile(r"(?<![A-Za-z0-9_$])(\$?)([A-Z]{1,3})(\$?)(\d+)(?![0-9])")


def shift_formula_row(formula: str, from_row: int, to_row: int) -> str:
    """把公式中的相对行引用从 from_row 平移到 to_row，绝对引用（$2）保持不变。"""
    if not isinstance(formula, str) or not formula.startswith("=") or from_row == to_row:
        return formula

    def repl(match: re.Match) -> str:
        col_abs, col, row_abs, row_no = match.groups()
        if row_abs == "$" or int(row_no) != from_row:
            return match.group(0)
        return f"{col_abs}{col}{row_abs}{to_row}"

    return _FORMULA_REF_RE.sub(repl, formula)


def normalize_natural_key_parts(platform: str, item: Dict[str, Any], entity_id: str, dimension: str) -> Tuple:
    """与 get_item_natural_key 对齐，用于原地合并时定位已有行"""
    return get_item_natural_key(platform, item, entity_id, dimension)


def _row_natural_key(row: List[Any], headers: List[str], platform: str, entity_id: str, dimension: str, id_col: str) -> Optional[Tuple]:
    row_dict = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
    date_val = row_dict.get("日期") or row_dict.get("时间") or ""
    if not str(date_val).strip():
        return None
    if platform == "taobao":
        row_dict.setdefault("任务ID", row_dict.get("任务ID") or entity_id)
        row_dict.setdefault("内容ID", row_dict.get("内容ID") or "")
        if dimension == "内容":
            row_dict["内容ID"] = row_dict.get("内容ID") or entity_id
        else:
            row_dict["任务ID"] = row_dict.get("任务ID") or entity_id
    return get_item_natural_key(platform, row_dict, entity_id, dimension)


def execute_inplace_merge_sync(
    task_id: int,
    trigger_type: str = "scheduled",
    custom_start_date: Optional[str] = None,
    custom_end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    原地合并同步：适用于已在飞书上人工维护的表。
    - 不重排行、不整块重写
    - 仅按自然键 upsert 变更行，按行区间写入
    - 跳过空单元格，绝不覆盖公式列（如 归属 / 任务组名称）
    - 已有行无数据时补空，有数据时只更新非空指标
    """
    started_at = datetime.now().isoformat()
    t0 = time.time()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            raise TaskNotFoundError(f"同步任务 #{task_id} 不存在")
        if not acquire_task_lease(conn, f"sync_task_{task_id}", owner=f"sync_{trigger_type}", lease_seconds=1800):
            raise TaskAlreadyRunningError(f"任务 #{task_id} 正在执行中，请勿重复触发")
        cursor.execute("SELECT * FROM task_sheets WHERE task_id = ?", (task_id,))
        sheets = cursor.fetchall()
        cursor.execute("""
            INSERT INTO runs (task_id, trigger_type, started_at, status, rows_fetched, rows_appended, rows_updated, message)
            VALUES (?, ?, ?, 'running', 0, 0, 0, '原地合并同步执行中...')
        """, (task_id, trigger_type, started_at))
        run_id = cursor.lastrowid
        conn.commit()

    feishu = FeishuClient()
    notifier = Notifier(feishu)
    spreadsheet_token = task["spreadsheet_token"]
    cutoff_date = custom_end_date or latest_sync_cutoff_date(task["platform"])
    total_fetched = 0
    total_appended = 0
    total_updated = 0
    errors: List[str] = []
    backups_written: List[Tuple[str, List[List[Any]]]] = []
    detail: List[Dict[str, Any]] = []

    # 每个子表独立容错：单个子表失败不影响其余子表，失败明细写入 runs.error_detail
    for s in sheets:
        try:
            sheet_title = s["sheet_title"]
            worksheet_id = s["worksheet_id"]
            headers = json.loads(s["header_json"])
            entity_ids = json.loads(s["entity_ids_json"])
            id_col = s["id_column"] or ("内容ID" if s["dimension"] == "内容" else "任务ID")
            date_col = s["date_column"] or "日期"
            dimension = s["dimension"] or "任务"

            raw_values = feishu.read_values(spreadsheet_token, worksheet_id, "A:BZ") or []
            formula_values = feishu.read_values_formula(spreadsheet_token, worksheet_id, "A:BZ") or []
            if not raw_values:
                errors.append(f"【{sheet_title}】表为空，跳过以免破坏结构")
                continue
            entity_ids = narrow_entity_ids_from_existing_rows(
                entity_ids, raw_values, headers, id_col
            )

            col_count = len(headers)
            data_rows = raw_values[1:]
            formula_rows = formula_values[1:] if len(formula_values) > 1 else []

            # 1. 计算已有数据的最新日期
            existing_dates: List[str] = []
            date_idx = headers.index(date_col) if date_col in headers else 0
            for r in data_rows:
                if date_idx < len(r):
                    compact = normalize_date_compact(r[date_idx])
                    if len(compact) == 8 and compact.isdigit():
                        existing_dates.append(f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}")

            if custom_start_date:
                start_date = custom_start_date
            else:
                configured_start = s["sheet_start_date"] if "sheet_start_date" in s.keys() else None
                if existing_dates:
                    latest = max(existing_dates)
                    try:
                        latest_dt = datetime.strptime(latest, "%Y-%m-%d").date()
                        start_date = (latest_dt - timedelta(days=int(task["calibration_days"]))).isoformat()
                    except Exception:
                        start_date = (date.today() - timedelta(days=int(task["calibration_days"]))).isoformat()
                elif configured_start:
                    start_date = configured_start
                else:
                    start_date = (date.today() - timedelta(days=int(task["calibration_days"]))).isoformat()

            if start_date > cutoff_date:
                start_date = cutoff_date

            # 2. 抓取
            fetched_items: List[Dict[str, Any]] = []
            sub_acc_id = task["sub_account_id"] if "sub_account_id" in task.keys() else None
            for eid in entity_ids:
                if task["platform"] == "jzt":
                    res = fetch_jzt_data(eid, start_date, cutoff_date, sub_account_id=sub_acc_id)
                elif task["platform"] == "taobao":
                    res = fetch_taobao_data(eid, dimension, start_date, cutoff_date)
                elif task["platform"] == "juguang":
                    res = fetch_juguang_data(eid, dimension, start_date, cutoff_date, sub_account_id=sub_acc_id)
                else:
                    raise ValueError(f"未知平台类型: {task['platform']}")
                rows = res.rows if hasattr(res, "rows") else res
                # 历史任务曾把所有任务ID复制进每个子表；只保留本子表负责的任务。
                rows = [
                    row
                    for row in rows
                    if is_entity_assigned_to_sheet(
                        eid,
                        entity_ids,
                        row.get("任务ID")
                        or row.get("内容ID")
                        or row.get(id_col),
                    )
                ]
                fetched_items.extend(rows)

            total_fetched += len(fetched_items)
            if not fetched_items:
                detail.append({"sheet": sheet_title, "fetched": 0, "appended": 0, "updated": 0, "note": "接口无新数据"})
                continue

            # 3. 建立已有行索引（自然键 -> 行号）
            key_to_row: Dict[Tuple, List[int]] = {}
            for offset, r in enumerate(data_rows):
                if not any(not _is_empty_cell(c) for c in r):
                    continue
                padded = list(r) + [""] * max(0, col_count - len(r))
                key = _row_natural_key(padded[:col_count], headers, task["platform"], entity_ids[0] if entity_ids else "", dimension, id_col)
                if key is None:
                    continue
                # 历史表可能已有重复自然键，全部记录并在本次同步一并校准
                key_to_row.setdefault(key, []).append(offset + 2)

            # 4. 生成变更（只写存在差异的单元格区间）
            pending_updates: List[Dict[str, Any]] = []
            appended_rows: List[List[Any]] = []
            rows_appended = 0
            rows_updated = 0
            last_row_needed = 1

            for item in fetched_items:
                mapped = map_item_to_row(item, headers, id_col, date_col)
                key = normalize_natural_key_parts(task["platform"], item, entity_ids[0] if entity_ids else "", dimension)
                if key in key_to_row:
                    duplicate_rows = key_to_row[key]
                    row_no = duplicate_rows[0]
                    idx_in_data = row_no - 2
                    old_row = data_rows[idx_in_data] if idx_in_data < len(data_rows) else []
                    old_formula_row = formula_rows[idx_in_data] if idx_in_data < len(formula_rows) else []
                    changed = False
                    for ci in range(col_count):
                        new_val = mapped[ci] if ci < len(mapped) else ""
                        if _is_empty_cell(new_val):
                            continue
                        formula_val = old_formula_row[ci] if ci < len(old_formula_row) else None
                        if isinstance(formula_val, str) and formula_val.startswith("="):
                            continue
                        old_val = old_row[ci] if ci < len(old_row) else ""
                        if not _cell_equivalent(old_val, new_val):
                            c_letter = column_letter(ci + 1)
                            pending_updates.append({
                                "range": f"{worksheet_id}!{c_letter}{row_no}:{c_letter}{row_no}",
                                "values": [[new_val]],
                            })
                            changed = True
                    for duplicate_row_no in duplicate_rows[1:]:
                        duplicate_idx = duplicate_row_no - 2
                        duplicate_formula_row = (
                            formula_rows[duplicate_idx]
                            if 0 <= duplicate_idx < len(formula_rows)
                            else []
                        )
                        for ci in range(col_count):
                            new_val = mapped[ci] if ci < len(mapped) else ""
                            if _is_empty_cell(new_val):
                                continue
                            formula_val = (
                                duplicate_formula_row[ci]
                                if ci < len(duplicate_formula_row)
                                else None
                            )
                            if isinstance(formula_val, str) and formula_val.startswith("="):
                                continue
                            c_letter = column_letter(ci + 1)
                            pending_updates.append({
                                "range": f"{worksheet_id}!{c_letter}{duplicate_row_no}:{c_letter}{duplicate_row_no}",
                                "values": [[new_val]],
                            })
                            changed = True
                    if changed:
                        rows_updated += 1
                    last_row_needed = max(last_row_needed, row_no)
                else:
                    appended_rows.append(mapped)
                    key_to_row[key] = [0]
                    rows_appended += 1

            # 5. 追加行：以"日期列"判定最后一条真实数据行。
            # 不能用整行非空判定 —— 归属/任务组名称等公式列会预填到几十上百行，
            # 否则新数据会被追加到很靠后的位置，中间留下大段空行。
            last_existing_row = 1
            for offset, r in enumerate(data_rows):
                if date_idx < len(r) and not _is_empty_cell(r[date_idx]):
                    last_existing_row = offset + 2

            write_plan: List[Dict[str, Any]] = []
            if pending_updates:
                write_plan.extend(pending_updates)
            if appended_rows:
                start_row = last_existing_row + 1
                target_last_row = start_row + len(appended_rows) - 1
                try:
                    sheet_meta = next(
                        (x for x in feishu.get_sheets(spreadsheet_token) if x.get("sheet_id") == worksheet_id),
                        None,
                    )
                    grid = (sheet_meta or {}).get("grid_properties") or {}
                    current_rows = int(grid.get("row_count") or 0)
                    if current_rows and target_last_row > current_rows:
                        feishu.add_rows(spreadsheet_token, worksheet_id, target_last_row - current_rows)
                        time.sleep(1.0)
                except Exception as ex:
                    print(f"[InPlaceMerge] add_rows note: {ex}")
                for offset, row in enumerate(appended_rows):
                    row_no = start_row + offset
                    # 新行若落在公式列，写入公式列的"计算后结果"，而不是公式本身。
                    # 平移公式会因引用类型不同（日期文本/空值）导致 #VALUE!，且历史上
                    # 该列也可能本来就是静态文本（如 启萃图文-F 的任务组名称）。
                    prev_row_no = row_no - 1
                    prev_formula_row = (
                        formula_rows[prev_row_no - 2]
                        if 0 <= prev_row_no - 2 < len(formula_rows)
                        else []
                    )
                    prev_value_row = (
                        data_rows[prev_row_no - 2]
                        if 0 <= prev_row_no - 2 < len(data_rows)
                        else []
                    )
                    for ci in range(min(col_count, len(row))):
                        formula_val = prev_formula_row[ci] if ci < len(prev_formula_row) else None
                        if isinstance(formula_val, str) and formula_val.startswith("="):
                            fallback = prev_value_row[ci] if ci < len(prev_value_row) else ""
                            row[ci] = "" if _is_empty_cell(fallback) else fallback
                    # 只写非公式列（表头中能识别的业务列）
                    for ci in range(min(col_count, len(row))):
                        if _is_empty_cell(row[ci]):
                            continue
                        c_letter = column_letter(ci + 1)
                        write_plan.append({
                            "range": f"{worksheet_id}!{c_letter}{row_no}:{c_letter}{row_no}",
                            "values": [[row[ci]]],
                        })

            # 6. 写前备份
            if write_plan:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = BACKUPS_DIR / f"{task_id}_{worksheet_id}_{stamp}.json"
                backup_file.write_text(json.dumps(raw_values, ensure_ascii=False), encoding="utf-8")
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO backups (task_id, worksheet_id, backup_path, row_count, created_at) VALUES (?, ?, ?, ?, ?)",
                        (task_id, worksheet_id, str(backup_file), len(raw_values), datetime.now().isoformat()),
                    )
                    conn.commit()
                clean_old_backups(task_id, worksheet_id, 30)
                backups_written.append((worksheet_id, raw_values))

                feishu.batch_update_values(spreadsheet_token, write_plan)

                # 7. 回读校验：确认追加行已落地
                verified = feishu.read_values(spreadsheet_token, worksheet_id, "A:BZ")
                if len(verified) < 1:
                    raise FeishuWriteError(f"【{sheet_title}】写后回读失败：表头丢失")
                apply_date_column_format(
                    feishu,
                    spreadsheet_token,
                    worksheet_id,
                    headers,
                    date_col,
                    len(verified),
                )

            total_appended += rows_appended
            total_updated += rows_updated
            detail.append({
                "sheet": sheet_title,
                "fetched": len(fetched_items),
                "appended": rows_appended,
                "updated": rows_updated,
                "range": f"{start_date}~{cutoff_date}",
            })

        except Exception as exc:
            errors.append(f"【{s['sheet_title']}】{type(exc).__name__}: {exc}")
            detail.append({
                "sheet": s["sheet_title"],
                "fetched": 0,
                "appended": 0,
                "updated": 0,
                "error": str(exc),
            })

    finished_at = datetime.now().isoformat()
    duration_ms = int((time.time() - t0) * 1000)
    status = "failed" if errors else "success"
    err_detail = "; ".join(errors) if errors else None
    message = f"抓取{total_fetched}行，追加{total_appended}行，更新{total_updated}行"
    if trigger_type.startswith("backfill"):
        message = f"历史补数({custom_start_date}~{cutoff_date})：抓取{total_fetched}行，追加{total_appended}行，更新{total_updated}行"

    with get_db() as conn:
        conn.execute("""
            UPDATE runs SET finished_at = ?, status = ?, rows_fetched = ?, rows_appended = ?,
                rows_updated = ?, duration_ms = ?, message = ?, error_detail = ?
            WHERE id = ?
        """, (finished_at, status, total_fetched, total_appended, total_updated,
              duration_ms, message, err_detail, run_id))
        conn.execute("""
            UPDATE tasks SET last_run_at = ?, last_status = ?, last_error = ?, updated_at = ? WHERE id = ?
        """, (finished_at, status, err_detail, finished_at, task_id))
        conn.commit()
        release_task_lease(conn, f"sync_task_{task_id}")

    if status == "failed":
        notifier.notify_failure(task["name"], task["platform"], err_detail or "未知错误")

    return {
        "status": status,
        "rows_fetched": total_fetched,
        "rows_appended": total_appended,
        "rows_updated": total_updated,
        "duration_ms": duration_ms,
        "errors": errors,
        "detail": detail,
    }

def execute_task_sync(task_id: int, trigger_type: str = "scheduled", custom_start_date: Optional[str] = None, custom_end_date: Optional[str] = None, force_upsert: bool = False) -> Dict[str, Any]:
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
            entity_ids = narrow_entity_ids_from_existing_rows(
                entity_ids, existing_values, headers, id_col
            )
            
            # 计算拉取日期范围
            dates_in_sheet = []
            if len(existing_values) > 1:
                date_idx = headers.index(date_col) if (headers and date_col in headers) else 0
                for r in existing_values[1:]:
                    if len(r) > date_idx and r[date_idx]:
                        compact = normalize_date_compact(r[date_idx])
                        if len(compact) == 8 and compact.isdigit():
                            dates_in_sheet.append(f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}")
                        else:
                            d_str = str(r[date_idx]).strip()[:10].replace("/", "-")
                            if len(d_str) == 10:
                                dates_in_sheet.append(d_str)
                            
            if custom_start_date:
                start_date = custom_start_date
                if custom_end_date:
                    cutoff_date = custom_end_date
            elif task["update_mode"] == "overwrite":
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
                    res = fetch_jzt_data(eid, start_date, cutoff_date, sub_account_id=sub_acc_id)
                elif task["platform"] == "taobao":
                    res = fetch_taobao_data(eid, dimension, start_date, cutoff_date)
                elif task["platform"] == "juguang":
                    res = fetch_juguang_data(eid, dimension, start_date, cutoff_date, sub_account_id=sub_acc_id)
                else:
                    raise ValueError(f"未知平台类型: {task['platform']}")

                rows = res.rows if hasattr(res, "rows") else res
                rows = [
                    row
                    for row in rows
                    if is_entity_assigned_to_sheet(
                        eid,
                        entity_ids,
                        row.get("任务ID")
                        or row.get("内容ID")
                        or row.get(id_col),
                    )
                ]
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
            
            # 若增量模式下接口未返回任何新数据，无需重复写回或备份飞书工作表
            if task["update_mode"] == "append" and not fetched_items:
                continue

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
            
            # 动态扩列：若多任务合并中新任务产生新字段，自动在飞书工作表右侧追加新列
            extra_cols = []
            for item in fetched_items:
                for col in item.keys():
                    if col and col not in headers and col not in extra_cols:
                        extra_cols.append(col)

            if extra_cols:
                try:
                    feishu.add_columns(task["spreadsheet_token"], worksheet_id, length=len(extra_cols))
                except Exception as ex:
                    print(f"[DynamicColumn] add_columns note: {ex}")
                headers = list(headers) + extra_cols
                try:
                    feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=1, rows=[headers])
                except Exception as ex:
                    print(f"[DynamicColumn] update header row note: {ex}")
                with get_db() as conn:
                    conn.execute(
                        "UPDATE task_sheets SET header_json = ? WHERE id = ?",
                        (json.dumps(headers, ensure_ascii=False), s["id"])
                    )
                    conn.commit()

            primary_entity_id = entity_ids[0] if entity_ids else ""
            id_idx = headers.index(id_col) if (headers and id_col in headers) else 1
            date_idx = headers.index(date_col) if (headers and date_col in headers) else 0
            is_overwrite = (task["update_mode"] == "overwrite") and not force_upsert
            if is_overwrite:
                # 分水岭智能全量更新（窗口全量覆盖 + 历史基线保护，彻底防止超期老数据被抹除）
                if not fetched_items and existing_values:
                    # 若接口未返回任何数据，安全起见绝不抹空表格
                    pass
                else:
                    # 1. 计算每个任务在本次 API 抓取中的最早返回日期 (分水岭)
                    min_date_by_task = {}
                    for item in fetched_items:
                        raw_tid = str(item.get("任务ID") or item.get(id_col) or primary_entity_id).strip()
                        if raw_tid.endswith(".0"):
                            raw_tid = raw_tid[:-2]
                        d = normalize_date_compact(item.get("日期") or item.get("时间") or item.get(date_col) or "")[:8]
                        if d and d.isdigit() and len(d) == 8:
                            if raw_tid not in min_date_by_task or d < min_date_by_task[raw_tid]:
                                min_date_by_task[raw_tid] = d

                    # 2. 提取分水岭之前的历史基线受保护行 (日期 < API最早日期的老数据 100% 完整保留)
                    protected_history_rows = []
                    if len(existing_values) > 1:
                        for r in existing_values[1:]:
                            if any(r):
                                padded_r = list(r) + [""] * max(0, len(headers) - len(r))
                                padded_r = padded_r[:len(headers)]
                                r_tid = str(padded_r[id_idx] if len(padded_r) > id_idx else "").strip()
                                if r_tid.endswith(".0"):
                                    r_tid = r_tid[:-2]
                                r_date = normalize_date_compact(padded_r[date_idx] if len(padded_r) > date_idx else "")[:8]
                                min_api_d = min_date_by_task.get(r_tid)
                                # 若老数据早于本次 API 能够返回的最早日期，或者该任务 API 暂未返回数据，严格保留
                                if min_api_d is None or (r_date and r_date < min_api_d):
                                    protected_history_rows.append(padded_r)

                    # 3. 本次 API 返回的活跃窗口数据
                    only_new_rows = [map_item_to_row(item, headers, id_col, date_col) for item in fetched_items]
                    protected_history_rows = [
                        normalize_row_date_value(r, date_idx) for r in protected_history_rows
                    ]
                    only_new_rows = [
                        normalize_row_date_value(r, date_idx) for r in only_new_rows
                    ]

                    # 4. 合并历史基线行与活跃重算行，并执行全局结构化排序
                    combined_rows = protected_history_rows + only_new_rows
                    sorted_rows = sort_sheet_data_rows(combined_rows, headers, id_col, date_col, entity_ids)

                    # 5. 写入飞书表格并清理多余尾部行
                    if sorted_rows:
                        feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=2, rows=sorted_rows)
                        total_updated += len(sorted_rows)

                        last_row = feishu.find_last_row_index(task["spreadsheet_token"], worksheet_id)
                        target_end_row = len(sorted_rows) + 1
                        if last_row > target_end_row:
                            feishu.clear_rows_below(task["spreadsheet_token"], worksheet_id, keep_header_row=target_end_row, col_count=len(headers) or 30)
            else:
                # 增量更新/Upsert（结构化任务组排序，彻底解决多任务合并时的乱序堆叠问题）
                # 1. 整理与合并所有已有历史行与新抓取行
                all_rows_map = {}
                existing_keys = set()
                if len(existing_values) > 1:
                    for r in existing_values[1:]:
                        if any(r):
                            padded_r = list(r) + [""] * max(0, len(headers) - len(r))
                            padded_r = padded_r[:len(headers)]
                            normalize_row_date_value(padded_r, date_idx)
                            row_dict = dict(zip(headers, padded_r))
                            key = get_item_natural_key(task["platform"], row_dict, primary_entity_id, dimension)
                            all_rows_map[key] = padded_r
                            existing_keys.add(key)

                # 2. 合并新抓取数据 (相同自然键更新指标，新自然键并入)
                rows_updated_count = 0
                rows_appended_count = 0
                for item in fetched_items:
                    mapped_row = map_item_to_row(item, headers, id_col, date_col)
                    key = get_item_natural_key(task["platform"], item, primary_entity_id, dimension)
                    if key in existing_keys:
                        rows_updated_count += 1
                    else:
                        rows_appended_count += 1
                        existing_keys.add(key)
                    all_rows_map[key] = mapped_row

                # 3. 双层全局结构化排序 (任务组间按配置顺序排列，任务组内日期严格从旧到新升序)
                sorted_rows = sort_sheet_data_rows(list(all_rows_map.values()), headers, id_col, date_col, entity_ids)

                # 4. 规整批量回写并清理末尾冗余脏行
                if sorted_rows:
                    feishu.write_rows(task["spreadsheet_token"], worksheet_id, start_row=2, rows=sorted_rows)
                    total_updated += rows_updated_count
                    total_appended += rows_appended_count

                    last_row = feishu.find_last_row_index(task["spreadsheet_token"], worksheet_id)
                    target_end_row = len(sorted_rows) + 1
                    if last_row > target_end_row:
                        feishu.clear_rows_below(task["spreadsheet_token"], worksheet_id, keep_header_row=target_end_row, col_count=len(headers) or 30)

            verify_rows = feishu.read_values(task["spreadsheet_token"], worksheet_id, "A:AZ")
            if len(verify_rows) < 1:
                raise FeishuWriteError(f"工作表【{sheet_title}】写后回读校验失败：表头或数据丢失")
            worksheet_rows = len(verify_rows)
            apply_date_column_format(
                feishu,
                task["spreadsheet_token"],
                worksheet_id,
                headers,
                date_col,
                worksheet_rows,
            )
                
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
                (f"补充历史数据完成({custom_start_date or start_date}~{custom_end_date or cutoff_date})：抓取{total_fetched}行，追加{total_appended}行，更新{total_updated}行" if trigger_type.startswith("backfill") else f"抓取{total_fetched}行，追加{total_appended}行，更新{total_updated}行"),
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

