"""Delete SQLite history.db rows older than HISTORY_RETENTION_DAYS (default 90).

Run inside the `mem0` container, or wire into cron / a systemd timer on the host.

Only touches the `history` table (change-log audit rows). The `messages` table
has its own built-in eviction and is left alone.

Environment:
  HISTORY_DB_PATH       — path to the SQLite file (default: /app/history/history.db)
  HISTORY_RETENTION_DAYS— delete rows with created_at older than this many days (default: 90)
  PRUNE_DRY_RUN         — "true" to only report what would be deleted
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone


def main() -> int:
    db_path = os.environ.get("HISTORY_DB_PATH", "/app/history/history.db").strip() or "/app/history/history.db"
    raw = os.environ.get("HISTORY_RETENTION_DAYS", "").strip() or "90"
    try:
        retention_days = int(raw)
    except ValueError:
        sys.stderr.write("HISTORY_RETENTION_DAYS must be an integer.\n")
        return 1
    if retention_days < 1:
        sys.stderr.write("HISTORY_RETENTION_DAYS must be >= 1.\n")
        return 1
    dry_run = os.environ.get("PRUNE_DRY_RUN", "").lower() == "true"

    if not os.path.exists(db_path):
        sys.stderr.write(f"history db not found: {db_path}\n")
        return 1

    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    size_before = os.path.getsize(db_path)

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute(
            "DELETE FROM history "
            "WHERE created_at IS NOT NULL AND datetime(created_at) < datetime(?)",
            (cutoff,),
        )
        deleted = conn.total_changes
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    if dry_run:
        sys.stdout.write(
            f"[DRY_RUN] would delete {deleted} history rows older than {cutoff} "
            f"(db size {size_before} bytes).\n"
        )
        return 0

    size_after = size_before
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()
        size_after = os.path.getsize(db_path)
    except Exception as e:
        sys.stderr.write(f"VACUUM failed (retry on next run): {e}\n")

    sys.stdout.write(
        f"Deleted {deleted} history rows older than {cutoff}. "
        f"db size: {size_before} -> {size_after} bytes.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
