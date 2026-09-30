import time
from datetime import datetime, timedelta, time as dtime
from typing import Optional
from dateutil import rrule
from dateutil.tz import gettz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError

from app.config import TIMEZONE
from app.db import get_db
from keyword_service.db import get_db as get_kw_db
from lingxi_service.db import get_db as get_lingxi_db
from core.workdays import is_china_workday

tz = gettz(TIMEZONE)

class SchedulerManager:
    _instance: Optional["SchedulerManager"] = None

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=tz)
        self._started = False

    @classmethod
    def get_instance(cls) -> "SchedulerManager":
        if cls._instance is None:
            cls._instance = SchedulerManager()
        return cls._instance

    def start(self):
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
        if after_dt is None:
            after_dt = datetime.now(tz)
        elif after_dt.tzinfo is None:
            after_dt = after_dt.replace(tzinfo=tz)
            
        clean_str = rrule_str.strip()
        if clean_str.startswith("RRULE:"):
            clean_str = clean_str[6:]

        if "WORKDAY=TRUE" in clean_str or "FREQ=WORKDAY" in clean_str:
            hour = 9
            minute = 0
            for part in clean_str.split(";"):
                if part.startswith("BYHOUR="):
                    try: hour = int(part.split("=")[1])
                    except Exception: pass
                elif part.startswith("BYMINUTE="):
                    try: minute = int(part.split("=")[1])
                    except Exception: pass

            cand = after_dt
            today_target = cand.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if cand < today_target and is_china_workday(cand.date()):
                return today_target

            curr_date = cand.date() + timedelta(days=1)
            for _ in range(60):
                if is_china_workday(curr_date):
                    return datetime.combine(curr_date, dtime(hour=hour, minute=minute)).replace(tzinfo=tz)
                curr_date += timedelta(days=1)
            return after_dt + timedelta(days=1)

        rule = rrule.rrulestr(clean_str, dtstart=after_dt)
        next_dt = rule.after(after_dt)
        if next_dt:
            return next_dt.astimezone(tz)
        return after_dt + timedelta(days=1)

    def parse_kw_next_run(self, rrule_str: str, after_dt: Optional[datetime] = None) -> datetime:
        if after_dt is None:
            after_dt = datetime.now(tz)
        elif after_dt.tzinfo is None:
            after_dt = after_dt.replace(tzinfo=tz)
            
        clean_str = rrule_str.strip()
        if clean_str.startswith("RRULE:"):
            clean_str = clean_str[6:]

        rule = rrule.rrulestr(clean_str, dtstart=after_dt)
        next_dt = rule.after(after_dt)
        if next_dt:
            return next_dt.astimezone(tz)
        return after_dt + timedelta(days=1)

    def schedule_sync_task(self, task_id: int):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, rrule, status FROM tasks WHERE id = ?", (task_id,))
            task = cursor.fetchone()
            if not task or task["status"] != "active":
                self.remove_sync_task(task_id)
                return
                
            now = datetime.now(tz)
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
                
            now = datetime.now(tz)
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
                
            now = datetime.now(tz)
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
                replace_existing=True
            )

    def remove_lingxi_task(self, task_id: int):
        job_id = f"lingxi_task_{task_id}"
        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError:
            pass

    def restore_all_tasks(self):
        # 1. 恢复主数据同步任务
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tasks WHERE status = 'active'")
            for r in cursor.fetchall():
                try:
                    self.schedule_sync_task(r["id"])
                except Exception as e:
                    print(f"[SchedulerManager] Schedule sync task {r['id']} error: {e}")
                    
        # 2. 恢复关键词同步任务
        with get_kw_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM keyword_tasks WHERE status = 'active'")
            for r in cursor.fetchall():
                try:
                    self.schedule_keyword_task(r["id"])
                except Exception as e:
                    print(f"[SchedulerManager] Schedule kw task {r['id']} error: {e}")

        # 3. 恢复灵犀关键词同步任务
        with get_lingxi_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM lingxi_tasks WHERE status = 'active'")
            for r in cursor.fetchall():
                try:
                    self.schedule_lingxi_task(r['id'])
                except Exception as e:
                    print(f"[SchedulerManager] Schedule lingxi task {r['id']} error: {e}")

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
    from keyword_service.sync_engine import run_keyword_task
    from keyword_service.client import sync_token_from_oss
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
    from lingxi_service.sync_engine import run_lingxi_task
    from lingxi_service.client import sync_token_from_oss
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

