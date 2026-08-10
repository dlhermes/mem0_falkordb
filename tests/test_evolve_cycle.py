"""Tests for the evolve cycle script (server/scripts/evolve_cycle.py).

Covers the three cron jobs: high-frequency salience boost (with same-day
idempotency), 24h zero-hit aggregation, and the >14d idle report. Uses a
sqlite temp DB and calls the script's pure session-taking functions directly
(script runs in Docker via `python3 scripts/evolve_cycle.py`, bare imports).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

# server/ modules use bare imports (from db import ...), so the server and
# scripts directories must be importable, mirroring how the script runs.
_SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "server")
for _dir in (_SERVER_DIR, os.path.join(_SERVER_DIR, "scripts")):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from db import Base  # noqa: E402
from models import EvolveSalience, EvolveSalienceAdjustment, EvolveQuery  # noqa: E402
import evolve_cycle  # noqa: E402

NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _salience(db, memory_id, access_count=0, score=1.0, last_access=None):
    row = EvolveSalience(
        memory_id=memory_id,
        access_count=access_count,
        salience_score=score,
        last_access_at=last_access,
    )
    db.add(row)
    return row


class TestBoostDelta:
    def test_formula_min_access_one_hundredth(self):
        assert evolve_cycle.boost_delta(5) == 0.01

    def test_formula_caps_at_five_hundredths(self):
        assert evolve_cycle.boost_delta(10) == 0.05
        assert evolve_cycle.boost_delta(20) == 0.05


class TestBoostCandidates:
    def test_below_min_access_not_eligible(self, db):
        _salience(db, "cold", access_count=4)
        db.commit()
        assert [r.memory_id for r in evolve_cycle.boost_candidates(db, NOW)] == []

    def test_at_min_access_eligible(self, db):
        _salience(db, "warm", access_count=5)
        db.commit()
        assert [r.memory_id for r in evolve_cycle.boost_candidates(db, NOW)] == ["warm"]

    def test_at_max_score_not_eligible(self, db):
        _salience(db, "topped", access_count=99, score=1.5)
        db.commit()
        assert evolve_cycle.boost_candidates(db, NOW) == []

    def test_already_boosted_today_excluded(self, db):
        _salience(db, "done", access_count=9)
        db.add(
            EvolveSalienceAdjustment(
                memory_id="done", delta=0.04, reason="evolve_boost", created_at=NOW
            )
        )
        db.commit()
        assert evolve_cycle.boost_candidates(db, NOW) == []

    def test_boosted_yesterday_still_eligible(self, db):
        _salience(db, "again", access_count=9)
        db.add(
            EvolveSalienceAdjustment(
                memory_id="again",
                delta=0.04,
                reason="evolve_boost",
                created_at=NOW - timedelta(days=1),
            )
        )
        db.commit()
        assert [r.memory_id for r in evolve_cycle.boost_candidates(db, NOW)] == ["again"]


class TestApplyBoosts:
    def test_boosts_and_writes_adjustment(self, db):
        _salience(db, "m1", access_count=5)
        db.commit()

        lines = evolve_cycle.apply_boosts(db, NOW)

        assert lines == ["BOOST m1 1.0000→1.0100 (acc=5)"]
        row = db.get(EvolveSalience, "m1")
        assert row.salience_score == pytest.approx(1.01)
        adj = db.scalar(select(EvolveSalienceAdjustment).where(EvolveSalienceAdjustment.memory_id == "m1"))
        assert adj.reason == "evolve_boost"
        assert adj.delta == pytest.approx(0.01)
        assert adj.feedback_id is None

    def test_caps_at_max_score(self, db):
        _salience(db, "m1", access_count=10, score=1.48)
        db.commit()

        lines = evolve_cycle.apply_boosts(db, NOW)

        assert lines == ["BOOST m1 1.4800→1.5000 (acc=10)"]
        assert db.get(EvolveSalience, "m1").salience_score == pytest.approx(1.5)
        adj = db.scalar(select(EvolveSalienceAdjustment).where(EvolveSalienceAdjustment.memory_id == "m1"))
        assert adj.delta == pytest.approx(0.02)

    def test_same_day_second_run_does_nothing(self, db):
        _salience(db, "m1", access_count=8)
        db.commit()

        first = evolve_cycle.apply_boosts(db, NOW)
        second = evolve_cycle.apply_boosts(db, NOW)

        assert len(first) == 1
        assert second == []
        with db as s:
            n = s.query(EvolveSalienceAdjustment).filter_by(reason="evolve_boost").count()
            assert n == 1

    def test_dry_run_writes_nothing(self, db):
        _salience(db, "m1", access_count=8)
        db.commit()

        lines = evolve_cycle.apply_boosts(db, NOW, dry_run=True)

        assert lines == ["BOOST m1 1.0000→1.0400 (acc=8)"]
        assert db.get(EvolveSalience, "m1").salience_score == pytest.approx(1.0)
        assert db.query(EvolveSalienceAdjustment).count() == 0


class TestZeroHitLines:
    def test_aggregates_counts_and_filters_window(self, db):
        db.add_all(
            [
                EvolveQuery(query="foo", is_zero_hit=True, created_at=NOW - timedelta(hours=1)),
                EvolveQuery(query="foo", is_zero_hit=True, created_at=NOW - timedelta(hours=2)),
                EvolveQuery(query="bar", is_zero_hit=True, created_at=NOW),
                EvolveQuery(query="old", is_zero_hit=True, created_at=NOW - timedelta(hours=25)),
                EvolveQuery(query="hit", is_zero_hit=False, created_at=NOW),
            ]
        )
        db.commit()

        assert evolve_cycle.zero_hit_lines(db, NOW) == ["ZERO_HIT bar x1", "ZERO_HIT foo x2"]

    def test_no_zero_hits_returns_empty(self, db):
        db.add(EvolveQuery(query="hit", is_zero_hit=False, created_at=NOW))
        db.commit()
        assert evolve_cycle.zero_hit_lines(db, NOW) == []


class TestIdleLines:
    def test_reports_stale_and_never_recalled(self, db):
        _salience(db, "stale", access_count=3, last_access=NOW - timedelta(days=21))
        _salience(db, "fresh", access_count=7, last_access=NOW - timedelta(days=1))
        _salience(db, "ghost", access_count=0, last_access=None)
        db.commit()

        lines = evolve_cycle.idle_lines(db, NOW)

        assert lines == [
            "IDLE ghost (acc=0, last=never)",
            "IDLE stale (acc=3, last=2026-07-20)",
        ]

    def test_no_idle_returns_empty(self, db):
        _salience(db, "fresh", access_count=2, last_access=NOW - timedelta(days=1))
        db.commit()
        assert evolve_cycle.idle_lines(db, NOW) == []
