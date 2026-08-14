"""Backfill memory_type for memories written before write-time classification.

Assigns the 5-class memory_type label (FACTS / PREFERENCES / EXPERIENCES /
OBSERVATIONS / DECISIONS) to every memory whose payload lacks a valid
memory_type, reusing the same classify_memory_type rules as the write path.
Idempotent: re-running only touches memories that still lack (or hold an
invalid) memory_type.

Identity convention (IMPORTANT): memories carry user_id=hermes-user /
agent_id=hermes to match Hermes auto-written memories. This script only
re-writes existing payloads (never creates memories), so it introduces no new
identity.

Environment:
  MEM0_CONFIG_PATH  — path to config.json (default: /app/config.json)
  PRUNE_DRY_RUN     — "true" to only report without writing (DRY_RUN)
  --use-llm         — CLI flag: LLM-classify pending memories, falling back
                      to keyword rules on any LLM/parse failure (default off)

Usage (same as dedup_memories.py, inside the container):
  python3 scripts/backfill_memory_types.py [--use-llm]
"""

import json
import logging
import os
import sys
import time
from collections import Counter
from typing import Optional

from mem0.memory.main import VALID_MEMORY_TYPES, classify_memory_type

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_memory_types")

DEFAULT_USER_ID = "hermes-user"
DEFAULT_AGENT_ID = "hermes"

SCAN_LIMIT = 10_000

LLM_CLASSIFY_SYSTEM_PROMPT = (
    "你是记忆类型分类器。判断给定记忆属于哪种类型，只能从 FACTS / PREFERENCES / "
    "EXPERIENCES / OBSERVATIONS / DECISIONS 五类中选一个。你必须严格输出 JSON 格式："
    '{"type": "FACTS"}，不要其他任何内容。'
)


def _list_rows(memory) -> list:
    results = memory.vector_store.list(top_k=SCAN_LIMIT)
    return results[0] if results and isinstance(results, list) and isinstance(results[0], list) else results or []


def discover_users(memory) -> list[str]:
    """Scan vector store payloads for unique user_ids."""
    user_ids: set[str] = set()
    for row in _list_rows(memory):
        payload = getattr(row, "payload", None) or {}
        uid = payload.get("user_id")
        if uid:
            user_ids.add(str(uid))
    return sorted(user_ids)


def _llm_classify(memory, text: str) -> Optional[str]:
    """One-shot LLM classification; returns a valid memory_type or None."""
    try:
        response = memory.llm.generate_response(
            messages=[
                {"role": "system", "content": LLM_CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": text or ""},
            ]
        )
    except Exception as e:  # noqa: BLE001 - fall back to rules on any failure
        logger.warning("LLM classify failed, falling back to rules: %s", e)
        return None
    try:
        parsed = json.loads(str(response))
        memory_type = parsed.get("type")
    except (ValueError, TypeError, AttributeError):
        return None
    return memory_type if memory_type in VALID_MEMORY_TYPES else None


def backfill_memories(memory, rows: list, use_llm: bool = False, dry_run: bool = False):
    """Classify and backfill memory_type on every row missing a valid one.

    Returns (scanned, pending, updated, type_distribution, per_user_pending).
    vector_store.update's payload is full-overwrite: always sends the merged
    {**old_payload, "memory_type": t}.
    """
    scanned = 0
    pending = 0
    updated = 0
    distribution = Counter()
    per_user = Counter()
    for row in rows:
        mem_id = getattr(row, "id", None)
        payload = getattr(row, "payload", None) or {}
        scanned += 1
        if payload.get("memory_type") in VALID_MEMORY_TYPES:
            continue  # already backfilled / valid — idempotent skip
        pending += 1
        text = payload.get("data") or payload.get("text") or ""
        llm_type = _llm_classify(memory, text) if use_llm else None
        memory_type = classify_memory_type(text, llm_type=llm_type)
        distribution[memory_type] += 1
        per_user[str(payload.get("user_id") or "unknown")] += 1
        if dry_run:
            continue
        try:
            memory.vector_store.update(vector_id=mem_id, payload={**payload, "memory_type": memory_type})
            updated += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("update failed for %s: %s", mem_id, e)
    return scanned, pending, updated, distribution, per_user


def main() -> int:
    config_path = os.environ.get("MEM0_CONFIG_PATH", "/app/config.json")
    dry_run = os.environ.get("PRUNE_DRY_RUN", "").lower() == "true"
    use_llm = "--use-llm" in sys.argv[1:]

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

    start = time.monotonic()
    rows = _list_rows(memory)
    user_ids = discover_users(memory)
    scanned, pending, updated, distribution, per_user = backfill_memories(
        memory, rows, use_llm=use_llm, dry_run=dry_run
    )
    elapsed = time.monotonic() - start

    if dry_run:
        for uid in user_ids:
            if per_user.get(uid):
                logger.info("[DRY_RUN] %s: %d 条待回填", uid, per_user[uid])
        report = f"[DRY_RUN] would backfill {pending} memories in {elapsed:.1f}s"
    else:
        dist_str = ", ".join(f"{k}={v}" for k, v in sorted(distribution.items()))
        report = (
            f"scanned {scanned} memories, {pending} to backfill, {updated} updated "
            f"({dist_str}) in {elapsed:.1f}s"
        )
    logger.info(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
