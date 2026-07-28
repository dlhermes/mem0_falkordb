#!/bin/bash
# PostgreSQL 初始化脚本 — docker-entrypoint-initdb.d 自动执行
# 为 mem0_app 库创建，Alembic 在 mem0 容器启动时建表
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
  CREATE DATABASE mem0_app;
  GRANT ALL PRIVILEGES ON DATABASE mem0_app TO $POSTGRES_USER;
EOSQL

# 在主库预建向量表（避免 Dashboard 首次访问 500）
# ⚠️ vector(1024) 维度需与 Embedder 模型输出一致：
#   Bvoyage-4-large → 1024, text-embedding-3-small → 1536, BAAI/bge-m3 → 1024
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE TABLE IF NOT EXISTS memories (
      id UUID PRIMARY KEY,
      vector vector(1024),
      payload JSONB
  );
  CREATE INDEX IF NOT EXISTS memories_hnsw_idx ON memories USING hnsw (vector vector_cosine_ops);
EOSQL

echo "init-db.sh: mem0_app database and memories table created."
