import zoneinfo
from datetime import date, datetime

import pytest
from core.business_time import (
    latest_keyword_available_date,
    latest_sync_cutoff_date,
    validate_keyword_date_range,
)
from core.errors import InvalidDateRangeError


def test_business_time_before_12():
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    dt = datetime(2026, 9, 30, 11, 59, 59, tzinfo=tz)
    avail = latest_keyword_available_date(dt)
    assert avail == date(2026, 9, 28), "12:00 前应返回 T-2"

def test_business_time_at_12():
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    dt = datetime(2026, 9, 30, 12, 0, 0, tzinfo=tz)
    avail = latest_keyword_available_date(dt)
    assert avail == date(2026, 9, 29), "12:00 起应返回 T-1"

def test_business_time_after_12():
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    dt = datetime(2026, 9, 30, 12, 1, 0, tzinfo=tz)
    avail = latest_keyword_available_date(dt)
    assert avail == date(2026, 9, 29), "12:00 后应返回 T-1"

def test_date_range_90_days():
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    dt = datetime(2026, 9, 30, 14, 0, 0, tzinfo=tz) # T-1 is 2026-09-29
    # Exactly 90 days: 2026-07-02 to 2026-09-29 is 90 days
    s, e, dates = validate_keyword_date_range(start_date="2026-07-02", end_date="2026-09-29", now=dt)
    assert len(dates) == 90
    assert s == "2026-07-02"
    assert e == "2026-09-29"

def test_date_range_91_days_rejected():
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    dt = datetime(2026, 9, 30, 14, 0, 0, tzinfo=tz)
    # 91 days: 2026-07-01 to 2026-09-29
    with pytest.raises(InvalidDateRangeError) as exc_info:
        validate_keyword_date_range(start_date="2026-07-01", end_date="2026-09-29", now=dt)
    assert "不能超过 90 天" in str(exc_info.value)

def test_date_range_start_after_end():
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    dt = datetime(2026, 9, 30, 14, 0, 0, tzinfo=tz)
    with pytest.raises(InvalidDateRangeError) as exc_info:
        validate_keyword_date_range(start_date="2026-09-29", end_date="2026-09-20", now=dt)
    assert "不能大于结束日期" in str(exc_info.value)

def test_date_range_future_date_rejected():
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    # At 11:30, max available is 2026-09-28 (T-2)
    dt = datetime(2026, 9, 30, 11, 30, 0, tzinfo=tz)
    with pytest.raises(InvalidDateRangeError) as exc_info:
        validate_keyword_date_range(start_date="2026-09-20", end_date="2026-09-29", now=dt)
    assert "超过当前最新可用日期" in str(exc_info.value)

def test_latest_sync_cutoff_date():
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    dt_morning = datetime(2026, 9, 30, 10, 0, 0, tzinfo=tz)
    assert latest_sync_cutoff_date(now=dt_morning) == "2026-09-28"
    dt_afternoon = datetime(2026, 9, 30, 15, 0, 0, tzinfo=tz)
    assert latest_sync_cutoff_date(now=dt_afternoon) == "2026-09-29"
