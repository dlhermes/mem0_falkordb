"""Recompute text_lemmatized for all PG memories after lemmatization changes.

Backfills the BM25 keyword-search index field after lemmatize_for_bm25
behavior changed (CJK jieba tokenization). Reads the vector_store block
from config.json, connects to PostgreSQL directly, and rewrites
payload['text_lemmatized'] from payload['data'] for every row.

Environment:
  MEM0_CONFIG_PATH  — path to config.json (default: /app/config.json)
  PRUNE_DRY_RUN     — "true" to only report without updating
"""

import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_lemmatized")


def main() -> int:
    config_path = os.environ.get("MEM0_CONFIG_PATH", "/app/config.json")
    dry_run = os.environ.get("PRUNE_DRY_RUN", "").lower() == "true"

    if not os.path.exists(config_path):
        logger.error("config not found: %s", config_path)
        return 1

    with open(config_path) as f:
        config = json.load(f)

    vs = config.get("vector_store") or {}
    if vs.get("provider") != "pgvector":
        logger.error("vector_store.provider must be pgvector, got %r", vs.get("provider"))
        return 1
    vs_config = vs.get("config") or {}
    table = vs_config.get("collection_name") or "mem0_memories"

    try:
        from psycopg import connect, sql
    except ImportError:
        from psycopg2 import connect, sql

    conninfo = vs_config.get("connection_string") or (
        "postgresql://{user}:{password}@{host}:{port}/{dbname}".format(**vs_config)
    )

    from mem0.utils.lemmatization import lemmatize_for_bm25

    table_id = sql.Identifier(table)
    select_sql = sql.SQL(
        "SELECT id, payload->>'data' FROM {} WHERE payload->>'data' IS NOT NULL"
    ).format(table_id)
    update_sql = sql.SQL(
        "UPDATE {} SET payload = jsonb_set(payload, '{{text_lemmatized}}', %s) WHERE id = %s"
    ).format(table_id)

    total = changed = 0
    with connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(select_sql)
            rows = cur.fetchall()
        total = len(rows)

        for memory_id, data in rows:
            text_lemmatized = lemmatize_for_bm25(data or "")
            if dry_run:
                logger.info(
                    "[DRY_RUN] %s: %r -> %r", memory_id, (data or "")[:30], text_lemmatized[:60]
                )
                continue
            with conn.cursor() as cur:
                cur.execute(update_sql, (json.dumps(text_lemmatized), str(memory_id)))
            changed += 1
        conn.commit()

    report = f"backfilled text_lemmatized for {changed}/{total} rows"
    if dry_run:
        report = "[DRY_RUN] would " + report
    logger.info(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
