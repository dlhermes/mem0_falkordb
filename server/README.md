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
  "embedder":    { "provider": "openai", "config": { "model": "...", "api_key": "sk-你的Key", "openai_base_url": "", "embedding_dims": 1536 } },
  "reranker":    { "provider": "llm_reranker", "config": { "model": "...", "api_key": "sk-你的Key", "llm": {...} } },
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

> `vector(1024)` 的维度需与 Embedder 模型输出一致。Bvoyage-4-large = 1024，text-embedding-3-small = 1536。

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

**现象**：使用 `cohere` provider 对接 SiliconFlow 原生 rerank API 时返回 400 `Input should be a valid integer`。

**根因**：Cohere Python SDK v5 的参数格式与 SiliconFlow 的 Cohere 兼容 API 不完全一致（`top_n` / `max_chunks_per_doc` 等参数被拒绝）。

**方案 A**（推荐）：用 `llm_reranker`，通过 LiteLLM 等网关调用 chat 模型做相关性打分。兼容任何 OpenAI-compatible 模型。

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

**方案 B**：直连 SiliconFlow，需调试 Cohere SDK 参数兼容性（留待后续）。

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
| `MEM0_LLM_MAX_INPUT_TOKENS` | `0`（不限制） | 单次记忆提取最大输入 token 数，超出自动分块提取并上下文传递 |

### Embedder 客户端

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_EMBEDDER_TIMEOUT` | SDK 默认 | OpenAI Embedding 客户端请求超时（秒） |
| `MEM0_EMBEDDER_MAX_RETRIES` | SDK 默认 | OpenAI Embedding 客户端最大重试次数 |
| `MEM0_EMBEDDING_DIMS` | 不设置 | Embedding 向量维度，不设置则自动检测 |
| `MEM0_EMBEDDING_BATCH_SIZE` | `100` | 批量 Embedding 每次请求最大文本条数 |

### 图存储

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_GRAPH_MAX_WORKERS` | `1` | 图写入线程池最大工作线程数 |

### 重排序

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MEM0_RERANK_TIMEOUT` | SDK 默认 | Cohere / ZeroEntropy 客户端请求超时（秒） |
| `MEM0_RERANK_MAX_RETRIES` | SDK 默认 | Cohere / ZeroEntropy 客户端最大重试次数 |
| `MEM0_RERANK_REQUEST_DELAY` | `0` | LLMReranker 逐文档调 LLM 时每次请求间隔（秒），防 RPM 限制 |

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
