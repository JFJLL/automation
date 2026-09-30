import json
from typing import List, Optional, Tuple

from core.business_time import now_business_tz
from fastapi import HTTPException


def validate_pagination(page: Optional[int], page_size: Optional[int]) -> Tuple[int, int]:
    p = 1 if page is None else page
    ps = 20 if page_size is None else page_size
    if p < 1:
        raise HTTPException(status_code=422, detail="页码必须大于或等于 1")
    if ps < 1 or ps > 100:
        raise HTTPException(status_code=422, detail="每页大小必须在 1 到 100 之间")
    return p, ps

def append_keywords_to_task_repo(
    conn,
    table_name: str,
    task_id: int,
    new_keywords: List[str]
) -> List[str]:
    with conn:
        cur = conn.cursor()
        cur.execute(f"SELECT keywords_json FROM {table_name} WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        existing_kws = json.loads(row[0]) if row[0] else []
        seen = set(existing_kws)
        updated_kws = list(existing_kws)
        for kw in new_keywords:
            k = str(kw).strip()
            if k and k not in seen:
                seen.add(k)
                updated_kws.append(k)

        if len(updated_kws) > 5000:
            raise HTTPException(status_code=400, detail="关键词总数不得超过 5000 个")

        now_str = now_business_tz().isoformat()
        cur.execute(
            f"UPDATE {table_name} SET keywords_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(updated_kws, ensure_ascii=False), now_str, task_id)
        )
        return updated_kws

def remove_keywords_from_task_repo(
    conn,
    table_name: str,
    task_id: int,
    keywords_to_remove: List[str]
) -> List[str]:
    with conn:
        cur = conn.cursor()
        cur.execute(f"SELECT keywords_json, removed_keywords_json FROM {table_name} WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        existing_kws = json.loads(row[0]) if row[0] else []
        removed_kws = json.loads(row[1]) if row[1] else []

        to_remove_set = set(k.strip() for k in keywords_to_remove if k.strip())
        remaining = [k for k in existing_kws if k not in to_remove_set]

        # Record into removed_keywords
        seen_removed = set(removed_kws)
        for k in to_remove_set:
            if k not in seen_removed:
                removed_kws.append(k)
                seen_removed.add(k)

        now_str = now_business_tz().isoformat()
        cur.execute(
            f"UPDATE {table_name} SET keywords_json = ?, removed_keywords_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(remaining, ensure_ascii=False), json.dumps(removed_kws, ensure_ascii=False), now_str, task_id)
        )
        return remaining

def soft_delete_task_repo(conn, table_name: str, task_id: int) -> bool:
    with conn:
        cur = conn.cursor()
        cur.execute(f"SELECT status FROM {table_name} WHERE id = ?", (task_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Task not found")
        now_str = now_business_tz().isoformat()
        cur.execute(
            f"UPDATE {table_name} SET status = 'archived', updated_at = ? WHERE id = ?",
            (now_str, task_id)
        )
        return True
