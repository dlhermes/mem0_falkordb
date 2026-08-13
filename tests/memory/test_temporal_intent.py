from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from mem0.memory import temporal_intent


def _freeze(monkeypatch, dt):
    monkeypatch.setattr(temporal_intent, "_now", lambda: dt)


FIXED = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


class TestStrongRecent:
    def test_recent_chinese(self):
        assert temporal_intent.detect_temporal_intent("最近部署了什么") == {
            "type": "recent",
            "days": 7,
            "strength": "strong",
        }

    def test_near_three_days(self):
        assert temporal_intent.detect_temporal_intent("近三天") == {
            "type": "recent",
            "days": 3,
            "strength": "strong",
        }

    def test_latest(self):
        assert temporal_intent.detect_temporal_intent("最新") == {
            "type": "recent",
            "days": 7,
            "strength": "strong",
        }

    def test_just_now(self):
        assert temporal_intent.detect_temporal_intent("刚刚") == {
            "type": "recent",
            "days": 7,
            "strength": "strong",
        }

    def test_hours_ago_floor_one(self):
        assert temporal_intent.detect_temporal_intent("3小时前") == {
            "type": "recent",
            "days": 1,
            "strength": "strong",
        }

    def test_two_days_ago(self):
        assert temporal_intent.detect_temporal_intent("两天前") == {
            "type": "recent",
            "days": 2,
            "strength": "strong",
        }

    def test_near_two_weeks(self):
        assert temporal_intent.detect_temporal_intent("近2周") == {
            "type": "recent",
            "days": 14,
            "strength": "strong",
        }

    def test_near_one_month(self):
        assert temporal_intent.detect_temporal_intent("近1个月") == {
            "type": "recent",
            "days": 30,
            "strength": "strong",
        }

    def test_last_n_days_en(self):
        assert temporal_intent.detect_temporal_intent("last 3 days") == {
            "type": "recent",
            "days": 3,
            "strength": "strong",
        }

    def test_recent_en(self):
        assert temporal_intent.detect_temporal_intent("recent") == {
            "type": "recent",
            "days": 7,
            "strength": "strong",
        }

    def test_latest_en(self):
        assert temporal_intent.detect_temporal_intent("latest") == {
            "type": "recent",
            "days": 7,
            "strength": "strong",
        }

    def test_window_days_param(self):
        assert temporal_intent.detect_temporal_intent("最近", window_days=3) == {
            "type": "recent",
            "days": 3,
            "strength": "strong",
        }


class TestWeakDate:
    def test_yesterday(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("昨天部署了什么") == {
            "type": "date",
            "date": "2026-08-12",
            "strength": "weak",
        }

    def test_today(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("今天") == {
            "type": "date",
            "date": "2026-08-13",
            "strength": "weak",
        }

    def test_yesterday_en(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("yesterday") == {
            "type": "date",
            "date": "2026-08-12",
            "strength": "weak",
        }

    def test_today_en(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("today") == {
            "type": "date",
            "date": "2026-08-13",
            "strength": "weak",
        }


class TestWeakRange:
    def test_this_week(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("本周") == {
            "type": "range",
            "start": "2026-08-10",
            "end": "2026-08-16",
            "strength": "weak",
        }

    def test_last_week(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("上周") == {
            "type": "range",
            "start": "2026-08-03",
            "end": "2026-08-09",
            "strength": "weak",
        }

    def test_this_month(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("本月") == {
            "type": "range",
            "start": "2026-08-01",
            "end": "2026-08-31",
            "strength": "weak",
        }

    def test_last_month(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("上月") == {
            "type": "range",
            "start": "2026-07-01",
            "end": "2026-07-31",
            "strength": "weak",
        }

    def test_this_week_en(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("this week") == {
            "type": "range",
            "start": "2026-08-10",
            "end": "2026-08-16",
            "strength": "weak",
        }

    def test_last_week_en(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("last week") == {
            "type": "range",
            "start": "2026-08-03",
            "end": "2026-08-09",
            "strength": "weak",
        }


class TestExclusion:
    @pytest.mark.parametrize(
        "query",
        ["今天天气怎么样", "最近新闻", "股票行情", "what's the weather", "最新汇率", "查看待办日程"],
    )
    def test_excluded(self, query):
        assert temporal_intent.detect_temporal_intent(query) is None


class TestISO:
    @pytest.mark.parametrize(
        ("query", "start", "end"),
        [
            ("2026-08-01 到 2026-08-10", "2026-08-01", "2026-08-10"),
            ("2026-08-01 至 2026-08-10", "2026-08-01", "2026-08-10"),
            ("2026-08-01 ~ 2026-08-10", "2026-08-01", "2026-08-10"),
            ("2026-08-01 to 2026-08-10", "2026-08-01", "2026-08-10"),
        ],
    )
    def test_range(self, query, start, end):
        assert temporal_intent.detect_temporal_intent(query) == {
            "type": "range",
            "start": start,
            "end": end,
            "strength": "strong",
        }

    def test_single_date(self):
        assert temporal_intent.detect_temporal_intent("2025-04-09") == {
            "type": "date",
            "date": "2025-04-09",
            "strength": "strong",
        }

    def test_since_iso(self):
        assert temporal_intent.detect_temporal_intent("since 2026-08-01") == {
            "type": "range",
            "start": "2026-08-01",
            "end": None,
            "strength": "strong",
        }

    def test_before_iso(self):
        assert temporal_intent.detect_temporal_intent("before 2026-08-10") == {
            "type": "range",
            "start": None,
            "end": "2026-08-10",
            "strength": "strong",
        }

    def test_since_yesterday(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("since yesterday") == {
            "type": "range",
            "start": "2026-08-12",
            "end": None,
            "strength": "strong",
        }

    def test_before_today(self, monkeypatch):
        _freeze(monkeypatch, FIXED)
        assert temporal_intent.detect_temporal_intent("before today") == {
            "type": "range",
            "start": None,
            "end": "2026-08-13",
            "strength": "strong",
        }


class TestNoIntent:
    @pytest.mark.parametrize(
        "query",
        ["favorite drink", "帮我总结一下会议内容", "普通运维查询", "如何部署服务"],
    )
    def test_none(self, query):
        assert temporal_intent.detect_temporal_intent(query) is None


class TestTimezone:
    def test_midnight_shanghai_uses_shanghai_not_utc(self, monkeypatch):
        shanghai_midnight = datetime(2026, 8, 13, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        _freeze(monkeypatch, shanghai_midnight)
        assert temporal_intent.detect_temporal_intent("昨天")["date"] == "2026-08-12"
        assert temporal_intent.detect_temporal_intent("今天")["date"] == "2026-08-13"
        assert temporal_intent.detect_temporal_intent("本周") == {
            "type": "range",
            "start": "2026-08-10",
            "end": "2026-08-16",
            "strength": "weak",
        }


class TestChineseTens:
    @pytest.mark.parametrize(
        ("query", "days"),
        [
            ("近二十天", 20),
            ("近二十三天", 23),
            ("近十五天", 15),
            ("近十天", 10),
            ("近三十天", 30),
            ("近三个月", 90),
        ],
    )
    def test_near(self, query, days):
        assert temporal_intent.detect_temporal_intent(query) == {
            "type": "recent",
            "days": days,
            "strength": "strong",
        }

    def test_ago(self):
        assert temporal_intent.detect_temporal_intent("二十天前") == {
            "type": "recent",
            "days": 20,
            "strength": "strong",
        }
