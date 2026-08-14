"""Generate memory-refinement candidates for all users (discovery only).

Runs the same candidate-discovery pipeline as POST /memory/refine/candidates
(stale-memory discovery -> clustering -> LLM proposal) and writes candidates
to memory_refine_candidates. It NEVER applies: apply is human-triggered via
POST /memory/refine/apply, and this script never calls memory.add.

Environment:
  MEM0_CONFIG_PATH  — path to config.json (default: /app/config.json)
  REFINE_DRY_RUN    — "true" to only report without writing candidates

Usage (same as dedup_memories.py, inside the container):
  python3 scripts/refine_candidates.py
"""

import json
import logging
import os
import sys

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from db import SessionLocal  # noqa: E402
from routers.refine import discover_refine_candidates  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("refine_candidates")

SCAN_LIMIT = 10_000


def discover_users(memory) -> list[str]:
    """Scan vector store payloads for unique user_ids."""
    results = memory.vector_store.list(top_k=SCAN_LIMIT)
    rows = results[0] if results and isinstance(results, list) and isinstance(results[0], list) else results or []
    user_ids: set[str] = set()
    for row in rows:
        payload = getattr(row, "payload", None) or {}
        uid = payload.get("user_id")
        if uid:
            user_ids.add(str(uid))
    return sorted(user_ids)


def main() -> int:
    config_path = os.environ.get("MEM0_CONFIG_PATH", "/app/config.json")
    dry_run = os.environ.get("REFINE_DRY_RUN", "").lower() == "true"

    if not os.path.exists(config_path):
        logger.error("config not found: %s", config_path)
        return 1

    with open(config_path) as f:
        config = json.load(f)

    from mem0 import Memory

    config["version"] = "v1.1"
    if "graph_store" not in config:
        config["graph_store"] = {"provider": "memory", "config": None}
    memory = Memory.from_config(config)

    user_ids = discover_users(memory)
    if not user_ids:
        logger.info("no users found — nothing to refine")
        return 0

    logger.info("refining %s users (dry_run=%s)", len(user_ids), dry_run)

    total_scanned = 0
    total_candidates = 0
    with SessionLocal() as db:
        for uid in user_ids:
            if dry_run:
                # Discovery requires scanning; report only, no candidate writes.
                items = []
                try:
                    from routers.refine import _collect_stale_items

                    items = _collect_stale_items(memory, db, uid)
                except Exception:  # noqa: BLE001
                    items = []
                total_scanned += len(items)
                logger.info("[DRY_RUN] %s: %d 条待扫描", uid, len(items))
                continue
            created = discover_refine_candidates(memory, db, uid)
            total_scanned += _count_stale(memory, db, uid)
            total_candidates += len(created)
            logger.info("%s: 生成 %d 个候选", uid, len(created))

    report = f"scanned {total_scanned} memories, {total_candidates} candidate group(s)"
    if dry_run:
        report = "[DRY_RUN] " + report
    logger.info(report)
    print(report)
    return 0


def _count_stale(memory, db, user_id: str) -> int:
    from routers.refine import _collect_stale_items

    try:
        return len(_collect_stale_items(memory, db, user_id))
    except Exception:  # noqa: BLE001
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
