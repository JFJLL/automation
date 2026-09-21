import time
from datetime import datetime, timedelta, time as dtime
from dateutil import rrule
from dateutil.tz import gettz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError

from app.config import TIMEZONE
from app.db import get_db
from core.sync import execute_task_sync
from core.workdays import is_china_workday

tz = gettz(TIMEZONE)
scheduler = BackgroundScheduler(timezone=tz)

def parse_next_run(rrule_str: str, after_dt: datetime = None) -> datetime:
    if after_dt is None:
        after_dt = datetime.now(tz)
    elif after_dt.tzinfo is None:
        after_dt = after_dt.replace(tzinfo=tz)
        
    clean_str = rrule_str.strip()
    if clean_str.startswith("RRULE:"):
        clean_str = clean_str[6:]

    # 特殊处理法定工作日模式 (含调休补班)
    if "WORKDAY=TRUE" in clean_str or "FREQ=WORKDAY" in clean_str:
        # 解析设定的小时和分钟
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
        # 如果当前日期的目标时间还没过，且今天就是法定工作日
        today_target = cand.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if cand < today_target and is_china_workday(cand.date()):
            return today_target

        # 否则向后寻找下一个法定工作日
        curr_date = cand.date() + timedelta(days=1)
        for _ in range(60): # 最多向前看60天
            if is_china_workday(curr_date):
                next_run = datetime.combine(curr_date, dtime(hour=hour, minute=minute)).replace(tzinfo=tz)
                return next_run
            curr_date += timedelta(days=1)
        return after_dt + timedelta(days=1)

    # 普通标准 RRULE 处理
    rule = rrule.rrulestr(clean_str, dtstart=after_dt)
    next_dt = rule.after(after_dt)
    if next_dt:
        return next_dt.astimezone(tz)
    return after_dt + timedelta(days=1)

def run_task_job(task_id: int):
    now = datetime.now(tz)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT rrule FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()

    # 如果是法定工作日任务，且当前不是法定工作日（双保险），则跳过并重新调度
    if task and ("WORKDAY=TRUE" in task["rrule"] or "FREQ=WORKDAY" in task["rrule"]):
        if not is_china_workday(now.date()):
            print(f"[{now.isoformat()}] Today {now.date()} is not a statutory workday, skipping task {task_id}")
            reschedule_task(task_id)
            return

    print(f"[{now.isoformat()}] Starting scheduled sync for task {task_id}")
    try:
        execute_task_sync(task_id, trigger_type="scheduled")
    except Exception as e:
        print(f"Error running scheduled task {task_id}: {e}")
    finally:
        reschedule_task(task_id)

def reschedule_task(task_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, rrule, status FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task or task["status"] != "active":
            remove_job(task_id)
            return
            
        now = datetime.now(tz)
        next_dt = parse_next_run(task["rrule"], now)
        next_iso = next_dt.isoformat()
        
        cursor.execute("UPDATE tasks SET next_run_at = ?, updated_at = ? WHERE id = ?", (next_iso, now.isoformat(), task_id))
        conn.commit()
        
        job_id = f"task_{task_id}"
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass
        scheduler.add_job(
            run_task_job,
            trigger="date",
            run_date=next_dt,
            args=[task_id],
            id=job_id,
            replace_existing=True
        )
        print(f"Task {task_id} scheduled for next run at {next_iso}")

def remove_job(task_id: int):
    job_id = f"task_{task_id}"
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass

def init_scheduler():
    if not scheduler.running:
        scheduler.start()
    print("APScheduler started.")
    
    now = datetime.now(tz)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, rrule, next_run_at, status FROM tasks WHERE status = 'active'")
        tasks = cursor.fetchall()
        for t in tasks:
            tid = t["id"]
            next_str = t["next_run_at"]
            if next_str:
                try:
                    next_dt = datetime.fromisoformat(next_str)
                    if next_dt.tzinfo is None:
                        next_dt = next_dt.replace(tzinfo=tz)
                    if next_dt < now:
                        if now - next_dt <= timedelta(hours=2):
                            # 节假日不补跑
                            if ("WORKDAY=TRUE" in t["rrule"] or "FREQ=WORKDAY" in t["rrule"]) and not is_china_workday(next_dt.date()):
                                pass
                            else:
                                print(f"Task {tid} ({t['name']}) missed run at {next_str}, triggering catch-up...")
                                try:
                                    execute_task_sync(tid, trigger_type="catch_up")
                                except Exception as e:
                                    print(f"Catch-up failed for task {tid}: {e}")
                except Exception as e:
                    print(f"Failed parsing next_run_at for task {tid}: {e}")
            reschedule_task(tid)
