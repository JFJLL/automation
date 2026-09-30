import datetime
import os
from unittest.mock import patch

from core.schedule_rules import next_run
from core.scheduler_manager import SchedulerManager


def test_schedule_rules_default_hour_minute():
    # 测试 BYHOUR / BYMINUTE 缺省时默认使用 09:00
    base_dt = datetime.datetime(2026, 9, 21, 8, 0, 0) # 2026-09-21 周一 08:00
    res = next_run("FREQ=WORKDAY", base_dt)
    assert res.hour == 9
    assert res.minute == 0
    assert res.date() == datetime.date(2026, 9, 21)

def test_schedule_rules_weekend_skip():
    # 2026-09-25 是周五 20:00，下一个工作日应当跳过周六周日
    base_dt = datetime.datetime(2026, 9, 25, 20, 0, 0)
    res = next_run("FREQ=WORKDAY;BYHOUR=10;BYMINUTE=30", base_dt)
    # 2026-09-26 是周六，2026-09-27 是周日，下一个工作日是 2026-09-28 周一
    assert res.date() == datetime.date(2026, 9, 28)
    assert res.hour == 10
    assert res.minute == 30

def test_scheduler_web_concurrency_guard():
    mgr = SchedulerManager()
    with patch.dict(os.environ, {"WEB_CONCURRENCY": "2"}):
        mgr.start()
        # 多进程下拒绝启动调度器
        assert mgr.scheduler.running is False

def test_scheduler_degraded_status_in_ready():
    mgr = SchedulerManager.get_instance()
    mgr.failed_tasks = [{"module": "sync", "task_id": 999, "error": "mock error"}]
    from apscheduler.schedulers.background import BackgroundScheduler
    with patch.object(BackgroundScheduler, "running", property(lambda self: True)):
        from app.main import readiness_check
        res = readiness_check()
    assert res["status"] == "degraded"
    assert res["failed_tasks_count"] == 1
    mgr.failed_tasks.clear()
