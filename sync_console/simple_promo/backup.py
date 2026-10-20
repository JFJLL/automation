# -*- coding: utf-8 -*-
import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.config import BASE_DIR

PROMO_BACKUP_DIR = BASE_DIR / "backups" / "simple_promo"
PROMO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def save_promo_execution_snapshot(
    run_id: int,
    task_id: Optional[int],
    task_name: str,
    mode: str,
    cutoff_date: str,
    accounts_summary: Dict[str, Any],
    paused_items: List[Dict[str, Any]],
    action_type: str = "PAUSE_EXECUTION"
) -> Path:
    """
    持久化保存简单投写操作（暂停/恢复）的本地不可篡改快照备份。
    即使前端页面或数据库任务被删除，该本地快照永远保留在磁盘上以供回溯与一键恢复。
    """
    PROMO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp_str}_{action_type}_run_{run_id}.json"
    filepath = PROMO_BACKUP_DIR / filename

    snapshot_data = {
        "backup_id": f"backup_{timestamp_str}_{action_type.lower()}_{run_id}",
        "operation": action_type,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": run_id,
        "task_id": task_id,
        "task_name": task_name,
        "mode": mode,
        "cutoff_date": cutoff_date,
        "total_items": len(paused_items),
        "accounts_summary": accounts_summary,
        "items": paused_items
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)

    return filepath

def save_task_backup(task_id: int, task_data: Dict[str, Any], reason: str = "DELETED") -> Path:
    """
    当任务被修改或删除时，在本地持久化归档该任务的完整配置，防止误删后无法恢复。
    """
    PROMO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp_str}_TASK_{reason}_id_{task_id}.json"
    filepath = PROMO_BACKUP_DIR / filename

    archive_data = {
        "backup_id": f"task_archive_{timestamp_str}_{task_id}",
        "action": reason,
        "archived_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "task_id": task_id,
        "task": task_data
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(archive_data, f, ensure_ascii=False, indent=2)

    return filepath

def list_promo_backups() -> List[Dict[str, Any]]:
    """列出所有本地持久化备份快照"""
    if not PROMO_BACKUP_DIR.exists():
        return []
    results = []
    for p in sorted(PROMO_BACKUP_DIR.glob("*.json"), reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                results.append({
                    "filename": p.name,
                    "filepath": str(p),
                    "operation": data.get("operation") or data.get("action"),
                    "created_at": data.get("created_at") or data.get("archived_at"),
                    "run_id": data.get("run_id"),
                    "task_name": data.get("task_name") or data.get("task", {}).get("name"),
                    "total_items": data.get("total_items", 0)
                })
        except Exception:
            continue
    return results
