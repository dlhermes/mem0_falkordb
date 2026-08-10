"""Evolve cycle: daily salience boost + zero-hit stats + idle list.

Cron-driven (docker exec mem0-dev-mem0-1 sh -c "cd /app && python3 scripts/evolve_cycle.py").
Reads/writes only the evolve_* tables; memory content is never touched.

High-frequency boost: memories with access_count >= 5 and salience_score < 1.5
get a +min(0.05, (acc-5)*0.01) bump (acc=5 -> +0.01, acc=10 -> +0.05 cap),
capped at 1.5. Idempotent per memory per day: a memory already carrying an
evolve_boost adjustment today is skipped.

Watchdog-friendly stdout: lines are emitted only when there is something to
say. No actions at all -> empty output, exit 0.

Environment:
  EVOLVE_DRY_RUN            — "true" to report boosts without writing
  EVOLVE_BOOST_MIN_ACCESS   — access_count threshold (default: 5)
  EVOLVE_BOOST_MAX_SCORE    — salience cap (default: 1.5)
  EVOLVE_IDLE_DAYS          — idle threshold in days (default: 14)
  EVOLVE_ZERO_HIT_HOURS     — zero-hit aggregation window (default: 24)
"""

import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db import SessionLocal
from models import EvolveSalience, EvolveSalienceAdjustment, EvolveQuery


def boost_delta(access_count: int) -> float:
    """+0.01 floor at acc=5, +0.05 cap at acc=9+ (matches T4b examples)."""
    return min(0.05, (access_count - 4) * 0.01)


def boost_candidates(db, now, min_access: int = 5, max_score: float = 1.5) -> list:
    """EvolveSalience rows eligible for a boost today (not already boosted today)."""
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    boosted_today = set(
        db.scalars(
            select(EvolveSalienceAdjustment.memory_id).where(
                EvolveSalienceAdjustment.reason == "evolve_boost",
                EvolveSalienceAdjustment.created_at >= today_start,
            )
        ).all()
    )
    rows = db.scalars(
        select(EvolveSalience).where(
            EvolveSalience.access_count >= min_access,
            EvolveSalience.salience_score < max_score,
        )
    ).all()
    return [r for r in rows if r.memory_id not in boosted_today]


def apply_boosts(db, now, min_access: int = 5, max_score: float = 1.5, dry_run: bool = False) -> list[str]:
    """Boost eligible memories, return one BOOST line each. Writes unless dry_run."""
    lines = []
    for row in boost_candidates(db, now, min_access=min_access, max_score=max_score):
        before = row.salience_score
        after = round(min(before + boost_delta(row.access_count), max_score), 4)
        lines.append(f"BOOST {row.memory_id} {before:.4f}→{after:.4f} (acc={row.access_count})")
        if not dry_run:
            row.salience_score = after
            row.updated_at = now
            db.add(
                EvolveSalienceAdjustment(
                    memory_id=row.memory_id,
                    delta=round(after - before, 4),
                    reason="evolve_boost",
                    feedback_id=None,
                    created_at=now,
                )
            )
    if lines and not dry_run:
        db.commit()
    return lines


def zero_hit_lines(db, now, hours: int = 24) -> list[str]:
    """Zero-hit queries in the last `hours`, aggregated by query text."""
    cutoff = now - timedelta(hours=hours)
    queries = db.scalars(
        select(EvolveQuery.query).where(
            EvolveQuery.is_zero_hit.is_(True),
            EvolveQuery.created_at >= cutoff,
        )
    ).all()
    counts = Counter(queries)
    return [f"ZERO_HIT {query} x{n}" for query, n in sorted(counts.items())]


def idle_lines(db, now, idle_days: int = 14) -> list[str]:
    """Memories not recalled for > idle_days, or never recalled at all."""
    cutoff = now - timedelta(days=idle_days)
    rows = db.scalars(
        select(EvolveSalience).where(
            (EvolveSalience.last_access_at < cutoff) | (EvolveSalience.last_access_at.is_(None))
        )
    ).all()
    lines = []
    for row in sorted(rows, key=lambda r: r.memory_id):
        last = row.last_access_at.date().isoformat() if row.last_access_at else "never"
        lines.append(f"IDLE {row.memory_id} (acc={row.access_count}, last={last})")
    return lines


def main() -> int:
    try:
        dry_run = os.environ.get("EVOLVE_DRY_RUN", "").lower() == "true"
        min_access = int(os.environ.get("EVOLVE_BOOST_MIN_ACCESS", "5"))
        max_score = float(os.environ.get("EVOLVE_BOOST_MAX_SCORE", "1.5"))
        idle_days = int(os.environ.get("EVOLVE_IDLE_DAYS", "14"))
        zero_hours = int(os.environ.get("EVOLVE_ZERO_HIT_HOURS", "24"))
    except ValueError as e:
        sys.stderr.write(f"bad EVOLVE_* env value: {e}\n")
        return 1

    now = datetime.now(timezone.utc)
    prefix = "[DRY_RUN] " if dry_run else ""

    with SessionLocal() as db:
        lines = [prefix + line for line in apply_boosts(db, now, min_access=min_access, max_score=max_score, dry_run=dry_run)]
        lines += zero_hit_lines(db, now, hours=zero_hours)
        lines += idle_lines(db, now, idle_days=idle_days)

    for line in lines:
        sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
