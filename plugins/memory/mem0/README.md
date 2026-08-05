# Mem0 Memory Provider

Server-side LLM fact extraction with semantic search and hybrid multi-signal retrieval via the Mem0 Platform v3 API.

## Requirements

- `pip install mem0ai`
- Mem0 API key from [app.mem0.ai](https://app.mem0.ai)

## Setup

```bash
hermes memory setup    # select "mem0"
```

Or manually:
```bash
hermes config set memory.provider mem0
echo "MEM0_API_KEY=your-key" >> ~/.hermes/.env
```

## Config

Behavioral settings live in `$HERMES_HOME/mem0.json` (set them via `hermes memory setup`). Only the secret `MEM0_API_KEY` belongs in `~/.hermes/.env`.

| Key | Default | Description |
|-----|---------|-------------|
| `mode` | `platform` | `platform` (Mem0 Cloud) or `oss` (self-managed, in-process) |
| `host` | — | Self-hosted Mem0 server URL (the Docker dashboard). When set, connects over HTTP with `X-API-Key`. Don't combine with `mode: oss` |
| `user_id` | `hermes-user` | User identifier on Mem0 |
| `agent_id` | `hermes` | Agent identifier |
| `rerank` | `false` | Rerank search results for relevance (platform mode only) |

### 潮浪并忆（Tidal Coalescing）— 批量合并写入

`sync_turn` 不再逐条调用服务端事实提取，而是把同一 `user+session` 的短对话合并成一次批量写入，摊薄 LLM 调用次数（写路径降本）。默认开启，全部参数通过环境变量配置（与 `MEM0_HOST` 等同风格）：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MEM0_COALESCE_ENABLED` | `true` | 总开关。`false` 时回到逐条写入的旧语义 |
| `MEM0_COALESCE_IDLE_SECS` | `5` | 空闲冲刷：桶内无新消息超过该秒数即写入 |
| `MEM0_COALESCE_WINDOW_SECS` | `15` | 窗口冲刷：桶从首条进入起超过该秒数即写入 |
| `MEM0_COALESCE_MAX_TURNS` | `5` | 条数上限：桶内对话轮数达到该值即写入 |
| `MEM0_COALESCE_MAX_CHARS` | `4000` | 字符上限：桶内累计字符达到该值即写入 |
| `MEM0_COALESCE_FASTPATH_CHARS` | `2000` | fastpath 阈值：单条消息超过该字符数时直接写入，不进合并缓冲 |

示例：密集对话场景可调大窗口提高合并率

```bash
echo "MEM0_COALESCE_WINDOW_SECS=30" >> ~/.hermes/.env
```

合并统计（批次、省下的调用数、按 session 分布）通过 `coalesce_stats()` 查询，日志中可见「潮浪并忆：合并 N 条对话为 1 次写入」。

The plugin has three connection modes:

- **Platform** — Mem0's hosted cloud (`api.mem0.ai`). Set `MEM0_API_KEY`. (default)
- **Self-hosted dashboard** — a Mem0 server you run yourself via Docker. Set `host`. See below.
- **OSS** — run Mem0 in-process with your own LLM + vector store. Set `mode: oss`. See below.

## Self-Hosted Dashboard (Server) Mode

Connect the plugin to a standalone Mem0 server you run yourself — the Docker-shipped Mem0 dashboard/server with its own REST API. Unlike OSS mode (which runs `mem0ai` in-process with your own vector store), here the plugin just talks HTTP to your server.

1. Run the Mem0 server (FastAPI + pgvector) from its Docker image and note its URL and `ADMIN_API_KEY`.
2. Point the plugin at it — via the setup wizard:
   ```bash
   hermes memory setup    # select "mem0" → "Self-hosted server"
   # Or non-interactive:
   hermes memory setup mem0 --mode selfhosted --host http://localhost:8888 --api-key your-admin-api-key
   ```
   or via env vars:
   ```bash
   echo "MEM0_HOST=http://localhost:8888" >> ~/.hermes/.env
   echo "MEM0_API_KEY=your-admin-api-key" >> ~/.hermes/.env
   ```
   or in `$HERMES_HOME/mem0.json`:
   ```json
   {
     "host": "http://localhost:8888",
     "api_key": "your-admin-api-key"
   }
   ```
3. Start a fresh Hermes session and call `mem0_search` — it connects to your server.

The plugin authenticates with `X-API-Key` and uses the server's `/search` and `/memories` routes. `api_key` is optional — omit it only for servers running with `AUTH_DISABLED`.

> Setting `host` routes to the self-hosted server automatically. Don't set `mode: oss` — OSS takes precedence and ignores `host`.

## OSS (Self-Hosted) Mode

Run Mem0 locally with your own LLM, embedder, and vector store. This is the in-process SDK mode. To instead connect to a Mem0 server you run via Docker, see [Self-Hosted Dashboard (Server) Mode](#self-hosted-dashboard-server-mode) above.

### Interactive Setup

```bash
hermes memory setup
# Select "mem0" → "Open Source (self-hosted)"
# Follow prompts for LLM, embedder, and vector store
```

### Agent-Driven Setup (Flags)

```bash
hermes memory setup mem0 --mode oss \
  --oss-llm openai --oss-llm-key sk-... \
  --oss-vector qdrant
```

### Supported Providers

| Component | Providers |
|-----------|-----------|
| LLM | openai, ollama |
| Embedder | openai, ollama |
| Vector Store | qdrant (local/server), pgvector |

### Flags Reference

| Flag | Description |
|------|-------------|
| `--mode` | `platform` or `oss` |
| `--oss-llm` | LLM provider (default: openai) |
| `--oss-llm-key` | LLM API key |
| `--oss-embedder` | Embedder provider (default: openai) |
| `--oss-vector` | Vector store (default: qdrant) |
| `--oss-vector-path` | Qdrant local path |
| `--user-id` | User identifier |

## Switching Modes

### Platform to OSS

```bash
hermes memory setup mem0 --mode oss --oss-llm-key sk-...
```

Or edit `$HERMES_HOME/mem0.json` directly:
```json
{
  "mode": "oss",
  "oss": {
    "llm": {"provider": "openai", "config": {"model": "gpt-5-mini"}},
    "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small"}},
    "vector_store": {"provider": "qdrant", "config": {"path": "~/.hermes/mem0_qdrant"}}
  }
}
```

### OSS to Platform

```bash
hermes memory setup mem0 --mode platform --api-key sk-...
```

### Dry Run (preview without writing)

```bash
hermes memory setup mem0 --mode oss --oss-llm-key sk-... --dry-run
```

## Tools

| Tool | Description |
|------|-------------|
| `mem0_search` | Semantic search by meaning |
| `mem0_add` | Store a fact verbatim (no LLM extraction) |
| `mem0_update` | Update a memory's text by ID |
| `mem0_delete` | Delete a memory by ID |

## Troubleshooting

### "Mem0 temporarily unavailable"

Circuit breaker tripped after 5 consecutive failures. Resets after 2 minutes.

- **Platform mode**: Check API key and internet connectivity.
- **OSS mode**: Check that your vector store (qdrant/pgvector) is running.

### OSS: Qdrant connection refused

```bash
# If using local Qdrant, check the storage path is writable:
ls -la ~/.hermes/mem0_qdrant

# If using Qdrant server, check it's reachable:
curl http://localhost:6333/healthz
```

### OSS: PGVector connection refused

```bash
# Verify PostgreSQL is running and accepting connections:
pg_isready -h localhost -p 5432
```

### OSS: Ollama not reachable

```bash
# Check Ollama is running:
curl http://localhost:11434/api/tags
```

### Memories not appearing

- `mem0_add` stores verbatim (no extraction). Use `sync_turn` for LLM extraction.
- Search uses semantic matching — try broader queries.
- Check `user_id` matches between sessions (`$HERMES_HOME/mem0.json`).
