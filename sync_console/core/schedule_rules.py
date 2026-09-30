import datetime
from datetime import time as dtime
from datetime import timedelta
from typing import Optional

from app.config import TIMEZONE
from core.workdays import is_china_workday
from dateutil import rrule
from dateutil.tz import gettz

tz = gettz(TIMEZONE)

def next_run(rule_str: str, after_dt: Optional[datetime.datetime] = None) -> datetime.datetime:
    """
    纯函数：计算 RRULE 或 WORKDAY 规则在 after_dt 之后的下一次执行时间
    """
    if after_dt is None:
        after_dt = datetime.datetime.now(tz)
    elif after_dt.tzinfo is None:
        after_dt = after_dt.replace(tzinfo=tz)

    clean_str = rule_str.strip()
    if clean_str.startswith("RRULE:"):
        clean_str = clean_str[6:]

    if "WORKDAY=TRUE" in clean_str or "FREQ=WORKDAY" in clean_str:
        hour = 9
        minute = 0
        for part in clean_str.split(";"):
            if part.startswith("BYHOUR="):
                try:
                    hour = int(part.split("=")[1])
                except Exception:
                    pass
            elif part.startswith("BYMINUTE="):
                try:
                    minute = int(part.split("=")[1])
                except Exception:
                    pass

        today_target = after_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if after_dt < today_target and is_china_workday(after_dt.date()):
            return today_target

        curr_date = after_dt.date() + timedelta(days=1)
        for _ in range(60):
            if is_china_workday(curr_date):
                return datetime.datetime.combine(curr_date, dtime(hour=hour, minute=minute)).replace(tzinfo=tz)
            curr_date += timedelta(days=1)
        return after_dt + timedelta(days=1)

    rule = rrule.rrulestr(clean_str, dtstart=after_dt)
    next_dt = rule.after(after_dt)
    if next_dt:
        return next_dt.astimezone(tz)
    return after_dt + timedelta(days=1)
