# mem0 + FalkorDB = 图增强记忆层

> **基于 [mem0ai/mem0](https://github.com/mem0ai/mem0) v2.0.14 的 Fork** — 回迁了 v2.0.0 起被移除的 `graphs/` 模块，通过 [mem0-falkordb](https://github.com/FalkorDB/mem0-falkordb) 插件恢复外部图数据库集成。

## 这个 Fork 做了什么

mem0 OSS v2.0.0+ 移除了外部图数据库支持（Neo4j、Kuzu、Memgraph、Apache AGE、Neptune）。整个 `mem0/graphs/` 模块——接口、工厂、配置、工具函数——全被删除。

本 Fork 恢复了图存储接口层，并修复了上游多个部署痛点：

- **`mem0/graphs/` 模块** — 配置、LLM 工具 Schema、提取提示词、MemoryGraph 存根
- **`GraphStoreFactory`** — 带 Provider 注册机制的工厂类
- **`graph_store` 字段** — 添加到 `MemoryConfig`
- **Memory 图集成** — `add()` 非阻塞图写入、`search()` 合并图关系、`delete()`/`reset()` 清理图数据，同步+异步全覆盖
- **pgvector 维度自动检测** — 不再硬编码 1536，切换 Embedder 模型自动适配
- **Provider 配置文件** — 设 `MEM0_CONFIG_PATH=/app/config.json` 即可，不需要调 API
- **Dockerfile 修复** — 预装 libpq5，开箱即用

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
                                   │ 插件注册
┌──────────────────────────────────▼─────────────┐
│           mem0-falkordb 插件                    │
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

> 本 Fork 恢复了 graph_store 接口层，需要配合 [mem0-falkordb](https://github.com/FalkorDB/mem0-falkordb) 插件 + FalkorDB 图数据库使用。

详细的集成配置、Cypher 翻译对照、验证方法请参阅 → **[docs/falkordb-integration.md](docs/falkordb-integration.md)**

简而言之：

```python
from mem0_falkordb import register
register()  # ⚠️ 必须在 Memory.from_config() 之前

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

**第一步：创建 Provider 配置文件**

```bash
cat > config.json << 'EOF'
{
  "llm": {
    "provider": "openai",
    "config": {
      "api_key": "sk-你的Key",
      "model": "gpt-4o-mini",
      "temperature": 0.1,
      "max_tokens": 8000
    }
  },
  "embedder": {
    "provider": "openai",
    "config": {
      "api_key": "sk-你的Key",
      "model": "text-embedding-3-small"
    }
  }
}
EOF
```

> 如果使用其他 Embedder 模型（如 `BAAI/bge-m3`，1024 维），pgvector 会自动检测维度，无需手动配置。

完整的三组件配置参考（LLM + Embedder + Reranker）：

```bash
cat > config.json << 'EOF'
{
  "llm": {
    "provider": "openai",
    "config": {
      "api_key": "sk-你的Key",
      "model": "deepseek-v4-flash-free",
      "temperature": 0.1,
      "max_tokens": 8000,
      "openai_base_url": "https://opencode.ai/zen/v1"
    }
  },
  "embedder": {
    "provider": "openai",
    "config": {
      "api_key": "sk-你的Key",
      "model": "BAAI/bge-m3",
      "openai_base_url": "https://api.siliconflow.cn/v1"
    }
  },
  "reranker": {
    "provider": "llm_reranker",
    "config": {
      "model": "BAAI/bge-reranker-v2-m3",
      "api_key": "sk-你的Key",
      "llm": {
        "provider": "openai",
        "config": {
          "model": "BAAI/bge-reranker-v2-m3",
          "api_key": "sk-你的Key",
          "openai_base_url": "https://api.siliconflow.cn/v1/rerank"
        }
      }
    }
  }
}
EOF
```

**第二步：启动**

```bash
cat > .env << 'EOF'
POSTGRES_PASSWORD=改一个密码
JWT_SECRET=随机字符串至少32位
DASHBOARD_URL=http://你的服务器IP:3002
MEM0_CONFIG_PATH=/app/config.json
AUTH_DISABLED=false
EOF

docker compose up -d
```

> `DASHBOARD_URL` 必须用 `http://`，不能用 `https://`，否则 Dashboard 的 Cookie 会被浏览器拒绝。

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
pip install mem0-falkordb falkordb --break-system-packages
docker run -d --rm -p 6379:6379 falkordb/falkordb
```

```python
from mem0_falkordb import register
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

| 改动 | 文件 | 说明 |
|---|---|---|
| 图存储模块恢复 | `mem0/graphs/` | 支持 FalkorDB 图存储 |
| GraphStoreFactory | `mem0/utils/factory.py` | Provider 注册机制 |
| Memory 图集成 | `mem0/memory/main.py` | add/search/delete 全路径覆盖 |
| pgvector 维度自动检测 | `mem0/configs/vector_stores/pgvector.py` | 不再硬编码 1536 |
| Provider 配置文件 | `server/server_state.py` | 设环境变量即可，不用调 API |
| Dockerfile 修复 | `server/Dockerfile` | 预装 libpq5 |
| CORS 修复 | `server/main.py` | allow_methods + allow_headers 已配置 |

## 环境要求

- Python 3.10-3.12
- Docker（运行 FalkorDB + PostgreSQL）
- mem0-falkordb ≥ 0.4.1
- FalkorDB ≥ 1.6.0

## 许可证

Apache 2.0 — 与上游 [mem0ai/mem0](https://github.com/mem0ai/mem0) 一致。
