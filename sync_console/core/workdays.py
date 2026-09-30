import datetime
import logging

logger = logging.getLogger(__name__)

try:
    import chinese_calendar as calendar
    HAS_CHINESE_CALENDAR = True
except ImportError:
    HAS_CHINESE_CALENDAR = False
    logger.warning("chinesecalendar 包未安装！节假日判定将依赖标准周一至周五与 2026 年内置调休兜底。")

# 2026 年已知调休补班日（即使是周六周日也是工作日）与法定假期（周一至周五也是休假日）的兜底表
FALLBACK_2026_WORKDAYS = {
    datetime.date(2026, 1, 4),
    datetime.date(2026, 2, 14),
    datetime.date(2026, 2, 28),
    datetime.date(2026, 4, 11),
    datetime.date(2026, 4, 25),
    datetime.date(2026, 5, 9),
    datetime.date(2026, 9, 20),
    datetime.date(2026, 10, 10),
}

FALLBACK_2026_HOLIDAYS = {
    datetime.date(2026, 1, 1), datetime.date(2026, 1, 2), datetime.date(2026, 1, 3),
    datetime.date(2026, 2, 16), datetime.date(2026, 2, 17), datetime.date(2026, 2, 18),
    datetime.date(2026, 2, 19), datetime.date(2026, 2, 20), datetime.date(2026, 2, 21), datetime.date(2026, 2, 22),
    datetime.date(2026, 4, 4), datetime.date(2026, 4, 5), datetime.date(2026, 4, 6),
    datetime.date(2026, 5, 1), datetime.date(2026, 5, 2), datetime.date(2026, 5, 3), datetime.date(2026, 5, 4), datetime.date(2026, 5, 5),
    datetime.date(2026, 6, 19), datetime.date(2026, 6, 20), datetime.date(2026, 6, 21),
    datetime.date(2026, 9, 25), datetime.date(2026, 9, 26), datetime.date(2026, 9, 27),
    datetime.date(2026, 10, 1), datetime.date(2026, 10, 2), datetime.date(2026, 10, 3),
    datetime.date(2026, 10, 4), datetime.date(2026, 10, 5), datetime.date(2026, 10, 6), datetime.date(2026, 10, 7),
}

def is_china_workday(d: datetime.date) -> bool:
    if HAS_CHINESE_CALENDAR:
        try:
            return calendar.is_workday(d)
        except Exception:
            pass

    if d in FALLBACK_2026_WORKDAYS:
        return True
    if d in FALLBACK_2026_HOLIDAYS:
        return False
    return d.weekday() < 5
