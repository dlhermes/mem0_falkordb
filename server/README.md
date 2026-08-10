# Mem0 自部署 Server（Fork 版）

> 基于 mem0-graph v2.0.14.post1，带 FalkorDB 图存储支持。

本目录包含 FastAPI 后端 + Next.js Dashboard，一键 `docker compose up` 部署。

## 快速开始

### 1. 创建配置文件

复制模板并填入你的 API key：

```bash
cp config.json.example config.json
# 编辑 config.json — 替换所有 sk-你的Key 为真实 key
cp .env.example .env
# 编辑 .env — 最少设置 POSTGRES_PASSWORD 和 JWT_SECRET
```

> `config.json` 管理模型配置（LLM / Embedder / Reranker）。`.env` 管理基础设施（数据库密码、部署地址等）。
> 模型 key 请写在 `config.json` 中，不要写在 `.env` 里。

配置模板参考 `config.json.example`，结构如下：

```json
{
  "llm":         { "provider": "openai", "config": { "model": "...", "api_key": "sk-你的Key", "openai_base_url": "" } },
  "embedder":    { "provider": "openai", "config": { "model": "...", "api_key": "sk-你的Key", "openai_base_url": "" } },
  "reranker":    { "provider": "siliconflow", "config": { "model": "BAAI/bge-reranker-v2-m3", "api_key": "sk-你的Key" } },
  "graph_store": { "provider": "falkordb", "config": { "host": "falkordb", "port": 6379, "database": "mem0" } }
}
```

⚠️ 常见错误：把 `openai_base_url` 写成 `api_base` → 容器启动崩溃。把 `llm` key 写成 `vlm` → 配置被忽略。

### 2. 启动

```bash
docker compose up -d
```

等几秒让 PostgreSQL 和 alembic 完成初始化。

## 部署踩坑记录

以下为全新部署到远程服务器时遇到的典型问题及修复方案。

### 1. Dashboard 无法登录（登录后自动跳回）

**现象**：输入邮箱密码后页面刷新，无法进入后台。

**根因**：Dashboard 容器的 `secure` cookie 设置为 `true`（Next.js standalone 构建时 `NODE_ENV` 可能被 bake 为 `production`），而自部署环境通常走 HTTP（无 TLS），浏览器拒绝写入 secure cookie → 登录后 token 丢失 → 跳回登录页。

**修复**：在 dashboard 容器 environment 中设置 `DASHBOARD_URL` 环境变量，代码会自动检测协议——`http://` 时 `secure: false`。

```yaml
mem0-dashboard:
  environment:
    - DASHBOARD_URL=http://你的IP:3002
```

> 详见源码 `dashboard/src/app/api/auth/refresh/route.ts` → `shouldUseSecureCookie()`。

**预防**：compose 中 `DASHBOARD_URL` 已变量化（`${DASHBOARD_URL:-http://localhost:3002}`），部署时在 `.env` 中填入实际地址即可。

### 2. 新部署后 Dashboard 报 500（memories 表不存在）

**现象**：Dashboard 访问 Memories / Entities 页面报 500，容器日志显示 `UndefinedTable: relation "memories" does not exist`。

**根因**：pgvector 采用懒建表策略——`memories` 表仅在首次调用 `add()` 写入记忆时才通过 `create_col()` 创建。全新部署且从未写入数据时，Dashboard 直接查表 → 500。

**修复**：部署后手动在 PostgreSQL 中建表：

```bash
docker exec mem0-dev-postgres-1 psql -U postgres -d postgres -c "
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    vector vector(1024),
    payload JSONB
);
CREATE INDEX IF NOT EXISTS memories_hnsw_idx ON memories USING hnsw (vector vector_cosine_ops);
"
```

> `vector(1024)` 的维度需与 Embedder 模型输出一致。voyage-4-large = 1024，text-embedding-3-small = 1536。

**预防**：已在 `init-db.sh` 中预建表（Docker 首次初始化时自动执行）。若需手动修复，可走上方 SQL。

### 3. Docker Compose IP 硬编码问题

**现象**：`docker-compose.yaml` 中 Dashboard 的 `NEXT_PUBLIC_API_URL`、`DASHBOARD_URL`、mem0 服务的 `DASHBOARD_URL` 均为硬编码 IP。

**修复**：已变量化，改为 `${VAR:-default}` 语法：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DASHBOARD_URL` | `http://localhost:3002` | Dashboard 完整 URL |
| `API_EXTERNAL_URL` | `http://localhost:8888` | API 外部访问地址 |
| `NODE_ENV` | `development` | Next.js 运行模式 |

部署时在 `server/.env` 中填入实际地址即可。

### 4. pgvector 连接的是默认 postgres 库

**现象**：Dashboard 中无记忆，API 查询返回空，但日志未见报错。

**根因**：`docker-compose.yaml` 中 pgvector 的 `POSTGRES_DB` 未显式设置，Mem0 的 v2.0.x 将向量表创建在默认的 `postgres` 库中（非 `mem0_app`）。Alembic 管理的业务表（users/api_keys/request_logs 等）在 `mem0_app` 库，而向量存储的表在 `postgres` 库——两个库各自独立。

**说明**：这是上游设计，非 bug。了解即可，正常使用不受影响。

### 5. FalkorDB 空图现象

**现象**：部署后 FalkorDB 中已有图 `mem0_alice`，含 telemetry stream，引起疑惑。

**说明**：`mem0-falkordb` 插件在 `register()` 初始化时自动创建了 `mem0_alice` 图（空图，零节点零关系）。这是库自身的初始化行为，类似 PostgreSQL 的 `alembic_version` 表——框架元数据，非用户数据或旧部署残留。

### 6. config.json 挂载缺失

**现象**：旧版 `docker-compose.yaml` 缺少 `config.json` 挂载。

**修复**：已在 mem0 服务 volumes 中添加 `- ./config.json:/app/config.json:ro`。

### 7. config.json 字段名错误导致容器启动崩溃

**现象**：容器日志报 `TypeError: OpenAIConfig.__init__() got an unexpected keyword argument 'api_base'`，容器无法启动。

**根因**：`mem0` 的 `OpenAIConfig` 参数名是 `openai_base_url`，不是 `api_base`（openai v2 客户端用 `openai_base_url`）。配了 `api_base` 会导致 Pydantic model 初始化失败。

**修复**：将 `config.json` 中所有 LLM/Embedder/Reranker config 的 `api_base` 改为 `openai_base_url`。

```json
// ❌ 错误
{ "llm": { "config": { "api_base": "http://..." } } }
// ✅ 正确
{ "llm": { "config": { "openai_base_url": "http://..." } } }
```

### 8. LLM 配置写到了 vlm key 下

**现象**：`/configure` API 返回配置中没有 `llm` 段，LLM 回退到 `.env` 的占位符 key。

**根因**：`config.json` 的顶层 key 必须是 `llm`（mem0 识别的标准字段）。写 `vlm` 不会报错但被忽略，`_merge_config` 会将其作为未知 key 合并进配置字典但 `Memory.from_config()` 不使用该 key。

**修复**：确保 `config.json` 中 LLM 配置的 key 是 `"llm"` 而非 `"vlm"`。

### 9. VoyageAI Embedding 兼容性问题

**现象**：使用 VoyageAI 模型（如 `voyage-4-large`）时容器日志报 `BadRequestError: encoding_format: float not accepted` 或 `Argument 'dimensions' is not supported`，写入记忆失败。

**根因**：VoyageAI API 与 OpenAI 有两处不兼容：
1. `encoding_format` 只接受 `base64`，不接受 `float`；
2. 不支持 `dimensions` 参数（非 Matryoshka 模型）。

且 VoyageAI 返回 base64 编码的 embedding，pgvector 无法直接识别为 float 数组。

**修复**：`mem0/embeddings/openai.py` 已内置 VoyageAI 兼容逻辑：
- 根据 `openai_base_url` 自动检测 VoyageAI（含 `voyageai` 字符串）
- VoyageAI 自动走 `encoding_format: base64` + 跳过 `dimensions`
- `_decode_embedding()` 自动将 base64 字符串解码为 float 列表

> ⚠️ 模型名必须与 VoyageAI 实际模型名一致（如 `voyage-4-large`，非 `Bvoyage-4-large`）。

### 10. Reranker 提供器选择

**现象**：搜索时未对结果重排序，相关度不够精准。

**说明**：本 Fork 支持两种 reranker 方案：

**方案 A**（推荐 — SiliconFlow 原生 reranker）：

配置最简单，直接 HTTP 调用 SiliconFlow `/v1/rerank`，无需第三方 SDK。

```json
{
  "reranker": {
    "provider": "siliconflow",
    "config": {
      "model": "BAAI/bge-reranker-v2-m3",
      "api_key": "sk-你的Key"
    }
  }
}
```

支持通过环境变量调优超时（`MEM0_RERANK_TIMEOUT`，默认 `60`）和重试次数（`MEM0_RERANK_MAX_RETRIES`）。

**方案 B**（备选）：用 `llm_reranker`，通过兼容 OpenAI 的网关调用 chat 模型做相关性打分。兼容任何 OpenAI-compatible 模型。

```json
{
  "reranker": {
    "provider": "llm_reranker",
    "config": {
      "model": "你的模型名",
      "api_key": "sk-你的Key",
      "llm": {
        "provider": "openai",
        "config": {
          "model": "你的模型名",
          "api_key": "sk-你的Key",
          "openai_base_url": "http://你的网关:4000/v1"
        }
      }
    }
  }
}
```

同时保留上游全部 Provider：Zero Entropy、Cohere、Sentence Transformer、HuggingFace、LLM-based。详见 [docs.mem0.ai](https://docs.mem0.ai/open-source/overview)。

### 11. pgvector 维度检测 Bug（重建容器后记忆清空）

**现象**：`docker compose down && up -d` 重建容器后，所有记忆丢失，`mem0_memories` 表为空。

**根因**：`mem0/vector_stores/pgvector.py` 的 `_get_table_vector_dim` 方法中，错误地执行了 `atttypmod - 4`。pgvector 的 `atttypmod` 直接等于向量维度数，不需要减 4。导致 `_ensure_collection` 检测到 `1020 ≠ 1024`（实际是 `1024 = 1024`），误触发 `delete_col()` + `create_col()`，清空所有记忆。

**修复**：将 `return row[0] - 4` 改为 `return row[0]`。同时将 `MEM0_EMBEDDING_DIMS` 环境变量同步传递到 `DEFAULT_CONFIG["vector_store"]["config"]["embedding_model_dims"]`，确保维度一致性从 `.env` 统一管理。

> ⚠️ `.env` 中 `MEM0_EMBEDDING_DIMS` 的值必须与实际 Embedder 模型输出的向量维度一致（voyage-4-large = 1024，text-embedding-3-small = 1536）。不一致会导致写入时重建表。

### 12. 推理模型导致记忆提取为空（results=0）

**现象**：LLM 请求返回 200，但日志一直 `add pipeline complete: results=0`、`graph write skipped: no extracted memories`，任何对话都提取不出记忆。

**根因**：LLM 是「推理模型」（如自部署 llama.cpp 上的 Qwen3.5 系列、DeepSeek-R1），默认把回答放在 `reasoning_content` 字段、`content` 恒为空。mem0 的提取链路只读取 `response.choices[0].message.content`（`mem0/llms/openai.py`），拿到的永远是空字符串。

**验证方法**：直接请求 LLM 服务（带上 api_key）：
```bash
curl -s http://<llm-host>/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer <key>" \
  -d '{"model":"<model>","messages":[{"role":"user","content":"1+1"}],"max_tokens":200}'
# 若返回 message.content 为空、message.reasoning_content 有内容 → 是推理模型
```

**修复**（2026-08-04 落地）：
1. `config.json` 的 `llm.config` 追加 `"reasoning_effort": "none"`，让模型跳过思考通道直接输出 `content`；
2. `mem0/llms/base.py` 的 `_get_common_params()` 增加 `reasoning_effort` 透传——上游只在推理模型白名单（o1/o3/gpt-5 系列）内透传，白名单外模型配置了也会被丢弃。

> ⚠️ 此项仅推理模型需要，普通模型（OpenAI/GPT、Claude、DeepSeek 非 R1 版等）**无需配置**。取消方法：删除 `config.json` 中 `"reasoning_effort"` 字段即可恢复默认（代码改动无副作用）；如需还原代码，删除 `_get_common_params()` 中「Add reasoning_effort if configured」注释段。

## 性能调优

通过环境变量调优数据库连接池、HTTP 客户端超时等参数。所有变量在 `docker-compose.yaml` 中 mem0 服务的 `environment` 段或 `.env` 文件中设置。

### 数据库连接池（PostgreSQL）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_DB_POOL_SIZE` | `10` | 连接池常驻连接数 |
| `MEM0_DB_MAX_OVERFLOW` | `20` | 超出 pool_size 的最大临时连接数 |
| `MEM0_DB_POOL_RECYCLE` | `3600` | 连接最大存活时间（秒），防止 PostgreSQL 服务端断开闲置连接 |
| `MEM0_DB_POOL_TIMEOUT` | `30` | 获取连接的超时时间（秒） |

### 向量库连接池（pgvector）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_VECTOR_MINCONN` | `3` | pgvector 最小连接数 |
| `MEM0_VECTOR_MAXCONN` | `10` | pgvector 最大连接数 |

### LLM 客户端

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_LLM_TIMEOUT` | SDK 默认 | OpenAI 客户端请求超时（秒） |
| `MEM0_LLM_MAX_RETRIES` | SDK 默认 | OpenAI 客户端最大重试次数 |
| `MEM0_LLM_TEMPERATURE` | `0.2` | LLM 生成温度 |
| `MEM0_LLM_MAX_TOKENS` | `2000` | LLM 最大生成 token 数 |
| `MEM0_LLM_MAX_INPUT_TOKENS` | `0`（不限制） | 兼容旧配置。已由 `MEM0_LLM_CONTEXT_WINDOW` 取代（未设置 CONTEXT_WINDOW 时回退使用） |
| `MEM0_LLM_CONTEXT_WINDOW` | `0`（不限制） | LLM 上下文窗口总大小（n_ctx）。分块按此计算并预留输出余量，避免 chunk 逼近窗口上限被截断（旧表现为 `JSON parse failed on chunk 0` + llama.cpp 日志 `truncated=1`）。8K 显存 llama.cpp（n_ctx=16384）建议设 16384。**依赖 tiktoken**（requirements.txt 已含）：容器无 tiktoken 时估算 fallback `len//4`，对中文严重低估（约 45%），分块会偏大 |

### Embedder 客户端

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_EMBEDDER_TIMEOUT` | SDK 默认 | OpenAI Embedding 客户端请求超时（秒） |
| `MEM0_EMBEDDER_MAX_RETRIES` | SDK 默认 | OpenAI Embedding 客户端最大重试次数 |
| `MEM0_EMBEDDING_DIMS` | 不设置 | Embedding 向量维度（同时设置到 `embedder.config.embedding_dims` 和 `vector_store.config.embedding_model_dims`）。不设置则从模型自动检测 |
| `MEM0_EMBEDDING_BATCH_SIZE` | `100` | 批量 Embedding 每次请求最大文本条数 |

### 图存储

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_GRAPH_MAX_WORKERS` | `5` | 图写入线程池最大工作线程数（图实体提取并发数，1 = 串行） |
| `MEM0_GRAPH_SEARCH_WORKERS` | `2` | 图搜索线程池最大工作线程数（与写池分离，批量写入时写任务不阻塞搜索） |
| `MEM0_GRAPH_SEARCH_TOKENS` | `0`（不限制） | 参与图搜索的 token 数量上限。设置后限制分词 token 数减少串行查询；默认不限制。图数据用独立 embedder 时通常不需要此限制，与 voyageai 共用时可设 15-25 控制 embed 输入规模 |
| `MEM0_GRAPH_THRESHOLD` | `0.7` | 图搜索相似度阈值（0-1，env 优先级最高，config.json `graph_store.threshold` 次之） |

### 重排序

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_RERANK_TIMEOUT` | `60` | SiliconFlow/Cohere/ZeroEntropy 客户端请求超时（秒） |
| `MEM0_RERANK_MAX_RETRIES` | `3` | SiliconFlow/Cohere/ZeroEntropy 客户端最大重试次数 |
| `MEM0_RERANK_REQUEST_DELAY` | `0` | SiliconFlow 分批请求 / LLMReranker 逐文档调 LLM 时的请求间隔（秒），防 RPM 限制 |

### 记忆衰减

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_ENABLE_DECAY` | `false` | `true` 时启用搜索时指数衰减 |
| `MEM0_DECAY_HALF_LIFE_DAYS` | `30` | 半衰期天数，`importance=5` 的记忆豁免 |

### 记忆清理

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEMORY_RETENTION_DAYS` | `0` | 超期记忆删除天数（0 = 仅清除设了 expiration_date 的记忆） |
| `PRUNE_DRY_RUN` | `false` | `true` 时只报告不删除 |

### 定期合并

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CONSOLIDATION_DRY_RUN` | `false` | `true` 时只报告不合并 |
| `CONSOLIDATION_MIN_GROUP` | `3` | 触发合并的最小记忆条数 |

示例 `.env` 配置：

```bash
MEM0_DB_POOL_SIZE=20
MEM0_DB_MAX_OVERFLOW=40
MEM0_LLM_TIMEOUT=120
MEM0_LLM_TEMPERATURE=0.1
MEM0_LLM_MAX_TOKENS=8000
MEM0_LLM_MAX_INPUT_TOKENS=32000
MEM0_EMBEDDING_BATCH_SIZE=50
MEM0_RERANK_TIMEOUT=60
MEM0_RERANK_REQUEST_DELAY=0.5
```

> ⚠️ **修改 `.env` 后，必须重建容器才能生效。** `docker compose restart` 不会重新读取 `env_file:` —— 容器的环境变量在创建时固化。
>
> 正确操作：
>
> ```bash
> # 只重建 mem0 容器（不碰 postgres/falkordb/dashboard）
> docker compose up -d --force-recreate mem0
> ```
>
> 也可以用 `docker compose up -d`（Compose 自动检测 `.env` 变化后重建）。

### 3. 获取管理员凭据

Server 容器启动时**自动创建**管理员账号。查看容器日志：

```bash
docker compose logs mem0 | grep -E "(admin|密码)"
```

日志中会打印：

```
👤 Admin user created:
   Email: admin@mem0.dev
   Password: <随机生成的密码>
```

直接用这个邮箱和密码登录，不需要手动创建管理员。

### 4. 打开 Dashboard

浏览器访问 `http://你的IP:3002`，用日志中的 admin 凭据登录。

## 管理命令

```bash
# 查看日志
docker compose logs -f

# 停止
docker compose down

# 清空所有数据（删 PostgreSQL 卷）
docker compose down -v
```

## 重置密码

```bash
docker exec -it mem0-mem0-1 python3 /app/scripts/reset_admin_password.py
```

## 日志清理

`request_logs` 表只增不减，定期清理：

```bash
docker exec -it mem0-mem0-1 python3 /app/scripts/prune_request_logs.py
```

## 记忆清理

过期记忆和 FalkorDB 孤立节点自动清理（每日凌晨 4:00 由 cron 触发）。也可手动执行：

```bash
# 干跑（只报告不删除）
docker exec -e PRUNE_DRY_RUN=true -e MEM0_CONFIG_PATH=/app/config.json -e MEMORY_RETENTION_DAYS=180 mem0-dev-mem0-1 python3 /app/prune_expired_memories.py

# 实际执行
docker exec -e MEM0_CONFIG_PATH=/app/config.json -e MEMORY_RETENTION_DAYS=180 mem0-dev-mem0-1 python3 /app/prune_expired_memories.py
```

## 记忆合并

碎片记忆按实体分组，≥3 条时自动合并为精简事实（每日凌晨 5:00 由 cron 触发）。手动执行：

```bash
# 干跑
docker exec -e CONSOLIDATION_DRY_RUN=true -e MEM0_CONFIG_PATH=/app/config.json mem0-dev-mem0-1 python3 /app/consolidate_memories.py

# 实际执行
docker exec -e MEM0_CONFIG_PATH=/app/config.json mem0-dev-mem0-1 python3 /app/consolidate_memories.py
```

## 矛盾检测

写入时实时判定，复用 LLM 提取调用。默认关闭，开启方式：

```bash
# 在 .env 中添加
echo "MEM0_ENABLE_CONTRADICTION=true" >> /data/mem0-push/server/.env

# 重建容器生效
cd /data/mem0-push/server && docker compose up -d --force-recreate mem0
```

开启后，Agent 写入记忆时发现矛盾（如先存"喜欢咖啡"后说"讨厌咖啡"）→ 自动 DELETE 旧记忆。所有变更记录在 history 表可追溯。

## 时间推理

LLM 在提取记忆时自动标注时间属性，写入 metadata 的 `temporal` 和 `temporal_date` 字段：

- **`temporal`** — 时间类型：`PAST`（过去）、`PRESENT`（现在/当前）、`FUTURE`（未来/计划）、`TIMELESS`（无时效通用知识）
- **`temporal_date`** — 具体日期（ISO 格式，如 `2026-07-30`），无法推断时省略

**过滤方式：**

```bash
# 搜索时按 temporal 筛选（通过 metadata filter，值需大写）
curl -s -X POST http://localhost:8080/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "...", "filters": {"user_id": "alice", "temporal": "FUTURE"}}'
```

## 搜索深度路由

`/search` 端点新增可选参数 `depth`（minimal/standard/full）：

- `minimal` — 跳过全部检索（命中废话白名单时）
- `standard` — 仅向量+BM25，跳过图查询和 rerank
- `full` — 完整检索（默认值，行为不变）

**启用方式：** `config.json` 中设置 `enable_search_depth: true`（模板已默认开启）。未设置时所有查询走 `full` 深度，无降本效果。`MEM0_SEARCH_DEPTH_AUTO=true`（环境变量，默认 true）控制是否自动判定深度，关闭后可手动通过 `depth` 参数指定。

关键词管理：通过 `search_keywords` 表（SQLite）管理，`INSERT` 即生效，无需重启。

```bash
# 查看当前词表
docker exec mem0-dev-mem0-1 sqlite3 /root/.mem0/history.db \
  "SELECT * FROM search_keywords ORDER BY category, keyword"

# 添加 minimal 拦截词
docker exec mem0-dev-mem0-1 sqlite3 /root/.mem0/history.db \
  "INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '收到', 'exact', 'zh')"
```

## 记忆衰减（含 Lane 分轨）

LLM 提取记忆时自动判断 `importance` 和 `lane`，一条 `MEM0_ENABLE_DECAY=true` 启用全部：

**启用方式：** `config.json` 中设置 `enable_lane: true`（模板已默认开启），开启后 LLM 未输出 lane 时按关键词自动分轨。`MEM0_ENABLE_DECAY=true`（环境变量）开启搜索时的指数衰减加权。

| 档位 | half_life | 触发条件 |
|------|-----------|---------|
| 永不衰减 | ∞ | `importance=5` |
| 慢衰减 | ~100天 | `lane=slow` / 关键词含"踩坑/报错/步骤/流程" |
| 正常衰减 | ~30天 | 兜底（无 lane / 存量记忆） |
| 快衰减 | ~20天 | `lane=fast` / 关键词含"开心/心情/今天" |

存量记忆无 lane 字段 → normal 行为，零变化。

### importance 关键词兜底

LLM 未输出 `importance` 时按关键词自动判断（Phase 2.6，sync/async 双路径）：

| 分值 | 判断 | 关键词示例 |
|------|------|-----------|
| 5 | 高价值信号命中 | 发哥 / 偏好 / 部署 / 配置 / 姓名 / 住在 |
| 2 | 低价值信号命中（优先判断） | 测试 / 验证 / 查询 / 建议 / 待办 / 需配置 / 处理顺序 |
| 3 | 兜底 | 其余 |

低价值优先判断——含「需配置 X」的方案建议类文本判 2 而非 5，防止污染记忆永不衰减。

## Rerank 联合过滤（方案 D）

`depth=full` 时 rerank 完成后按双阈值过滤（`mem0/memory/main.py`）：

| 通道 | 保留条件 | 环境变量 |
|------|---------|---------|
| rerank | `rerank_score >= 0.4` | `MEM0_RERANK_SCORE_THRESHOLD`（默认 0.4） |
| 向量兜底 | `vector score >= 0.5`（图碎片无向量分，不适用） | `MEM0_VECTOR_SCORE_FALLBACK`（默认 0.5，0=关闭） |

过滤仅在 rerank 实际执行后生效（`_rerank_applied` 守卫）——`rerank=False` 时不再误杀全部结果。

## 图碎片方案 C（图关联补充召回，v2 重构后）

图搜索返回的实体关系碎片（如「发哥 部署于 10.200.1.163」）**参与 rerank 竞争**，与向量结果统一由 reranker 按 query 相关性打分排序：

- **关系类型存储**：纯中文关系类型经 backtick 转义直接写入（`部署于`、`偏好`），不再映射英文（909705c 的 52 条中文→英文映射表已删除，见 `mem0/memory/utils.py` `sanitize_relationship_for_cypher`）
- **召回通道**：
  - 向量通道：节点 embedding 相似度召回，`recall_channel=vector`
  - 前缀通道：query token（含同义词扩展）对关系类型做 `STARTS WITH` 前缀匹配，`recall_channel=contains`——动词原形「部署」可命中「部署于」，否定前缀（不/未/没 开头）天然排除
- **rerank 阈值豁免**：前缀通道命中的图碎片即使 rerank 分低于阈值也保留（reranker 对同义词关系如「喜欢↔偏好」可能不认识，但前缀匹配已确认相关），仅影响过滤不影响排序
- **排序**：统一按 `rerank_score` 降序，图碎片与向量结果交错排列，分数高者在前；同分时前缀命中碎片优先
- 拼句优先用中文关系名（`relation_cn` 属性，如「部署于」），无则回退 `- {type} ->` 格式

## 显式反馈闭环

记忆系统支持**显式反馈闭环**：对话层捕获用户纠正信号后，通过 `POST /evolve/feedback` 直接调整对应记忆的热度（salience）分（useful +0.1 / useless -0.15 / correction -0.05，clamp 到 [0.05, 1.0]），只改热度不改记忆内容。反馈可审计（evolve_feedback / evolve_salience_adjustments 落库），误报可逆。

## 本地访问地址

- Dashboard: `http://localhost:3002`
- API: `http://localhost:8888`
- OpenAPI 文档: `http://localhost:8888/docs`

## Dashboard 功能

登录后可访问：

- **Requests** — API 调用审计日志
- **Memories** — 浏览和搜索记忆
- **Entities** — 用户/Agent/会话列表及计数
- **API Keys** — 创建和管理 API Key
- **Configuration** — 查看当前 Provider 配置
- **Settings** — 修改密码和个人信息

## 安全

- Dashboard 使用 JWT 登录
- API 使用 `X-API-Key` 头鉴权
- Auth 默认开启，本地开发可设 `AUTH_DISABLED=true`
- Dashboard 自动设置 `X-Frame-Options: DENY`、`CSP: frame-ancestors 'none'` 等安全头

## 遥测

默认开启（与 mem0 OSS 一致），发送至匿名 PostHog。设 `MEM0_TELEMETRY=false` 可关闭。

## 参考

更多文档见 [docs.mem0.ai](https://docs.mem0.ai/open-source/overview) 和项目根目录 [README.md](../README.md)。
