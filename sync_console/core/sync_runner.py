import json
import secrets
from typing import List, Optional

from core.business_time import now_business_tz
from core.database import acquire_task_lease, release_task_lease, renew_task_lease
from core.errors import TaskAlreadyRunningError


class TaskRunGuard:
    def __init__(
        self,
        conn,
        task_key: str,
        task_id: int,
        module: str = "sync",
        trigger_type: str = "scheduled",
        lease_seconds: int = 600,
        task_name: str = "",
        keywords_count: int = 0
    ):
        self.conn = conn
        self.task_key = task_key
        self.task_id = task_id
        self.module = module
        self.trigger_type = trigger_type
        self.lease_seconds = lease_seconds
        self.task_name = task_name or f"Task_{task_id}"
        self.keywords_count = keywords_count
        self.owner = secrets.token_hex(16)
        self.run_id: Optional[int] = None
        self.start_dt = None
        self.finished = False

    def __enter__(self):
        acquired = acquire_task_lease(
            self.conn,
            self.task_key,
            owner=self.owner,
            lease_seconds=self.lease_seconds
        )
        if not acquired:
            raise TaskAlreadyRunningError(f"Task [{self.task_key}] is currently running by another worker.")

        self.start_dt = now_business_tz()
        start_iso = self.start_dt.isoformat()

        with self.conn:
            cur = self.conn.cursor()
            if self.module == "sync":
                cur.execute(
                    """
                    INSERT INTO runs (
                        task_id, trigger_type, started_at, status, rows_fetched,
                        rows_appended, rows_updated, message
                    ) VALUES (?, ?, ?, 'running', 0, 0, 0, '执行中...')
                    """,
                    (self.task_id, self.trigger_type, start_iso)
                )
            elif self.module == "keyword":
                cur.execute(
                    """
                    INSERT INTO keyword_runs (
                        task_id, task_name, trigger_type, started_at, status,
                        keywords_count, days_count, message
                    ) VALUES (?, ?, ?, ?, 'running', ?, 0, '执行中...')
                    """,
                    (self.task_id, self.task_name, self.trigger_type, start_iso, self.keywords_count)
                )
            elif self.module == "lingxi":
                cur.execute(
                    """
                    INSERT INTO lingxi_runs (
                        task_id, task_name, trigger_type, started_at, status,
                        keywords_count, message
                    ) VALUES (?, ?, ?, ?, 'running', ?, '执行中...')
                    """,
                    (self.task_id, self.task_name, self.trigger_type, start_iso, self.keywords_count)
                )
            self.run_id = cur.lastrowid
        return self

    def renew(self) -> None:
        ok = renew_task_lease(
            self.conn,
            self.task_key,
            owner=self.owner,
            lease_seconds=self.lease_seconds
        )
        if not ok:
            raise RuntimeError(f"Lease renewal failed for task [{self.task_key}]; lease lost.")

    def finish_run(
        self,
        status: str,
        message: str = "",
        error_detail: Optional[str] = None,
        rows_fetched: int = 0,
        rows_appended: int = 0,
        rows_updated: int = 0,
        days_count: int = 0,
        successful_keywords: Optional[List[str]] = None,
        failed_keywords: Optional[List[str]] = None,
        provider_status: str = "ok",
        rollback_status: Optional[str] = None,
        **kwargs
    ):
        if self.finished or not self.run_id:
            return
        self.finished = True
        end_dt = now_business_tz()
        end_iso = end_dt.isoformat()
        duration_ms = int((end_dt - self.start_dt).total_seconds() * 1000) if self.start_dt else 0

        succ_json = json.dumps(successful_keywords or [], ensure_ascii=False)
        fail_json = json.dumps(failed_keywords or [], ensure_ascii=False)

        with self.conn:
            cur = self.conn.cursor()
            if self.module == "sync":
                cur.execute(
                    """
                    UPDATE runs SET
                        finished_at = ?, status = ?, rows_fetched = ?,
                        rows_appended = ?, rows_updated = ?, message = ?,
                        error_detail = ?, duration_ms = ?, provider_status = ?,
                        rollback_status = ?
                    WHERE id = ?
                    """,
                    (
                        end_iso, status, rows_fetched, rows_appended,
                        rows_updated, message, error_detail, duration_ms,
                        provider_status, rollback_status, self.run_id
                    )
                )
                cur.execute(
                    "UPDATE tasks SET last_run_at = ?, last_status = ?, last_error = ?, updated_at = ? WHERE id = ?",
                    (end_iso, status, error_detail or "", end_iso, self.task_id)
                )
            elif self.module == "keyword":
                cur.execute(
                    """
                    UPDATE keyword_runs SET
                        finished_at = ?, status = ?, duration_ms = ?, message = ?,
                        error_detail = ?, days_count = ?, successful_keywords = ?,
                        failed_keywords = ?
                    WHERE id = ?
                    """,
                    (
                        end_iso, status, duration_ms, message,
                        error_detail, days_count, succ_json,
                        fail_json, self.run_id
                    )
                )
                cur.execute(
                    "UPDATE keyword_tasks SET last_run_at = ?, last_status = ?, updated_at = ? WHERE id = ?",
                    (end_iso, status, end_iso, self.task_id)
                )
            elif self.module == "lingxi":
                cur.execute(
                    """
                    UPDATE lingxi_runs SET
                        finished_at = ?, status = ?, duration_ms = ?, message = ?,
                        error_detail = ?, successful_keywords = ?, failed_keywords = ?
                    WHERE id = ?
                    """,
                    (
                        end_iso, status, duration_ms, message,
                        error_detail, succ_json, fail_json,
                        self.run_id
                    )
                )
                cur.execute(
                    "UPDATE lingxi_tasks SET last_run_at = ?, last_status = ?, updated_at = ? WHERE id = ?",
                    (end_iso, status, end_iso, self.task_id)
                )

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type and not self.finished and self.run_id:
                err_msg = str(exc_val)
                self.finish_run(status="failed", message=err_msg[:200], error_detail=err_msg)
        finally:
            release_task_lease(self.conn, self.task_key, owner=self.owner)
