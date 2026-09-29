import time
from datetime import datetime, timedelta
from dateutil import rrule
from dateutil.tz import gettz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError

from keyword_service.db import get_db

tz = gettz("Asia/Shanghai")
kw_scheduler = BackgroundScheduler(timezone=tz)

def parse_next_run(rrule_str: str, after_dt: datetime = None) -> datetime:
    if after_dt is None:
        after_dt = datetime.now(tz)
    elif after_dt.tzinfo is None:
        after_dt = after_dt.replace(tzinfo=tz)
        
    clean_str = rrule_str.strip()
    if clean_str.startswith("RRULE:"):
        clean_str = clean_str[6:]

    try:
        rule = rrule.rrulestr(clean_str, dtstart=after_dt)
        next_dt = rule.after(after_dt)
        if next_dt:
            return next_dt.astimezone(tz)
    except Exception as e:
        print(f"Error parsing rrule {rrule_str}: {e}")
    return after_dt + timedelta(days=1)

def run_keyword_job(task_id: int):
    from keyword_service.sync_engine import run_keyword_task
    try:
        from keyword_service.client import sync_token_from_oss
        sync_token_from_oss()
    except Exception as e:
        print(f"[Scheduler] Auto-sync token from OSS warning: {e}")
    try:
        run_keyword_task(task_id, trigger_type="scheduled")
    except Exception as e:
        print(f"[Scheduler] Run keyword task #{task_id} failed: {e}")
    finally:
        reschedule_keyword_task(task_id)

def reschedule_keyword_task(task_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, rrule, status FROM keyword_tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        
    job_id = f"kw_task_{task_id}"
    try:
        kw_scheduler.remove_job(job_id)
    except JobLookupError:
        pass
        
    if not task or task["status"] != "active":
        with get_db() as conn:
            conn.execute("UPDATE keyword_tasks SET next_run_at = NULL WHERE id = ?", (task_id,))
            conn.commit()
        return

    next_run = parse_next_run(task["rrule"])
    with get_db() as conn:
        conn.execute("UPDATE keyword_tasks SET next_run_at = ? WHERE id = ?", (next_run.isoformat(), task_id))
        conn.commit()

    kw_scheduler.add_job(
        run_keyword_job,
        'date',
        run_date=next_run,
        args=[task_id],
        id=job_id,
        replace_existing=True
    )
    print(f"[Scheduler] Rescheduled keyword task #{task_id} at {next_run}")

def remove_keyword_job(task_id: int):
    job_id = f"kw_task_{task_id}"
    try:
        kw_scheduler.remove_job(job_id)
    except JobLookupError:
        pass

def init_keyword_scheduler():
    if not kw_scheduler.running:
        kw_scheduler.start()
        print("[Scheduler] Keyword scheduler started.")
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM keyword_tasks WHERE status = 'active'")
        for r in cursor.fetchall():
            reschedule_keyword_task(r["id"])

