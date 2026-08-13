import re
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

_EXCLUSION_WORDS = (
    "天气", "新闻", "汇率", "股票", "日程", "待办",
    "weather", "news", "stock", "schedule", "todo", "forecast", "exchange rate",
)

_CN_NUM_RE = r"[0-9一二两三四五六七八九十]+"

_NEAR_N_UNIT_RE = re.compile(rf"近({_CN_NUM_RE})(天|周|个?月)")
_AGO_RE = re.compile(rf"({_CN_NUM_RE})(个)?(小时|天|周|个?月)前")
_LAST_N_EN_RE = re.compile(r"last\s+([0-9]+)\s+(days?|weeks?|months?)")
_AGO_EN_RE = re.compile(r"([0-9]+)\s+(hours?|days?)\s+ago")

_STRONG_WORDS = ("最近", "近期", "最新一次", "最新", "刚刚", "just now", "latest", "recent")

_WEAK_DATE_CN = {"今天": "today", "昨天": "yesterday"}
_WEAK_DATE_EN = {"today", "yesterday"}
_WEAK_RANGE_CN = {"本周": "week", "上周": "week", "本月": "month", "上月": "month"}
_WEAK_RANGE_EN = {"this week": "week", "last week": "week", "this month": "month", "last month": "month"}

_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_RANGE_ISO_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})\s*(?:到|至|~|to)\s*(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE
)
_SINCE_AFTER_RE = re.compile(r"\b(since|after)\s+(today|yesterday|\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_BEFORE_UNTIL_RE = re.compile(r"\b(before|until)\s+(today|yesterday|\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)

_UNIT_DAYS_CN = {"天": 1, "周": 7, "月": 30, "个月": 30}
_UNIT_DAYS_EN = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30}


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _to_int(s: str) -> int:
    if s.isdigit():
        return int(s)
    if "十" in s:
        tens, _, ones = s.partition("十")
        return (_CN_NUM.get(tens, 1) if tens else 1) * 10 + (_CN_NUM.get(ones, 0) if ones else 0)
    return sum(_CN_NUM.get(ch, 0) for ch in s)


def _fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _week_range(d: date):
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def _month_range(d: date):
    first = d.replace(day=1)
    next_month = first.replace(year=first.year + (first.month == 12), month=first.month % 12 + 1)
    return first, next_month - timedelta(days=1)


def _resolve(token: str, today: date, yesterday: date) -> str:
    if token == "today":
        return _fmt(today)
    if token == "yesterday":
        return _fmt(yesterday)
    return token


def detect_temporal_intent(query: str, window_days: int = 7) -> Optional[dict]:
    if not isinstance(query, str):
        return None

    q = query.lower()
    for word in _EXCLUSION_WORDS:
        if word in q:
            return None

    now = _now()
    today = now.date()
    yesterday = today - timedelta(days=1)

    m = _NEAR_N_UNIT_RE.search(q)
    if m:
        return {"type": "recent", "days": _to_int(m.group(1)) * _UNIT_DAYS_CN[m.group(2)], "strength": "strong"}

    m = _AGO_RE.search(q)
    if m:
        n = _to_int(m.group(1))
        unit = m.group(3)
        if unit == "小时":
            n = max(1, (n + 23) // 24)
        else:
            n *= _UNIT_DAYS_CN[unit]
        return {"type": "recent", "days": n, "strength": "strong"}

    m = _LAST_N_EN_RE.search(q)
    if m:
        return {"type": "recent", "days": int(m.group(1)) * _UNIT_DAYS_EN[m.group(2)], "strength": "strong"}

    m = _AGO_EN_RE.search(q)
    if m:
        n = int(m.group(1))
        if m.group(2).startswith("hour"):
            n = max(1, (n + 23) // 24)
        return {"type": "recent", "days": n, "strength": "strong"}

    for word in _STRONG_WORDS:
        if word in q:
            return {"type": "recent", "days": window_days, "strength": "strong"}

    m = _SINCE_AFTER_RE.search(q)
    if m:
        return {"type": "range", "start": _resolve(m.group(2), today, yesterday), "end": None, "strength": "strong"}

    m = _BEFORE_UNTIL_RE.search(q)
    if m:
        return {"type": "range", "start": None, "end": _resolve(m.group(2), today, yesterday), "strength": "strong"}

    for word, kind in _WEAK_DATE_CN.items():
        if word in q:
            return {"type": "date", "date": _fmt(today if kind == "today" else yesterday), "strength": "weak"}
    for word in _WEAK_DATE_EN:
        if word in q:
            return {"type": "date", "date": _fmt(today if word == "today" else yesterday), "strength": "weak"}

    for word, kind in _WEAK_RANGE_CN.items():
        if word in q:
            ref = today
            if word in ("上周", "上月"):
                ref = today - timedelta(days=7) if kind == "week" else today.replace(day=1) - timedelta(days=1)
            start, end = _week_range(ref) if kind == "week" else _month_range(ref)
            return {"type": "range", "start": _fmt(start), "end": _fmt(end), "strength": "weak"}
    for word, kind in _WEAK_RANGE_EN.items():
        if word in q:
            ref = today
            if word in ("last week", "last month"):
                ref = today - timedelta(days=7) if kind == "week" else today.replace(day=1) - timedelta(days=1)
            start, end = _week_range(ref) if kind == "week" else _month_range(ref)
            return {"type": "range", "start": _fmt(start), "end": _fmt(end), "strength": "weak"}

    m = _RANGE_ISO_RE.search(q)
    if m:
        return {"type": "range", "start": m.group(1), "end": m.group(2), "strength": "strong"}

    m = _ISO_RE.search(q)
    if m:
        return {"type": "date", "date": m.group(1), "strength": "strong"}

    return None
