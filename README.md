# mem0 + FalkorDB = 图增强记忆层

> **基于 [mem0ai/mem0](https://github.com/mem0ai/mem0) v2.0.14 的 Fork** — 回迁了 v2.0.0 起被移除的 `graphs/` 模块，通过 [mem0-falkordb](https://github.com/FalkorDB/mem0-falkordb) 插件恢复外部图数据库集成。

## 为什么需要这个 Fork

### 上游做了什么

mem0 OSS v2.0.0 移除了外部图数据库支持。`mem0/graphs/` 整个模块——接口定义、工厂类、Provider 注册机制、LLM 工具 Schema、实体提取提示词——连同 Neo4j、Kuzu、Memgraph、Apache AGE、Neptune 等图存储后端全部删除。

**后果**：自 v2.0.0 起，开源用户无法在 mem0 中使用任何外部图数据库。实体关系、知识图谱、实体链接等功能仅限云端 Platform 版。

### 本 Fork 解决了什么

我们恢复了图存储接口层，并在此基础上修复了上游的多个部署痛点：

| 维度 | 上游 mem0 v2.0.14 | 本 Fork |
|------|------------------|---------|
| **图存储** | ❌ 已删除整个 `graphs/` 模块 | ✅ 完整恢复，含配置、工厂、LLM schema、实体提取 |
| **图数据库后端** | ❌ 无 | ✅ FalkorDB（775 行 Cypher 翻译 + 向量索引） |
| **实体关系** | ❌ 独立实体无连接 | ✅ 实体节点 + 关系边 + 引用计数 + 跨用户隔离 |
| **搜索增强** | 纯向量 + BM25 | ✅ 向量 + BM25 + 图关系合并（`search()` 附带实体关系） |
| **pgvector 维度** | 硬编码 1536 | ✅ 自动检测（切换 Embedder 模型自适应） |
| **Provider 配置** | 需调 `/configure` API | ✅ `MEM0_CONFIG_PATH=/app/config.json` 即可 |
| **生产部署** | 需手动注册 admin | ✅ 启动自动创建 admin@mem0.dev |
| **性能调优** | 硬编码或不可配 | ✅ 18 个环境变量全覆盖（连接池/HTTP超时/批量/并发） |
| **Docker 开箱** | 依赖手动安装系统包 | ✅ Dockerfile 预装 libpq5 |
| **长消息内存** | 超长消息一次性传入 | ✅ `MEM0_LLM_MAX_INPUT_TOKENS` 自动分块提取 |
| **Reranker 重排序** | SDK 有、Server API 未启用 | ✅ Server `/search` API 支持 rerank 参数，配置后自动生效 |
| **中文记忆提取** | 英文 Prompt → 英文事实 | ✅ 全中文 system prompt（记忆+图实体+图关系三链路汉化），`sanitize_relationship_for_cypher` 支持 CJK |
| **VoyageAI Embedder** | 仅 OpenAI 兼容 | ✅ 自动检测 `voyageai` base_url → `encoding_format: base64` + 跳过 `dimensions` + base64 解码 |
| **SiliconFlow Reranker** | 无原生支持 | ✅ 新增 `siliconflow` provider，HTTP 直连 `/v1/rerank`，无需 Cohere SDK |
| **mem0-falkordb 内置** | pip 安装，不兼容中文 Cypher 标签 | ✅ Vendor 到 `mem0/graphs/falkordb/`，entity/relation name 自动 sanitize 为 ASCII |

## 架构

```
┌─────────────────────────────────────────────────┐
│                  AI Agent                        │
│         add() / search() / delete()              │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              Mem0 SDK v2.0.14 + graphs           │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ 向量存储  │  │ 实体存储   │  │ 图存储       │  │
│  │          │  │           │  │ (已恢复)     │  │
│  └──────────┘  └───────────┘  └──────┬───────┘  │
│                                      │           │
│                           GraphStoreFactory     │
│                           provider_to_class     │
└──────────────────────────────────┬─────────────┘
                                   │ 自动注册
┌──────────────────────────────────▼─────────────┐
│      mem0/graphs/falkordb/ (Vendor 内置)       │
│  ┌──────────────────────────────────────────┐  │
│  │  MemoryGraph (775 行)                     │  │
│  │  - FalkorDB Cypher（向量索引、实体合并）   │  │
│  │  - 每用户独立图隔离                        │  │
│  │  - 引用计数 / 实体链接                     │  │
│  └──────────────────────────────────────────┘  │
└──────────────────────┬─────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────┐
│              FalkorDB（图数据库）               │
│  真正的 Cypher 图 — 可遍历、可查询              │
└────────────────────────────────────────────────┘
```

> **Server 容器启动时自动创建 admin 用户（`admin@mem0.dev` + 随机密码），无需手动注册。查看容器日志即可获取凭据。FalkorDB Web UI 端口为 `3003`。**

## 📖 FalkorDB 图存储集成

> 本 Fork 恢复了 graph_store 接口层，FalkorDB 图存储实现已 Vendor 内置在 `mem0/graphs/falkordb/`，无需额外 pip 依赖。

详细的集成配置、Cypher 翻译对照、验证方法请参阅 → **[docs/falkordb-integration.md](docs/falkordb-integration.md)**

简而言之：

```python
from mem0.graphs.falkordb import register
register()  # ⚠️ 必须在 Memory.from_config() 之前调用

config = {
    "graph_store": {
        "provider": "falkordb",
        "config": {"host": "localhost", "port": 6379, "database": "mem0"},
    },
    # ... llm / embedder / vector_store ...
}
m = Memory.from_config(config)
```

## 快速开始

### Server 部署（推荐）

自带 FastAPI 后端 + Next.js Dashboard，启动后浏览器直接使用。

```bash
git clone https://github.com/dlhermes/mem0_falkordb.git
cd mem0_falkordb/server
```

**第一步：创建配置文件**

`config.json` 管理所有模型配置（LLM / Embedder / Reranker / Graph Store）。复制 `server/config.json.example` 并填入你的 API key。示例：

```bash
cp server/config.json.example server/config.json
# 编辑 config.json，替换 sk-你的Key 为真实 key
```

配置文件结构（详见 `server/config.json.example`）：

```json
{
  "llm":         { "provider": "openai", "config": { "model": "...", "api_key": "sk-你的Key", "openai_base_url": "" } },
  "embedder":    { "provider": "openai", "config": { "model": "...", "api_key": "sk-你的Key", "openai_base_url": "" } },
  "reranker":    { "provider": "siliconflow", "config": { "model": "BAAI/bge-reranker-v2-m3", "api_key": "sk-你的Key" } },
  "graph_store": { "provider": "falkordb", "config": { "host": "falkordb", "port": 6379, "database": "mem0" } }
}
```

> ⚠️ LLM 配置的 `openai_base_url` 字段**不是** `api_base`，填错会导致容器启动崩溃。

**第二步：创建环境变量**

复制 `server/.env.example` 并填入基础设施配置（模型配置不要放这里）：

```bash
cp server/.env.example server/.env
```

`.env` 只需设置以下内容（其他可用默认值）：

```bash
POSTGRES_PASSWORD=改一个密码
JWT_SECRET=随机字符串至少32位
DASHBOARD_URL=http://你的服务器IP:3002
API_EXTERNAL_URL=http://你的服务器IP:8888
MEM0_CONFIG_PATH=/app/config.json
```

```bash
docker compose up -d
```

> `DASHBOARD_URL` 必须用 `http://`，不能用 `https://`，否则 Dashboard 的 Cookie 会被浏览器拒绝。

> 启动后可调整数据库连接池、LLM/Embedder 超时等参数以优化性能，详见 [server/README.md#性能调优](server/README.md#性能调优)。


**第三步：获取管理员凭据**

Server 容器启动时自动创建管理员。查看日志获取凭据：

```bash
docker compose logs mem0 | grep -E "(admin|密码)"
```

日志中打印 `admin@mem0.dev` 和随机密码。

**第四步：打开 Dashboard**

浏览器访问 `http://你的服务器IP:3002`，用日志中打印的凭据登录。无需手动创建管理员。

### 仅使用 Python SDK

如果只需要 SDK，不需要 Dashboard：

```bash
git clone https://github.com/dlhermes/mem0_falkordb.git
cd mem0_falkordb
pip install build --break-system-packages
python3 -m build --wheel
pip install dist/mem0_graph-*.whl --break-system-packages
pip install falkordb --break-system-packages
docker run -d --rm -p 6379:6379 falkordb/falkordb
```

```python
from mem0.graphs.falkordb import register
register()  # 必须在 Memory.from_config() 之前调用

from mem0 import Memory

config = {
    "graph_store": {
        "provider": "falkordb",
        "config": {"host": "localhost", "port": 6379, "database": "mem0"},
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {"host": "localhost", "port": 6333},
    },
    "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
    "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small"}},
}

m = Memory.from_config(config)
m.add("我喜欢披萨", user_id="alice")

# 图关系会通过 FalkorDB 自动创建
results = m.search("alice 喜欢什么？", user_id="alice")
```

> 如果在虚拟环境中安装，去掉 `--break-system-packages` 参数。

## 相比上游的改进

### 图存储恢复（最核心）

上游 v2.0.0 整个删除了 `mem0/graphs/` 模块——接口定义、工厂类、LLM 工具 Schema、实体提取提示词全部移除。本 Fork 完整恢复：

| 模块 | 说明 |
|------|------|
| `mem0/graphs/` (5 文件) | `__init__`、`configs`（GraphStoreConfig）、`memory`（MemoryGraph 基类）、`tools`（LLM 实体提取 JSON Schema）、`utils`（辅助函数） |
| `GraphStoreFactory` | 带 Provider 注册机制的工厂类，通过 `provider_to_class` 字典动态加载图存储后端 |
| `MemoryConfig.graph_store` | 将 `graph_store` 字段添加到顶层配置，支持 `provider` + `config` 子配置 |

**价值**：自 v2.0.0 起，开源用户无法在 mem0 中使用图数据库。本 Fork 恢复了该能力，使实体关系、知识图谱等图增强功能在开源版可用。

### FalkorDB 图数据库集成

通过 [mem0-falkordb](https://github.com/FalkorDB/mem0-falkordb) 插件（775 行），FalkorDB 作为图存储后端接入：

- **Cypher 操作**：`CREATE/MERGE/MATCH` 节点、关系、索引
- **向量索引**：通过 FalkorDB 的 VSS 扩展实现嵌入向量存储与检索
- **实体合并**：节点融合逻辑（名称+类型去重）
- **引用计数**：关系边带 `count` 属性追踪引用频率
- **每用户独立图隔离**：通过 `user_id` 前缀自动分区

### pgvector 维度自动检测

上游硬编码向量维度为 1536（OpenAI `text-embedding-3-small` 默认值）。本 Fork 修改 `mem0/configs/vector_stores/pgvector.py`，首次建表时通过 `select statement` 探测 Embedder 实际返回维度，自动适配。

**价值**：切换 Embedder 模型（如换成 1024 维的 `BAAI/bge-m3`）无需手动修改数据库 Schema。

### Provider 配置文件

上游 Server 部署后必须通过 `/configure` API 或浏览器 Wizard 来配置 LLM/Embedder Provider。本 Fork 支持 `MEM0_CONFIG_PATH` 环境变量指向 JSON 配置文件，容器启动时自动加载。

**价值**：纯配置文件驱动部署，无需调 API 或跑 Wizard。CI/CD、IaC 等自动化场景直接读取 JSON。

### 自动管理员创建

上游部署后需要手动注册管理员。本 Fork 的 Server 容器启动时自动创建 `admin@mem0.dev` + 随机密码，并在日志中打印凭据。

**价值**：去掉 Wizard 注册步骤，`docker compose up -d` 后直接登录使用。

### 生产级性能调优

上游几乎不可配。本 Fork 暴露 18 个环境变量覆盖全链路：

| 类别 | 变量数 | 覆盖范围 |
|------|--------|---------|
| 数据库连接池 | 4 | `POOL_SIZE`、`MAX_OVERFLOW`、`POOL_RECYCLE`、`POOL_TIMEOUT` |
| LLM HTTP 客户端 | 4 | `TEMPERATURE`、`MAX_TOKENS`、`TIMEOUT`、`MAX_RETRIES` |
| Embedder HTTP 客户端 | 4 | `DIMS`、`BATCH_SIZE`、`TIMEOUT`、`MAX_RETRIES` |
| Reranker | 3 | `TIMEOUT`、`MAX_RETRIES`、`REQUEST_DELAY` |
| 长消息处理 | 1 | `MAX_INPUT_TOKENS`（超出自动分块） |
| 图处理 | 1 | `MAX_WORKERS`（实体提取并发数） |
| 向量库连接池 | 2 | `VECTOR_MINCONN`、`VECTOR_MAXCONN` |

详见 [server/README.md#性能调优](server/README.md#性能调优)。

### 中文记忆全链路汉化

上游的 system prompt 全部英文，中文输入会被 LLM 翻译成英文事实存储。本 Fork 全链路汉化：

| 链路 | Prompt 位置 | 改动 |
|------|-----------|------|
| 记忆事实提取 | `mem0/configs/prompts.py` `ADDITIVE_EXTRACTION_PROMPT` | 中文化 + JSON 输出格式保留 |
| 图实体检测 | `mem0/graphs/falkordb/graph_memory.py` | 中文 system prompt + tool call 指令 |
| 图关系提取 | `mem0/graphs/utils.py` `EXTRACT_RELATIONS_PROMPT` | 中文化 + 语言强制指令 |
| Cypher 安全 | `mem0/memory/utils.py` `sanitize_relationship_for_cypher` | CJK 字符 fallback → underscore → 空值兜底 `related_to` |
| 图标签安全 | `mem0/graphs/falkordb/graph_memory.py` `_add_entities` | entity_type / relationship 自动 ASCII sanitize（FalkorDB 标签仅支持 ASCII）|
| CJK BM25 分词 | `mem0/graphs/falkordb/graph_memory.py` `_tokenize_cjk` | jieba 词级切分 + 非中文空格切分，BM25 关键词匹配精度提升 |

### VoyageAI Embedding 兼容

VoyageAI API 与 OpenAI 有三处不兼容：`encoding_format` 只接受 `base64`、不支持 `dimensions` 参数、返回 base64 编码向量。`mem0/embeddings/openai.py` 已自动检测 `openai_base_url` 中的 `voyageai` 并适配：

```python
# 自动检测 → base64 编码 + 跳过 dimensions + struct.unpack 解码
_is_voyage = "voyageai" in (self.config.openai_base_url or "")
```

### Docker 生产就绪

上游的 Dockerfile 未预装 PostgreSQL 客户端库，首次构建会因 `psycopg` 编译失败。本 Fork 的 `server/dev.Dockerfile` 预装 `libpq5`，开箱即用。

### Server Reranker 重排序

上游的 Server API 虽然 SDK 层支持 reranker，但 `/search` 端点从未传递 `rerank` 参数——配了也用不上。本 Fork 修复了这个问题：

- `POST /search` 新增 `rerank` 字段（可选布尔值）
- 显式传 `rerank=true/false` → 按指定执行
- 不传但 `config.json` 中配置了 reranker → **自动启用**
- 未配置 reranker → 保持原行为，无额外开销

**新增 SiliconFlow 原生 reranker**（`siliconflow` provider），直接 HTTP 调用 `/v1/rerank`，无需第三方 SDK：

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

同时保留上游全部 Provider：Zero Entropy、Cohere、Sentence Transformer、HuggingFace、LLM-based。详见 [server/README.md#10-reranker-提供器选择](server/README.md#10-reranker-提供器选择)。

## 环境要求

- Python 3.10-3.12
- Docker（运行 FalkorDB + PostgreSQL）
- FalkorDB ≥ 1.6.0（图数据库，Docker 运行）
- mem0-falkordb 已 Vendor 到 mem0/graphs/falkordb/，无需额外 pip 安装

## 许可证

Apache 2.0 — 与上游 [mem0ai/mem0](https://github.com/mem0ai/mem0) 一致。
