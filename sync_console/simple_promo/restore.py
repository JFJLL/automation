# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# 保证可直接作为脚本运行
CURRENT_DIR = Path(__file__).resolve().parent
CONSOLE_DIR = CURRENT_DIR.parent
if str(CONSOLE_DIR) not in sys.path:
    sys.path.insert(0, str(CONSOLE_DIR))
if str(CONSOLE_DIR.parent) not in sys.path:
    sys.path.insert(0, str(CONSOLE_DIR.parent))

from core.database import get_simple_promo_db
from simple_promo.engine import JuguangSimplePromotionClient
from simple_promo.backup import save_promo_execution_snapshot, PROMO_BACKUP_DIR

def rollback_simple_promo_run(run_id: int) -> Dict[str, Any]:
    """
    按 Run ID 一键原样恢复该批次被暂停的全部笔记创意 (开启投放，actionType=1)
    无论前端是否开启，均可随时通过脚本或后台调用恢复。
    """
    conn = get_simple_promo_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM simple_promo_runs WHERE id = ?", (run_id,))
    run_row = cur.fetchone()
    if not run_row:
        raise ValueError(f"未找到运行记录 ID={run_id}")

    run_dict = dict(run_row)
    task_name = run_dict["task_name"]

    # 提取该次运行中所有被实际暂停的创意
    cur.execute("""
        SELECT * FROM simple_promo_run_items
        WHERE run_id = ? AND (action = '暂停投放' OR result_status = '已暂停')
    """, (run_id,))
    items = [dict(r) for r in cur.fetchall()]

    # 如果数据库中已被清理，尝试从本地持久化备份快照中恢复
    if not items:
        backup_files = list(PROMO_BACKUP_DIR.glob(f"*_run_{run_id}.json"))
        if backup_files:
            with open(backup_files[0], "r", encoding="utf-8") as f:
                snapshot = json.load(f)
                items = snapshot.get("items", [])

    if not items:
        return {
            "run_id": run_id,
            "status": "NO_ITEMS",
            "message": f"Run #{run_id} 中未发现需要恢复的已暂停笔记创意",
            "total_resumed": 0
        }

    # 按子账号分组
    account_groups: Dict[str, Dict[str, Any]] = {}
    for it in items:
        aid = it["account_id"]
        aname = it["account_name"]
        cid = it["creativity_id"]
        if aid not in account_groups:
            account_groups[aid] = {
                "account_id": aid,
                "account_name": aname,
                "creativity_ids": [],
                "items": []
            }
        account_groups[aid]["creativity_ids"].append(cid)
        account_groups[aid]["items"].append(it)

    total_resumed = 0
    resumed_accounts = {}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for aid, group in account_groups.items():
        aname = group["account_name"]
        cids = group["creativity_ids"]
        try:
            client = JuguangSimplePromotionClient(aid, aname)
            res = client.batch_resume_creativities(cids, chunk_size=50)
            success_count = res["success_count"]
            total_resumed += success_count
            resumed_accounts[aname] = {
                "account_id": aid,
                "total": len(cids),
                "resumed": success_count,
                "failed": res["failed_count"],
                "errors": res.get("errors", [])
            }
        except Exception as e:
            resumed_accounts[aname] = {
                "account_id": aid,
                "total": len(cids),
                "resumed": 0,
                "failed": len(cids),
                "error": str(e)
            }

    # 更新数据库明细状态
    with conn:
        cur.execute("""
            UPDATE simple_promo_run_items
            SET action = '恢复投放', result_status = '已恢复'
            WHERE run_id = ? AND (action = '暂停投放' OR result_status = '已暂停')
        """, (run_id,))

        old_msg = run_dict.get("message") or ""
        new_msg = f"{old_msg} [已于 {now_str} 执行一键恢复开启投放共 {total_resumed} 篇]"
        cur.execute("""
            UPDATE simple_promo_runs
            SET message = ?
            WHERE id = ?
        """, (new_msg, run_id))

    # 保存本地持久化回滚备份快照
    save_promo_execution_snapshot(
        run_id=run_id,
        task_id=run_dict.get("task_id"),
        task_name=task_name,
        mode="EXECUTE",
        cutoff_date=run_dict.get("cutoff_date") or "",
        accounts_summary=resumed_accounts,
        paused_items=items,
        action_type="RESUME_ROLLBACK"
    )

    return {
        "run_id": run_id,
        "task_name": task_name,
        "status": "SUCCESS",
        "total_resumed": total_resumed,
        "details": resumed_accounts,
        "message": f"成功将 Run #{run_id} 中 {total_resumed} 篇笔记恢复为【开启投放】状态"
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小红书聚光简单投已暂停老笔记一键原样恢复脚本")
    parser.add_argument("--run-id", type=int, required=True, help="需要回滚恢复的运行记录 ID (例如 1)")
    args = parser.parse_args()

    print(f"\n============================================================")
    print(f"小红书聚光简单投老笔记【一键原样恢复投放】引擎")
    print(f"目标 Run ID: #{args.run_id}")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"============================================================")

    try:
        result = rollback_simple_promo_run(args.run_id)
        print(f"\n✔ 恢复执行完成: {result['message']}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as err:
        print(f"\n❌ 恢复失败: {err}")
        sys.exit(1)
