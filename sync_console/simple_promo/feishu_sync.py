# -*- coding: utf-8 -*-
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from app.config import BASE_DIR
from core.database import get_simple_promo_db
from feishu.client import FeishuClient

PROMO_SETTINGS_FILE = BASE_DIR / "data" / "simple_promo_feishu.json"

def get_or_create_promo_spreadsheet() -> Tuple[str, str]:
    """
    获取或创建专门用于存放简单投老笔记暂停运行记录的飞书在线电子表格
    """
    feishu = FeishuClient()
    if PROMO_SETTINGS_FILE.exists():
        try:
            with open(PROMO_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                ss_token = data.get("spreadsheet_token")
                ss_url = data.get("spreadsheet_url")
                if ss_token and ss_url:
                    return ss_token, ss_url
        except Exception:
            pass

    folder_token = feishu.get_or_create_shared_folder()
    title = f"【监控中心】简单投老笔记巡检暂停记录"
    sheet_res = feishu.create_spreadsheet(title, folder_token)
    ss_token = sheet_res["spreadsheet_token"]
    ss_url = sheet_res.get("url") or f"https://feishu.cn/sheets/{ss_token}"

    try:
        feishu.set_public_permission(ss_token, edit=True)
    except Exception:
        pass

    # 初始化第一个工作表为【每日巡检汇总】
    try:
        sheets = feishu.get_sheets(ss_token)
        if sheets:
            first_id = sheets[0]["sheet_id"]
            # 重命名工作表需调用更新接口或写入标题头
            summary_headers = [
                ["巡检日期", "执行时间", "运行模式", "覆盖账号数", "扫描笔记总数",
                 "老笔记总数", "本次暂停篇数", "原已暂停", "新笔记保留", "执行状态", "详细日志说明"]
            ]
            feishu.write_cells(ss_token, f"{first_id}!A1:K1", summary_headers)
    except Exception as e:
        print(f"[FeishuSync] Init summary sheet header warning: {e}")

    # 保存配置
    PROMO_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMO_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "spreadsheet_token": ss_token,
            "spreadsheet_url": ss_url,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, f, ensure_ascii=False, indent=2)

    return ss_token, ss_url

def sync_run_to_feishu(run_id: int) -> Dict[str, Any]:
    """
    将指定运行批次 (Run) 的老笔记暂停与排查结果同步写入飞书表格：
    1. 在【每日巡检汇总】总表中追加一行统计；
    2. 为当天自动创建独立日期 Tab (如 '2026-10-16' 或 '10-16_Run#1')，存放该批次全部笔记明细，便于一键切换日期查验。
    """
    conn = get_simple_promo_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM simple_promo_runs WHERE id = ?", (run_id,))
    run_row = cur.fetchone()
    if not run_row:
        raise ValueError(f"未找到运行记录 ID={run_id}")
    run = dict(run_row)

    cur.execute("SELECT * FROM simple_promo_run_items WHERE run_id = ? ORDER BY id ASC", (run_id,))
    items = [dict(r) for r in cur.fetchall()]

    ss_token, ss_url = get_or_create_promo_spreadsheet()
    feishu = FeishuClient()

    sheets = feishu.get_sheets(ss_token)
    summary_sheet_id = sheets[0]["sheet_id"] if sheets else "0"

    run_date = (run.get("started_at") or "").split(" ")[0] or datetime.now().strftime("%Y-%m-%d")
    mode_text = "线上实际执行" if run.get("mode") == "EXECUTE" else "仅巡检排查"

    # 1. 在汇总表中追加写入该批次概览
    last_row = feishu.find_last_row_index(ss_token, summary_sheet_id)
    next_row = max(2, last_row + 1)
    summary_row = [[
        run_date,
        run.get("started_at") or "",
        mode_text,
        run.get("accounts_count") or 0,
        run.get("total_notes_scanned") or 0,
        run.get("pre_cutoff_notes_count") or 0,
        run.get("paused_success_count") if run.get("mode") == "EXECUTE" else run.get("to_pause_count") or 0,
        run.get("already_paused_count") or 0,
        (run.get("total_notes_scanned") or 0) - (run.get("pre_cutoff_notes_count") or 0),
        run.get("status") or "",
        run.get("message") or ""
    ]]
    feishu.write_cells(ss_token, f"{summary_sheet_id}!A{next_row}:K{next_row}", summary_row)

    # 2. 创建或更新对应日期的明细工作表 Tab
    tab_title = f"{run_date}_Run{run_id}"
    sheet_map = {s["title"]: s["sheet_id"] for s in sheets}

    if tab_title not in sheet_map:
        new_sheet_id = feishu.add_worksheet(ss_token, tab_title)
    else:
        new_sheet_id = sheet_map[tab_title]

    # 写入明细表表头
    detail_headers = [
        ["子账号名称", "子账号ID", "创意ID", "笔记ID", "笔记发布时间", "笔记标题",
         "小红书直达链接", "原投放状态", "操作动作", "处理状态", "错误信息"]
    ]
    feishu.write_cells(ss_token, f"{new_sheet_id}!A1:K1", detail_headers)

    # 批量写入笔记明细 (按 200 条分块写入保证稳定性)
    detail_rows = []
    for it in items:
        detail_rows.append([
            it.get("account_name") or "",
            it.get("account_id") or "",
            it.get("creativity_id") or "",
            it.get("note_id") or "",
            it.get("note_publish_time") or "",
            it.get("note_title") or "",
            it.get("note_url") or "",
            it.get("original_status") or "",
            it.get("action") or "",
            it.get("result_status") or "",
            it.get("error_message") or ""
        ])

    if detail_rows:
        chunk_size = 200
        start_r = 2
        for i in range(0, len(detail_rows), chunk_size):
            chunk = detail_rows[i:i + chunk_size]
            end_r = start_r + len(chunk) - 1
            feishu.write_cells(ss_token, f"{new_sheet_id}!A{start_r}:K{end_r}", chunk)
            start_r = end_r + 1

    return {
        "run_id": run_id,
        "spreadsheet_token": ss_token,
        "spreadsheet_url": ss_url,
        "tab_title": tab_title,
        "total_items_synced": len(items)
    }
