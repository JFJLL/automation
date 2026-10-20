# -*- coding: utf-8 -*-
import os
import csv
import json
import sqlite3
from pathlib import Path
from datetime import datetime

DEFAULT_ACCOUNTS = [
    {"id": "691d9a94252ae1001521f3d3", "name": "易美传播-凯乐石EX3-红京"},
    {"id": "6971f17051a1f100153a9d55", "name": "易美传播-凯乐石EX330-红京"},
    {"id": "67d4046297c0d1001531a013", "name": "易美传播-凯乐石DU红京"},
    {"id": "6965e3674c897400159341cc", "name": "易美传播-凯乐石黑山红京"},
]

CSV_PATH = Path(r"C:\Users\liuhao_PC\Documents\Codex\2026-10-16\https-partner-xiaohongshu-com-partner-subaccount-3\outputs\凯乐石简单投老笔记暂停明细表_20261016.csv")

def seed_simple_promo_data(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM simple_promo_runs")
    if cur.fetchone()[0] > 0:
        return  # Already seeded or has data

    # 1. Seed initial task
    cur.execute("""
        INSERT INTO simple_promo_tasks (
            id, name, accounts_json, cutoff_date, whitelist_note_ids_json,
            rrule, status, next_run_at, last_run_at, last_status, last_error,
            created_at, updated_at
        ) VALUES (
            1, ?, ?, '2026-01-01 00:00:00', '[]',
            'RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0', 'active', ?, ?, 'success', NULL,
            ?, ?
        )
    """, (
        "凯乐石简单投老笔记巡检暂停",
        json.dumps(DEFAULT_ACCOUNTS, ensure_ascii=False),
        "2026-10-17T09:00:00",
        "2026-10-16T11:38:16",
        "2026-10-16T10:00:00",
        "2026-10-16T11:39:23"
    ))

    # 2. Seed run #1
    summary = {
        "易美传播-凯乐石EX3-红京": {"total": 445, "pre_2026": 186, "paused": 137, "already_paused": 49, "post_2026": 259},
        "易美传播-凯乐石EX330-红京": {"total": 444, "pre_2026": 108, "paused": 102, "already_paused": 6, "post_2026": 336},
        "易美传播-凯乐石DU红京": {"total": 359, "pre_2026": 64, "paused": 64, "already_paused": 0, "post_2026": 295},
        "易美传播-凯乐石黑山红京": {"total": 692, "pre_2026": 57, "paused": 57, "already_paused": 0, "post_2026": 635}
    }

    cur.execute("""
        INSERT INTO simple_promo_runs (
            id, task_id, task_name, trigger_type, mode, cutoff_date,
            started_at, finished_at, duration_ms, status, accounts_count,
            total_notes_scanned, pre_cutoff_notes_count, to_pause_count,
            paused_success_count, already_paused_count, message, error_detail, summary_json
        ) VALUES (
            1, 1, '凯乐石简单投老笔记巡检暂停', 'manual', 'EXECUTE', '2026-01-01 00:00:00',
            '2026-10-16 11:34:25', '2026-10-16 11:39:23', 298000, 'success', 4,
            1940, 415, 360, 360, 55,
            '成功执行老笔记暂停，共排查 4 个子账号 1,940 篇笔记，415 篇老笔记全部进入暂停状态（本次暂停 360 篇，原已暂停 55 篇），新笔记 1,525 篇保持正常投放。',
            NULL, ?
        )
    """, (json.dumps(summary, ensure_ascii=False),))

    # 3. Seed run items
    if CSV_PATH.exists():
        with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            items = []
            for r in reader:
                note_id = r.get("笔记ID", "").strip()
                items.append((
                    1,
                    r.get("子账号名称", "").strip(),
                    r.get("子账号ID", "").strip(),
                    "",
                    r.get("创意ID", "").strip(),
                    note_id,
                    r.get("笔记标题", "").strip(),
                    r.get("笔记发布时间", "").strip(),
                    f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
                    r.get("原投放状态", "").strip(),
                    r.get("操作动作", "").strip(),
                    r.get("处理状态", "").strip(),
                    ""
                ))
            if items:
                cur.executemany("""
                    INSERT INTO simple_promo_run_items (
                        run_id, account_name, account_id, campaign_group_id,
                        creativity_id, note_id, note_title, note_publish_time,
                        note_url, original_status, action, result_status, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, items)
    conn.commit()
