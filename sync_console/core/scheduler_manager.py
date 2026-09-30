import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import TIMEZONE
from app.db import get_db
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from core.business_time import now_business_tz
from core.schedule_rules import next_run
from dateutil.tz import gettz

from keyword_service.db import get_db as get_kw_db
from lingxi_service.db import get_db as get_lingxi_db

tz = gettz(TIMEZONE)

class SchedulerManager:
    _instance: Optional["SchedulerManager"] = None

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=tz)
        self._started = False
        self.failed_tasks: List[Dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> "SchedulerManager":
        if cls._instance is None:
            cls._instance = SchedulerManager()
        return cls._instance

    def start(self):
        # 检查多进程启动配置
        concurrency = int(os.getenv("WEB_CONCURRENCY", 0) or os.getenv("WORKERS", 0) or 1)
        if concurrency > 1:
            print("[SchedulerManager] Warning: WEB_CONCURRENCY / WORKERS > 1 detected. Refusing to run multiple schedulers to prevent race conditions.")
            return

        if not self.scheduler.running:
            self.scheduler.start()
            self._started = True
            print("[SchedulerManager] Unified APScheduler started.")
            self.restore_all_tasks()

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            self._started = False
            print("[SchedulerManager] Unified APScheduler shut down.")

    def parse_sync_next_run(self, rrule_str: str, after_dt: Optional[datetime] = None) -> datetime:
        return next_run(rrule_str, after_dt)

    def parse_kw_next_run(self, rrule_str: str, after_dt: Optional[datetime] = None) -> datetime:
        return next_run(rrule_str, after_dt)

    def schedule_sync_task(self, task_id: int):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, rrule, status FROM tasks WHERE id = ?", (task_id,))
            task = cursor.fetchone()
            if not task or task["status"] != "active":
                self.remove_sync_task(task_id)
                return

            now = now_business_tz()
            next_dt = self.parse_sync_next_run(task["rrule"], now)
            next_iso = next_dt.isoformat()

            cursor.execute("UPDATE tasks SET next_run_at = ?, updated_at = ? WHERE id = ?", (next_iso, now.isoformat(), task_id))
            conn.commit()

            job_id = f"sync_task_{task_id}"
            try:
                self.scheduler.remove_job(job_id)
            except JobLookupError:
                pass

            self.scheduler.add_job(
                _run_sync_task_job,
                trigger="date",
                run_date=next_dt,
                args=[task_id],
                id=job_id,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
                replace_existing=True
            )

    def remove_sync_task(self, task_id: int):
        job_id = f"sync_task_{task_id}"
        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError:
            pass

    def schedule_keyword_task(self, task_id: int):
        with get_kw_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, rrule, status FROM keyword_tasks WHERE id = ?", (task_id,))
            task = cursor.fetchone()
            if not task or task["status"] != "active":
                self.remove_keyword_task(task_id)
                return

            now = now_business_tz()
            next_dt = self.parse_kw_next_run(task["rrule"], now)
            next_iso = next_dt.isoformat()

            cursor.execute("UPDATE keyword_tasks SET next_run_at = ?, updated_at = ? WHERE id = ?", (next_iso, now.isoformat(), task_id))
            conn.commit()

            job_id = f"kw_task_{task_id}"
            try:
                self.scheduler.remove_job(job_id)
            except JobLookupError:
                pass

            self.scheduler.add_job(
                _run_keyword_task_job,
                trigger="date",
                run_date=next_dt,
                args=[task_id],
                id=job_id,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
                replace_existing=True
            )

    def remove_keyword_task(self, task_id: int):
        job_id = f"kw_task_{task_id}"
        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError:
            pass

    def schedule_lingxi_task(self, task_id: int):
        with get_lingxi_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, rrule, status FROM lingxi_tasks WHERE id = ?", (task_id,))
            task = cursor.fetchone()
            if not task or task["status"] != "active":
                self.remove_lingxi_task(task_id)
                return

            now = now_business_tz()
            next_dt = self.parse_kw_next_run(task["rrule"], now)
            next_iso = next_dt.isoformat()

            cursor.execute("UPDATE lingxi_tasks SET next_run_at = ?, updated_at = ? WHERE id = ?", (next_iso, now.isoformat(), task_id))
            conn.commit()

            job_id = f"lingxi_task_{task_id}"
            try:
                self.scheduler.remove_job(job_id)
            except JobLookupError:
                pass

            self.scheduler.add_job(
                _run_lingxi_task_job,
                trigger="date",
                run_date=next_dt,
                args=[task_id],
                id=job_id,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
                replace_existing=True
            )

    def remove_lingxi_task(self, task_id: int):
        job_id = f"lingxi_task_{task_id}"
        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError:
            pass

    def restore_all_tasks(self):
        self.failed_tasks.clear()
        now = now_business_tz()
        now_iso = now.isoformat()
        missed_policy = os.getenv("MISSED_RUN_POLICY", "run_once").lower()

        # 1. 恢复主数据同步任务
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, next_run_at, last_run_at FROM tasks WHERE status = 'active'")
            for r in cursor.fetchall():
                task_id = r["id"]
                try:
                    self.schedule_sync_task(task_id)
                    # 错失运行判定
                    next_run_at = r["next_run_at"]
                    last_run_at = r["last_run_at"]
                    if next_run_at and next_run_at < now_iso and (not last_run_at or last_run_at < next_run_at):
                        if missed_policy == "run_once":
                            self.scheduler.add_job(
                                _run_sync_task_job,
                                trigger="date",
                                run_date=now,
                                args=[task_id],
                                id=f"missed_sync_{task_id}",
                                misfire_grace_time=3600,
                                coalesce=True,
                                max_instances=1,
                                replace_existing=True
                            )
                except Exception as e:
                    self.failed_tasks.append({"module": "sync", "task_id": task_id, "error": str(e)})
                    print(f"[SchedulerManager] Schedule sync task {task_id} error: {e}")

        # 2. 恢复关键词同步任务
        with get_kw_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, next_run_at, last_run_at FROM keyword_tasks WHERE status = 'active'")
            for r in cursor.fetchall():
                task_id = r["id"]
                try:
                    self.schedule_keyword_task(task_id)
                    next_run_at = r["next_run_at"]
                    last_run_at = r["last_run_at"]
                    if next_run_at and next_run_at < now_iso and (not last_run_at or last_run_at < next_run_at):
                        if missed_policy == "run_once":
                            self.scheduler.add_job(
                                _run_keyword_task_job,
                                trigger="date",
                                run_date=now,
                                args=[task_id],
                                id=f"missed_kw_{task_id}",
                                misfire_grace_time=3600,
                                coalesce=True,
                                max_instances=1,
                                replace_existing=True
                            )
                except Exception as e:
                    self.failed_tasks.append({"module": "keyword", "task_id": task_id, "error": str(e)})
                    print(f"[SchedulerManager] Schedule kw task {task_id} error: {e}")

        # 3. 恢复灵犀关键词同步任务
        with get_lingxi_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, next_run_at, last_run_at FROM lingxi_tasks WHERE status = 'active'")
            for r in cursor.fetchall():
                task_id = r["id"]
                try:
                    self.schedule_lingxi_task(task_id)
                    next_run_at = r["next_run_at"]
                    last_run_at = r["last_run_at"]
                    if next_run_at and next_run_at < now_iso and (not last_run_at or last_run_at < next_run_at):
                        if missed_policy == "run_once":
                            self.scheduler.add_job(
                                _run_lingxi_task_job,
                                trigger="date",
                                run_date=now,
                                args=[task_id],
                                id=f"missed_lingxi_{task_id}",
                                misfire_grace_time=3600,
                                coalesce=True,
                                max_instances=1,
                                replace_existing=True
                            )
                except Exception as e:
                    self.failed_tasks.append({"module": "lingxi", "task_id": task_id, "error": str(e)})
                    print(f"[SchedulerManager] Schedule lingxi task {task_id} error: {e}")

def _run_sync_task_job(task_id: int):
    from core.sync import execute_task_sync
    mgr = SchedulerManager.get_instance()
    try:
        execute_task_sync(task_id, trigger_type="scheduled")
    except Exception as e:
        print(f"[Scheduler] Run scheduled sync task {task_id} error: {e}")
    finally:
        mgr.schedule_sync_task(task_id)

def _run_keyword_task_job(task_id: int):
    from keyword_service.client import sync_token_from_oss
    from keyword_service.sync_engine import run_keyword_task
    mgr = SchedulerManager.get_instance()
    try:
        sync_token_from_oss()
    except Exception:
        pass
    try:
        run_keyword_task(task_id, trigger_type="scheduled")
    except Exception as e:
        print(f"[Scheduler] Run scheduled kw task {task_id} error: {e}")
    finally:
        mgr.schedule_keyword_task(task_id)

def _run_lingxi_task_job(task_id: int):
    from lingxi_service.client import sync_token_from_oss
    from lingxi_service.sync_engine import run_lingxi_task
    mgr = SchedulerManager.get_instance()
    try:
        sync_token_from_oss()
    except Exception:
        pass
    try:
        run_lingxi_task(task_id, trigger_type="scheduled")
    except Exception as e:
        print(f"[Scheduler] Run scheduled lingxi task {task_id} error: {e}")
    finally:
        mgr.schedule_lingxi_task(task_id)
