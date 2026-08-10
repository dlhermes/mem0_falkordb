"""Delete expired or used refresh token jti rows from refresh_token_jtis.

Expired rows are always removed. Used (single-use, already consumed) jtis are
kept for REFRESH_TOKEN_RETENTION_DAYS (default 30) as a replay-audit window.
Set PRUNE_DRY_RUN=true to report without deleting.

Run inside the `mem0` container, or wire into cron / a systemd timer on the host.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from db import SessionLocal
from models import RefreshTokenJti


def main() -> int:
    retention_raw = os.environ.get("REFRESH_TOKEN_RETENTION_DAYS", "").strip() or "30"
    try:
        retention_days = int(retention_raw)
    except ValueError:
        sys.stderr.write("REFRESH_TOKEN_RETENTION_DAYS must be an integer.\n")
        return 1
    if retention_days < 1:
        sys.stderr.write("REFRESH_TOKEN_RETENTION_DAYS must be >= 1.\n")
        return 1

    dry_run = os.environ.get("PRUNE_DRY_RUN", "").strip().lower() == "true"
    now = datetime.now(timezone.utc)
    used_cutoff = now - timedelta(days=retention_days)
    conditions = (RefreshTokenJti.expires_at < now) | (
        (RefreshTokenJti.used_at.is_not(None)) & (RefreshTokenJti.used_at < used_cutoff)
    )

    with SessionLocal() as session:
        if dry_run:
            count = session.execute(select(func.count()).select_from(RefreshTokenJti).where(conditions)).scalar_one()
            sys.stdout.write(
                f"Dry run: would delete {count} refresh_token_jtis rows "
                f"(expired before {now.isoformat()} or used before {used_cutoff.isoformat()}).\n"
            )
            return 0

        result = session.execute(delete(RefreshTokenJti).where(conditions))
        session.commit()
        sys.stdout.write(
            f"Deleted {result.rowcount or 0} refresh_token_jtis rows "
            f"(expired before {now.isoformat()} or used before {used_cutoff.isoformat()}).\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
