import os
import zoneinfo
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

DEFAULT_TIMEZONE_NAME = os.getenv("TIMEZONE", "Asia/Shanghai")

def get_business_tz() -> zoneinfo.ZoneInfo:
    tz_name = os.getenv("TIMEZONE", DEFAULT_TIMEZONE_NAME)
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return zoneinfo.ZoneInfo("Asia/Shanghai")

def now_business_tz() -> datetime:
    return datetime.now(get_business_tz())

def latest_keyword_available_date(now: Optional[datetime] = None) -> date:
    """
    业务规则：
    北京时间中午 12:00 前：最新支持 T-2
    北京时间中午 12:00 起：最新支持 T-1
    """
    curr = now if now is not None else now_business_tz()
    offset = 1 if curr.hour >= 12 else 2
    return curr.date() - timedelta(days=offset)

def validate_keyword_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    now: Optional[datetime] = None
) -> Tuple[str, str, List[str]]:
    """
    验证关键词查询日期范围：
    1. end_date 默认按当前业务时间最新可用日期
    2. start_date 默认向前 89 天 (共 90 天)
    3. 开始日期不得晚于结束日期
    4. 日期间隔不超过 90 个自然日
    5. 结束日期不得超过业务时间最新可用日期 (中午12点前T-2，12点后T-1)
    """
    from core.errors import InvalidDateRangeError

    max_avail = latest_keyword_available_date(now)

    if not end_date:
        e_date = max_avail
        end_date_str = e_date.isoformat()
    else:
        try:
            e_date = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
            end_date_str = e_date.isoformat()
        except ValueError:
            raise InvalidDateRangeError(f"结束日期格式非法: {end_date}，必须为 YYYY-MM-DD")

    if e_date > max_avail:
        raise InvalidDateRangeError(
            f"结束日期 {end_date_str} 超过当前最新可用日期 {max_avail.isoformat()} (12:00 前支持 T-2，12:00 起支持 T-1)"
        )

    if not start_date:
        s_date = e_date - timedelta(days=89)
        start_date_str = s_date.isoformat()
    else:
        try:
            s_date = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
            start_date_str = s_date.isoformat()
        except ValueError:
            raise InvalidDateRangeError(f"开始日期格式非法: {start_date}，必须为 YYYY-MM-DD")

    if s_date > e_date:
        raise InvalidDateRangeError(f"开始日期 {start_date_str} 不能大于结束日期 {end_date_str}")

    days_count = (e_date - s_date).days + 1
    if days_count > 90:
        raise InvalidDateRangeError(f"查询日期间隔不能超过 90 天 (当前请求 {days_count} 天)")

    # 生成连续日期序列
    dates = []
    curr = s_date
    while curr <= e_date:
        dates.append(curr.isoformat())
        curr += timedelta(days=1)

    return start_date_str, end_date_str, dates

def latest_sync_cutoff_date(platform: Optional[str] = None, now: Optional[datetime] = None) -> str:
    """
    主数据同步 cutoff 截止日期，遵循统一时区规则
    """
    curr = now if now is not None else now_business_tz()
    offset = 1 if curr.hour >= 12 else 2
    return (curr.date() - timedelta(days=offset)).isoformat()
