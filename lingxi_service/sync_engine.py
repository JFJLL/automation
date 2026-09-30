import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.business_time import now_business_tz
from core.errors import TaskNotFoundError
from core.sync_runner import TaskRunGuard
from feishu.client import FeishuClient, column_letter

from lingxi_service.client import fetch_lingxi_keywords
from lingxi_service.db import get_db


def parse_existing_lingxi_sheet(existing_rows: List[List[Any]]) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    """
    解析灵犀现有表格结构：
    第一行：表头 ['关键词', '2026-09-29', '2026-09-30', ...]
    后续行：[关键词, 数量1, 数量2, ...]
    返回：
      existing_dates: [date_str1, date_str2, ...]
      keyword_history: { kw: { date_str: user_cnt } }
    """
    if not existing_rows or len(existing_rows) < 1:
        return [], {}

    row0 = existing_rows[0]
    existing_dates = []
    date_col_map = {} # date_str -> col_index
    for idx in range(1, len(row0)):
        val = str(row0[idx]).strip() if row0[idx] is not None else ""
        if val:
            existing_dates.append(val)
            date_col_map[val] = idx

    keyword_history = {}
    for r in existing_rows[1:]:
        if not r or not str(r[0]).strip():
            continue
        kw = str(r[0]).strip()
        kw_dict = {}
        for d_str, col_idx in date_col_map.items():
            if col_idx < len(r) and r[col_idx] not in (None, ""):
                try:
                    kw_dict[d_str] = int(r[col_idx])
                except Exception:
                    kw_dict[d_str] = r[col_idx]
            else:
                kw_dict[d_str] = 0
        keyword_history[kw] = kw_dict

    return existing_dates, keyword_history

def build_lingxi_date_matrix(
    keywords: List[str],
    target_dates: List[str],
    new_date: str,
    new_data: Dict[str, Dict[str, Any]],
    old_history: Dict[str, Dict[str, Any]]
) -> List[List[Any]]:
    """
    构建日期横向增长的灵犀表格矩阵：
    表头：['关键词', '2026-09-29', '2026-09-30', ...]
    每一行：[kw, cnt1, cnt2, ...]
    """
    header = ["关键词"] + target_dates
    matrix = [header]

    for kw in keywords:
        row = [kw]
        kw_hist = old_history.get(kw, {})
        new_kw_item = new_data.get(kw, {})
        for d in target_dates:
            if d == new_date and kw in new_data:
                cnt = new_kw_item.get("user_cnt", 0)
                row.append(cnt)
            elif d in kw_hist:
                row.append(kw_hist[d])
            else:
                row.append(0)
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
    """直接生成灵犀关键词飞书在线表格，列即为当前日期"""
    from app.config import SHARED_FOLDER_TOKEN
    feishu = FeishuClient()

    today_str = datetime.now().strftime("%Y-%m-%d")
    sheet_title = title or f"小红书灵犀关键词覆盖人数_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    fetch_res = fetch_lingxi_keywords(keywords)
    matrix = build_lingxi_date_matrix(
        keywords=keywords,
        target_dates=[today_str],
        new_date=today_str,
        new_data=fetch_res["results"],
        old_history={}
    )

    meta = feishu.create_spreadsheet(title=sheet_title, folder_token=SHARED_FOLDER_TOKEN or None)
    ss_token = meta.get("spreadsheet_token") or meta.get("token")
    ss_url = meta.get("url")

    sheets = feishu.get_sheets(ss_token)
    sheet_id = sheets[0]["sheet_id"]

    write_matrix_to_sheet(feishu, ss_token, sheet_id, matrix)

    try:
        feishu.set_sheet_share_permission(ss_token)
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
    update_mode: str = "append",
    rrule: str = "FREQ=DAILY;BYHOUR=9;BYMINUTE=30",
    folder_token: Optional[str] = None
) -> int:
    """创建灵犀关键词定时监控任务（固定为按日期增量更新）"""
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

    guard = TaskRunGuard(conn=conn, task_key=task_key, task_id=task_id, module="lingxi", trigger_type=trigger_type, lease_seconds=600, task_name=task_name)

    with guard:
        keywords: List[str] = json.loads(task_dict["keywords_json"])
        removed_kws: List[str] = json.loads(task_dict.get("removed_keywords_json") or "[]")
        update_mode = task_dict.get("update_mode", "append")
        ss_token = task_dict["spreadsheet_token"]
        ss_url = task_dict["spreadsheet_url"]

        # 过滤已被移除的词
        active_keywords = [k for k in keywords if k not in set(removed_kws)]
        feishu = FeishuClient()
        fetch_res = fetch_lingxi_keywords(active_keywords)

        # 失败词绝不写 0 (严格模式：只要有失败词，中止写表并让 run 失败)
        failed_list = fetch_res.get("failed") or []
        if failed_list:
            err_msg = f"抓取失败词: {', '.join(failed_list)}，严格模式下中止写入以防止写入虚假 0 值"
            guard.finish_run(
                status="failed",
                message=err_msg[:200],
                error_detail=err_msg,
                words_total=len(active_keywords),
                words_succeeded=len(fetch_res.get("success", [])),
                words_failed=len(failed_list)
            )
            raise RuntimeError(err_msg)

        today_str = now_business_tz().strftime("%Y-%m-%d")
        sheets = feishu.get_sheets(ss_token)
        if not sheets:
            raise RuntimeError(f"Spreadsheet {ss_token} has no sheets.")
        sheet_id = sheets[0]["sheet_id"]

        from core.feishu_matrix import backup_sheet_values, rollback_sheet_values, write_matrix_to_sheet

        # 读取现有历史内容以按日期向右对齐
        last_row = feishu.find_last_row_index(ss_token, sheet_id)
        existing_rows = []
        if last_row >= 1:
            existing_rows = feishu.read_values(ss_token, sheet_id, f"A1:ZZ{max(2, last_row)}") or []

        existing_dates, old_history = parse_existing_lingxi_sheet(existing_rows)

        if update_mode == "overwrite":
            # overwrite 仅保留最新抓取日期
            target_dates = [today_str]
        else:
            # append 增量向右对齐
            if today_str not in existing_dates:
                target_dates = existing_dates + [today_str]
            else:
                target_dates = existing_dates

        all_target_keywords = list(dict.fromkeys(list(old_history.keys()) + active_keywords))

        matrix = build_lingxi_date_matrix(
            keywords=all_target_keywords,
            target_dates=target_dates,
            new_date=today_str,
            new_data=fetch_res["results"],
            old_history=old_history
        )

        # 写前备份
        backup = backup_sheet_values(feishu, ss_token, sheet_id)
        try:
            write_matrix_to_sheet(feishu, ss_token, sheet_id, matrix)
        except Exception as write_err:
            rollback_sheet_values(feishu, ss_token, sheet_id, backup)
            guard.finish_run(
                status="failed",
                message=f"写入飞书表格失败: {write_err}",
                error_detail=str(write_err),
                words_total=len(active_keywords),
                words_succeeded=len(fetch_res.get("success", [])),
                words_failed=0
            )
            raise write_err

        guard.finish_run(
            status="success",
            message=f"成功同步 {len(fetch_res.get('success', []))} 个关键词",
            words_total=len(active_keywords),
            words_succeeded=len(fetch_res.get("success", [])),
            words_failed=0
        )

        return {
            "success": True,
            "spreadsheet_url": ss_url,
            "words_succeeded": len(fetch_res.get("success", [])),
            "words_failed": 0
        }

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
        now_iso = now_business_tz().isoformat()
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
        now_iso = now_business_tz().isoformat()
        cur.execute("UPDATE lingxi_tasks SET keywords_json = ?, removed_keywords_json = ?, updated_at = ? WHERE id = ?", (
            json.dumps(remaining, ensure_ascii=False),
            json.dumps(new_removed, ensure_ascii=False),
            now_iso,
            task_id
        ))
    return remaining
