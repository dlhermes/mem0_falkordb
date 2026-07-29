# mem0 + FalkorDB = 图增强记忆层

> **基于 [mem0ai/mem0](https://github.com/mem0ai/mem0) v2.0.14 的 Fork** — 回迁了 v2.0.0 起被移除的 `graphs/` 模块，内置 FalkorDB 图存储集成。补齐了自部署场景下缺失的记忆衰减、cron 清理等生产级能力。

## 为什么需要这个 Fork

### 上游做了什么

mem0 OSS v2.0.0 移除了外部图数据库支持。`mem0/graphs/` 整个模块——接口定义、工厂类、Provider 注册机制、LLM 工具 Schema、实体提取提示词——连同 Neo4j、Kuzu、Memgraph、Apache AGE、Neptune 等图存储后端全部删除。

**后果**：自 v2.0.0 起，开源用户无法在 mem0 中使用任何外部图数据库。实体关系、知识图谱、实体链接等功能仅限云端 Platform 版。

### 本 Fork 解决了什么

我们恢复了图存储接口层，并在此基础上修复了上游的多个部署痛点：

| 维度 | 上游 mem0 v2.0.14 | 本 Fork |
|:-----|:------------------|:---------|
| **图存储** | ❌ 已删除整个 `graphs/` 模块 | ✅ 完整恢复，含配置、工厂、LLM schema、实体提取 |
| **图数据库后端** | ❌ 无 | ✅ FalkorDB（775 行 Cypher 翻译 + 向量索引） |
| **实体关系** | ❌ 独立实体无连接 | ✅ 实体节点 + 关系边 + 引用计数 + 跨用户隔离 |
| **搜索增强** | 纯向量 + BM25 | ✅ 向量 + BM25 + 图关系合并（`search()` 附带实体关系） |
| **pgvector 维度** | 硬编码 1536 | ✅ 自动检测（切换 Embedder 模型自适应） |
| **Provider 配置** | 需调 `/configure` API | ✅ `MEM0_CONFIG_PATH=/app/config.json` 即可 |
| **生产部署** | 需手动注册 admin | ✅ 启动自动创建 admin@mem0.dev |
| **性能调优** | 硬编码或不可配 | ✅ 22 个环境变量全覆盖（连接池/HTTP超时/批量/并发/衰减/清理） |
| **Docker 开箱** | 依赖手动安装系统包 | ✅ Dockerfile 预装 libpq5 |
| **长消息内存** | 超长消息一次性传入 | ✅ `MEM0_LLM_MAX_INPUT_TOKENS` 自动分块提取 |
| **Reranker 重排序** | SDK 有、Server API 未启用 | ✅ Server `/search` API 支持 rerank 参数，配置后自动生效 |
| **中文记忆提取** | 英文 Prompt → 英文事实 | ✅ 全中文 system prompt（记忆+图实体+图关系三链路汉化） |
| **VoyageAI Embedder** | 仅 OpenAI 兼容 | ✅ 自动检测 `voyageai` base_url → `encoding_format: base64` + 跳过 `dimensions` + base64 解码 |
| **SiliconFlow Reranker** | 无原生支持 | ✅ 新增 `siliconflow` provider，HTTP 直连 `/v1/rerank` |
| **FalkorDB 内建集成** | 需 `register()` 补丁激活 | ✅ `GraphStoreFactory` + `GraphStoreConfig` 内置，即配即用 |
| **记忆衰减** | ❌ 无 | ✅ `MEM0_ENABLE_DECAY=true` 启用，半衰期可配，`importance=5` 豁免，Lane 分轨（slow/normal/fast三段速度） |
| **cron 过期清理** | ❌ 无 | ✅ 每日自动清理过期记忆 + FalkorDB 孤立节点，保留天数可配 |
| **时间推理** | ❌ 无 | ✅ LLM 提取时自动标注 PAST/PRESENT/FUTURE/TIMELESS，metadata 过滤 |
| **定期合并** | ❌ 无 | ✅ cron 按实体分组，LLM 合并 3+ 碎片为精炼事实 |
| **矛盾检测** | ❌ 无 | ✅ `MEM0_ENABLE_CONTRADICTION=true` 启用，写入时实时判定矛盾，自动 DELETE 旧记忆 |
| **搜索深度路由** | ❌ 无 | ✅ 三级深度（minimal/standard/full），自动识别废话跳过检索，降本 40-60%。`MEM0_SEARCH_DEPTH_DEFAULT=full` 确保零行为变化 |
| **用户纠正感知** | ❌ 无 | ✅ 检测"不对/记错了"等纠正信号→自动降 threshold、扩 top_k、强制 full depth。Agent 能自我纠正 |

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

> 本 Fork 已将 FalkorDB 直接编译进 `GraphStoreFactory`，无需 `register()` 补丁。配置 `graph_store.provider="falkordb"` 即可使用。

详细的集成配置、Cypher 翻译对照、验证方法请参阅 → **[docs/falkordb-integration.md](docs/falkordb-integration.md)**

简而言之：

```python
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
|| CJK BM25 分词 | `mem0/graphs/falkordb/graph_memory.py` `_tokenize_cjk` | jieba 词级切分 + 非中文空格切分，BM25 关键词匹配精度提升 |
|| spaCy 英文 NLP | `mem0/utils/spacy_models.py` | 英文实体提取 + 词形还原。中英混杂场景需安装：`pip install spacy && python -m spacy download en_core_web_sm` |

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

### 记忆衰减

上游无此功能。本 Fork 在搜索 pipeline 中增加了指数衰减 + Lane 分轨：

```
score' = score × 0.5 ** (age_days / (half_life × lane_multiplier))
```

一条配置 `MEM0_ENABLE_DECAY=true` 启用所有衰减行为。**LLM 和关键词两种方式自动分档，无需人工干预：**

| 档位 | half_life | 触发条件 | 示例记忆 |
|------|-----------|---------|---------|
| 永不衰减 | ∞ | LLM 判 `importance=5` | "发哥用中文沟通" |
| 慢衰减 | ~100 天 | LLM 判 `lane=slow` / 关键词含"踩坑/报错/步骤/流程/配置" | "部署先装libpq5" |
| 正常衰减 | ~30 天 | 兜底（LLM 未判、关键词未命中、存量记忆） | "Python os.walk用法" |
| 快衰减 | ~20 天 | LLM 判 `lane=fast` / 关键词含"开心/心情/今天/临时" | "今天心情不错" |

**配置：**

```yaml
MEM0_ENABLE_DECAY=true              # 启用衰减（默认关）
MEM0_DECAY_HALF_LIFE_DAYS=30        # 基准半衰期
```

### 用户纠正感知

用户说"不对/记错了/应该是"等纠正信号时，搜索自动放宽参数让旧记忆进入候选，Agent 能自我纠正：

```
search("不对，发哥喜欢喝咖啡")
  → 命中 correction 关键词（27条种子词）
  → threshold 降至 0.1（默认0.3）
  → top_k 扩至 30（默认10-20）
  → depth=full（强制全套检索）
```

配置：

```yaml
MEM0_CORRECTION_MODE=true           # 启用纠正感知（默认关）
MEM0_CORRECTION_THRESHOLD=0.1       # 放宽后的相似度阈值
MEM0_CORRECTION_TOP_K=30            # 放宽后返回数量上限
```

### cron 过期清理

上游无此功能。本 Fork 提供自动清理脚本 + Hermes cronjob：

- 每日凌晨 4:00 自动执行
- `MEMORY_RETENTION_DAYS=180` 超期天数（默认 0 = 仅清除显式过期记录）
- `PRUNE_DRY_RUN=true` 干跑模式
- 同时清理 FalkorDB 孤立实体节点
- 用户列表从向量存储 payload 自动发现

### 时间推理

上游无此功能。本 Fork 修改了 LLM 提取 prompt，每条记忆自动标注时间属性：

- LLM 输出 `metadata.temporal` — PAST / PRESENT / FUTURE / TIMELESS
- LLM 输出 `metadata.temporal_date` — 有明确日期时同时输出 ISO 日期
- 搜索时可通过 `filters: {"metadata.temporal": "FUTURE"}` 过滤
- 代码改动：`prompts.py`（LLM 输出格式）、`main.py`（metadata 合并）
- 零额外 LLM 调用——在已有提取请求中附带

### 定期合并

上游无此功能。本 Fork 提供脚本 + cronjob，自动将碎片记忆合并为精简事实：

- 每日凌晨 5:00 自动执行（Hermes cronjob）
- 从 FalkorDB 读取实体节点，按实体名分组
- 同组 ≥3 条记忆 → 调 LLM 合并为 1-3 条
- 先 add 合并后记忆，再 delete 旧的（crash-safe）
- FalkorDB 不可用时降级为关键词搜索分组
- `CONSOLIDATION_DRY_RUN=true` 干跑，`CONSOLIDATION_MIN_GROUP=3` 分组阈值

### 矛盾检测

上游无此功能。本 Fork 复用 mem0 内置 `DEFAULT_UPDATE_MEMORY_PROMPT` 的 ADD/UPDATE/DELETE/NONE 判定能力：

- 默认关闭（`MEM0_ENABLE_CONTRADICTION=true` 启用）
- 开启后 LLM 在每次写入时自动对比新消息与已有记忆
- 发现矛盾（如"喜欢咖啡"→"讨厌咖啡"）→ 自动 DELETE 旧记忆
- UPDATE 时先 delete 旧向量，再 insert 新版本
- 零额外 LLM 调用——判定逻辑复用已有提取请求
| - history 表可追溯 DELETE/UPDATE 记录
| - 写入即检测，无需 cron 等待

### 搜索深度路由（Phase 1）

本 Fork 新增三级搜索深度，优化检索成本：

| 深度 | 链路 | 降本 |
|------|------|------|
| `minimal` | 跳过全部检索（命中废话白名单） | 100% |
| `standard` | embedding + BM25（跳过图查询 + rerank） | ~70% |
| `full` | embedding + BM25 + 图 + rerank（默认，零行为变化） | 0% |

深度自动判定在 `Memory.search()` 入口执行，关键词从 `search_keywords` 表读取（SQLite，`INSERT` 即生效）。

配置：

```yaml
MEM0_SEARCH_DEPTH_AUTO=true         # 启用自动深度判定
MEM0_SEARCH_DEPTH_DEFAULT=full      # 默认深度（v1 版本 full，零行为变化）
MEM0_SEARCH_CACHE_TTL=15            # minimal 路径 LRU 缓存 TTL 秒
MEM0_SEARCH_STD_CACHE_TTL=5         # standard 路径 LRU 缓存 TTL 秒
```

种子词表通过迁移 `mem0/migrations/002_search_keywords.py` 初始化（含中英文 ~127 条）。增删词直接操作 `search_keywords` 表，无需重启服务。`depth` 参数也暴露在 `SearchRequest` API 和 SDK `SearchMemoryOptions` 中，外部调用可显式指定。

## 环境要求

- Python 3.10-3.12
- Docker（运行 FalkorDB + PostgreSQL）
- FalkorDB ≥ 1.6.0（图数据库，Docker 运行）
- mem0-falkordb 已 Vendor 到 mem0/graphs/falkordb/，无需额外 pip 安装

## 许可证

Apache 2.0 — 与上游 [mem0ai/mem0](https://github.com/mem0ai/mem0) 一致。
