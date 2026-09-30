from datetime import datetime
from typing import Optional

from core.scheduler_manager import SchedulerManager

kw_scheduler = SchedulerManager.get_instance().scheduler

def parse_next_run(rrule_str: str, after_dt: Optional[datetime] = None) -> datetime:
    return SchedulerManager.get_instance().parse_kw_next_run(rrule_str, after_dt)

def reschedule_keyword_task(task_id: int):
    SchedulerManager.get_instance().schedule_keyword_task(task_id)

def remove_keyword_job(task_id: int):
    SchedulerManager.get_instance().remove_keyword_task(task_id)

def init_keyword_scheduler():
    SchedulerManager.get_instance().start()

