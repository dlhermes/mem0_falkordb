"""Semantic deduplication of near-duplicate memories (no compression).

Merges memories that express the same fact, keeps the newer/more complete
one, deletes the other. Never rewrites or compresses content.

Pipeline (three gates):
  1. Vector coarse filter (no LLM): pairwise cosine similarity on embeddings,
     candidates where sim > DEDUP_SIMILARITY_THRESHOLD.
  2. Char Jaccard pre-filter (no LLM): drop candidates whose char Jaccard
     < DEDUP_MIN_JACCARD (visibly different wording).
  3. LLM binary judgment: "same fact? YES/NO" per remaining candidate pair.

Identity convention (IMPORTANT): any write to mem0 must use
user_id=hermes-user / agent_id=hermes to stay consistent with Hermes
auto-written memories (recall is scoped by these keys). This script only
deletes (never adds), so writes are not applicable; keep the convention in
mind if a write path is ever added.

Environment:
  MEM0_CONFIG_PATH              — path to config.json (default: /app/config.json)
  PRUNE_DRY_RUN                 — "true" to only report without deleting
  DEDUP_SIMILARITY_THRESHOLD    — vector coarse-filter threshold (default: 0.85)
  DEDUP_MIN_JACCARD             — char Jaccard lower bound (default: 0.2)
  DEDUP_EMBED_BATCH             — embed batch size (default: 10)
"""

DEFAULT_USER_ID = "hermes-user"
DEFAULT_AGENT_ID = "hermes"

import json
import logging
import os
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("dedup_memories")

SCAN_LIMIT = 10_000
GET_ALL_LIMIT = 10_000


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


def _timestamp(mem: dict) -> str:
    """Newest-known timestamp for a memory; prefers updated_at, falls back to created_at."""
    return mem.get("updated_at") or mem.get("created_at") or ""


def is_newer(a: dict, b: dict) -> bool:
    """True if memory a is the better survivor vs b (newer, then more complete)."""
    try:
        ta = datetime.fromisoformat(_timestamp(a).replace("Z", "+00:00"))
        tb = datetime.fromisoformat(_timestamp(b).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        ta = tb = None
    if ta is not None and tb is not None and ta != tb:
        return ta > tb
    return len(a.get("memory", "")) >= len(b.get("memory", ""))


def char_jaccard(a: str, b: str) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    return len(sa & sb) / len(union)


def find_candidates(texts: list[str], embeddings, threshold: float, min_jaccard: float):
    """Vector + char pre-filters. Returns list of (i, j, sim) with i < j."""
    try:
        import numpy as np
    except ImportError:
        logger.error("numpy is required (mem0 runtime dependency)")
        raise

    arr = np.asarray(embeddings, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[0] != len(texts):
        logger.error("embed_batch returned %s; expected %s rows", arr.shape, len(texts))
        return []

    norm = np.linalg.norm(arr, axis=1, keepdims=True)
    sim = (arr @ arr.T) / (np.clip(norm, 1e-9, None) @ np.clip(norm, 1e-9, None).T)
    np.fill_diagonal(sim, 0.0)

    candidates = []
    rows, cols = np.where(sim > threshold)
    for i, j in zip(rows.tolist(), cols.tolist()):
        if i >= j:
            continue
        if char_jaccard(texts[i], texts[j]) < min_jaccard:
            continue
        candidates.append((int(i), int(j), float(sim[i, j])))
    return sorted(candidates, key=lambda c: -c[2])


def same_fact(memory, a: str, b: str) -> bool:
    """LLM binary judgment: do these two memories state the same fact?"""
    prompt = (
        "这两条记忆是否表述同一事实？仅回答 YES 或 NO。\n\n"
        f"记忆A：{a}\n\n记忆B：{b}"
    )
    try:
        response = memory.llm.generate_response([{"role": "user", "content": prompt}])
    except Exception as e:
        logger.warning("LLM judgment failed: %s", e)
        return False
    answer = str(response)
    try:
        answer = json.loads(answer).get("answer", answer)
    except (ValueError, TypeError, AttributeError):
        pass
    return str(answer).strip().upper().startswith("YES")


def dedup_user(memory, user_id: str, threshold: float, min_jaccard: float, batch_size: int, dry_run: bool) -> list[tuple[dict, dict]]:
    """Find and merge near-duplicate memories for one user.

    Returns list of (keep, delete) memory dict pairs.
    """
    try:
        all_mems = memory.get_all(filters={"user_id": user_id}, top_k=GET_ALL_LIMIT)
    except Exception as e:
        logger.error("get_all failed for %s: %s", user_id, e)
        return []

    mems = [m for m in all_mems.get("results", []) if m.get("memory")]
    if len(mems) < 2:
        return []

    texts = [m["memory"] for m in mems]
    logger.info("%s: %s memories, embedding...", user_id, len(mems))

    embeddings = []
    for i in range(0, len(texts), batch_size):
        try:
            embeddings.extend(memory.embedding_model.embed_batch(texts[i : i + batch_size]))
        except Exception as e:
            logger.error("embed_batch failed for %s at %s: %s", user_id, i, e)
            return []

    candidates = find_candidates(texts, embeddings, threshold, min_jaccard)
    if not candidates:
        logger.info("%s: no candidate pairs above threshold %.2f", user_id, threshold)
        return []

    logger.info("%s: %s candidate pair(s) passed pre-filters", user_id, len(candidates))
    merges: list[tuple[dict, dict]] = []
    deleted_ids: set[str] = set()

    for i, j, sim in candidates:
        a, b = mems[i], mems[j]
        if a["id"] in deleted_ids or b["id"] in deleted_ids:
            continue
        if not same_fact(memory, a["memory"], b["memory"]):
            continue
        keep, delete = (a, b) if is_newer(a, b) else (b, a)
        deleted_ids.add(delete["id"])
        merges.append((keep, delete))

        if dry_run:
            logger.info(
                "[DRY_RUN] would merge %s %.2f: keep %s | delete %s",
                user_id, sim, keep["memory"][:40], delete["memory"][:40],
            )
        else:
            try:
                memory.delete(delete["id"])
                logger.info(
                    "merged %s: kept '%s', deleted '%s'",
                    user_id, keep["memory"][:40], delete["memory"][:40],
                )
            except Exception as e:
                logger.warning("delete failed %s: %s", delete["id"][:8], e)

    return merges


def main() -> int:
    config_path = os.environ.get("MEM0_CONFIG_PATH", "/app/config.json")
    dry_run = os.environ.get("PRUNE_DRY_RUN", "").lower() == "true"
    threshold = float(os.environ.get("DEDUP_SIMILARITY_THRESHOLD", "0.85"))
    min_jaccard = float(os.environ.get("DEDUP_MIN_JACCARD", "0.2"))
    batch_size = int(os.environ.get("DEDUP_EMBED_BATCH", "10"))

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

    # Scripts run from /app/scripts/; server modules (evolve_cleanup) live in /app/.
    _app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _app_dir not in sys.path:
        sys.path.insert(0, _app_dir)
    from evolve_cleanup import build_session_factory, register_delete_cleanup

    register_delete_cleanup(memory, build_session_factory(config))
    user_ids = discover_users(memory)

    if not user_ids:
        logger.info("no users found — nothing to dedupe")
        return 0

    logger.info(
        "deduplicating %s users (dry_run=%s, threshold=%.2f, min_jaccard=%.2f)",
        len(user_ids), dry_run, threshold, min_jaccard,
    )

    all_merges = 0
    involved: set[str] = set()
    for uid in user_ids:
        merges = dedup_user(memory, uid, threshold, min_jaccard, batch_size, dry_run)
        all_merges += len(merges)
        for keep, delete in merges:
            involved.add(keep["id"])
            involved.add(delete["id"])

    remaining = len(involved) - all_merges
    report = f"deduplicated {all_merges} pairs ({len(involved)} memories -> {remaining} memories)"
    if dry_run:
        report = "[DRY_RUN] " + report
    logger.info(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
