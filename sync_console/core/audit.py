import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import BACKUPS_DIR


AUDIT_DIR = Path(os.getenv("ADMIN_AUDIT_DIR", str(BACKUPS_DIR / "deletions")))


def save_deletion_audit(
    module: str,
    task_id: int,
    task: Dict[str, Any],
    related_counts: Optional[Dict[str, int]] = None,
) -> Path:
    """Persist a task snapshot before archiving/deleting it.

    Files live outside the database so a later cleanup can never erase the
    evidence of what was removed and when.
    """
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = AUDIT_DIR / f"{module}_task_{task_id}_{stamp}.json"
    payload = {
        "module": module,
        "task_id": task_id,
        "deleted_at": datetime.now().isoformat(),
        "task": task,
        "related_counts": related_counts or {},
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return target


def list_deletion_audits(limit: int = 200) -> List[Dict[str, Any]]:
    """Return newest-first deletion snapshots for the admin audit page."""
    if not AUDIT_DIR.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(AUDIT_DIR.glob("*_task_*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        task = data.get("task") or {}
        rows.append(
            {
                "filename": path.name,
                "module": data.get("module"),
                "task_id": data.get("task_id"),
                "task_name": task.get("name") or task.get("task_name"),
                "platform": task.get("platform"),
                "rrule": task.get("rrule"),
                "deleted_at": data.get("deleted_at"),
                "related_counts": data.get("related_counts") or {},
            }
        )
    return rows
