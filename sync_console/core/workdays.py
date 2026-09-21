import datetime
from typing import Optional
from dateutil.tz import gettz

try:
    import chinese_calendar as calendar
    HAS_CHINESE_CALENDAR = True
except ImportError:
    HAS_CHINESE_CALENDAR = False

# 2026 年已知调休补班日（即使是周六周日也是工作日）与法定假期（周一至周五也是休假日）的兜底表
FALLBACK_2026_WORKDAYS = {
    # 元旦、春节、清明、劳动、端午、中秋、国庆相关的周末调休补班
    datetime.date(2026, 1, 4),   # 元旦后补班
    datetime.date(2026, 2, 14),  # 春节前补班
    datetime.date(2026, 2, 28),  # 春节后补班
    datetime.date(2026, 4, 11),  # 清明补班
    datetime.date(2026, 4, 25),  # 五一前补班
    datetime.date(2026, 5, 9),   # 五一后补班
    datetime.date(2026, 9, 20),  # 中秋/国庆补班 (周日)
    datetime.date(2026, 10, 10), # 国庆补班 (周六)
}

FALLBACK_2026_HOLIDAYS = {
    # 2026 法定节假日（休假不用上班）
    datetime.date(2026, 1, 1), datetime.date(2026, 1, 2), datetime.date(2026, 1, 3), # 元旦
    datetime.date(2026, 2, 16), datetime.date(2026, 2, 17), datetime.date(2026, 2, 18),
    datetime.date(2026, 2, 19), datetime.date(2026, 2, 20), datetime.date(2026, 2, 21), datetime.date(2026, 2, 22), # 春节
    datetime.date(2026, 4, 4), datetime.date(2026, 4, 5), datetime.date(2026, 4, 6), # 清明
    datetime.date(2026, 5, 1), datetime.date(2026, 5, 2), datetime.date(2026, 5, 3), datetime.date(2026, 5, 4), datetime.date(2026, 5, 5), # 五一
    datetime.date(2026, 6, 19), datetime.date(2026, 6, 20), datetime.date(2026, 6, 21), # 端午
    datetime.date(2026, 9, 25), datetime.date(2026, 9, 26), datetime.date(2026, 9, 27), # 中秋
    datetime.date(2026, 10, 1), datetime.date(2026, 10, 2), datetime.date(2026, 10, 3),
    datetime.date(2026, 10, 4), datetime.date(2026, 10, 5), datetime.date(2026, 10, 6), datetime.date(2026, 10, 7), # 国庆
}

def is_china_workday(d: datetime.date) -> bool:
    if HAS_CHINESE_CALENDAR:
        try:
            return calendar.is_workday(d)
        except Exception:
            pass
    # 兜底判定
    if d in FALLBACK_2026_WORKDAYS:
        return True
    if d in FALLBACK_2026_HOLIDAYS:
        return False
    # 常规周一至周五 (0-4) 为工作日
    return d.weekday() < 5
