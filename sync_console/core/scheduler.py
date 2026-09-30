from datetime import datetime
from typing import Optional

from core.scheduler_manager import SchedulerManager

scheduler = SchedulerManager.get_instance().scheduler

def parse_next_run(rrule_str: str, after_dt: Optional[datetime] = None) -> datetime:
    return SchedulerManager.get_instance().parse_sync_next_run(rrule_str, after_dt)

def reschedule_task(task_id: int):
    SchedulerManager.get_instance().schedule_sync_task(task_id)

def remove_job(task_id: int):
    SchedulerManager.get_instance().remove_sync_task(task_id)

def init_scheduler():
    SchedulerManager.get_instance().start()
