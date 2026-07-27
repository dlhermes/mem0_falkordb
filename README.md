# mem0 + FalkorDB = Graph-Enhanced Memory Layer

> **Fork of [mem0ai/mem0](https://github.com/mem0ai/mem0) v2.0.14** — backporting the `graphs/` module removed since v2.0.0, enabling external graph database integration via [mem0-falkordb](https://github.com/FalkorDB/mem0-falkordb).

## What This Fork Does

mem0 OSS v2.0.0+ removed external graph database support (Neo4j, Kuzu, Memgraph, Apache AGE, Neptune). The entire `mem0/graphs/` module — interface, factory, configs, tools — was deleted.

This fork restores the graph store interface layer while keeping everything else intact from v2.0.14. Also fixes several deployment pain points from the original upstream.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  AI Agent                        │
│         add() / search() / delete()              │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              Mem0 SDK v2.0.14 + graphs           │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ vector   │  │ entity    │  │ graph_store  │  │
│  │ store    │  │ store     │  │ (restored)   │  │
│  └──────────┘  └───────────┘  └──────┬───────┘  │
│                                      │           │
│                           GraphStoreFactory     │
│                           provider_to_class     │
└──────────────────────────────────┬─────────────┘
                                   │ plugin registers
┌──────────────────────────────────▼─────────────┐
│           mem0-falkordb plugin                  │
│  ┌──────────────────────────────────────────┐  │
│  │  MemoryGraph (775 lines)                  │  │
│  │  - FalkorDB Cypher (vector index, merge)  │  │
│  │  - Per-user graph isolation               │  │
│  │  - Mention counting / entity linking       │  │
│  └──────────────────────────────────────────┘  │
└──────────────────────┬─────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────┐
│              FalkorDB (graph DB)                │
│  Real Cypher graphs — traversable, queryable   │
└────────────────────────────────────────────────┘
```

## Quick Start

### Server Deployment (Recommended)

自带的 FastAPI server + Next.js Dashboard，一键部署后打开浏览器就能用。

```bash
git clone https://github.com/dlhermes/mem0_falkordb.git
cd mem0_falkordb/server
```

**Step 1: 创建 Provider 配置文件**

```bash
cat > config.json << 'EOF'
{
  "llm": {
    "provider": "openai",
    "config": {
      "api_key": "sk-xxx",
      "model": "gpt-4o-mini",
      "temperature": 0.1,
      "max_tokens": 8000
    }
  },
  "embedder": {
    "provider": "openai",
    "config": {
      "api_key": "sk-xxx",
      "model": "text-embedding-3-small"
    }
  }
}
EOF
```

> **切换 Embedder 模型**: 如果使用 `BAAI/bge-m3`（1024 维），pgvector 会自动检测维度，无需手动改配置。只需在 config.json 中指定 embedder model 即可。

完整的 Provider 配置参考（LLM + Embedder + Reranker）：

```bash
cat > config.json << 'EOF'
{
  "llm": {
    "provider": "openai",
    "config": {
      "api_key": "sk-xxx",
      "model": "deepseek-v4-flash-free",
      "temperature": 0.1,
      "max_tokens": 8000,
      "openai_base_url": "https://opencode.ai/zen/v1"
    }
  },
  "embedder": {
    "provider": "openai",
    "config": {
      "api_key": "sk-xxx",
      "model": "BAAI/bge-m3",
      "openai_base_url": "https://api.siliconflow.cn/v1"
    }
  },
  "reranker": {
    "provider": "llm_reranker",
    "config": {
      "model": "BAAI/bge-reranker-v2-m3",
      "api_key": "sk-xxx",
      "llm": {
        "provider": "openai",
        "config": {
          "model": "BAAI/bge-reranker-v2-m3",
          "api_key": "sk-xxx",
          "openai_base_url": "https://api.siliconflow.cn/v1/rerank"
        }
      }
    }
  }
}
EOF
```

**Step 2: 启动**

```bash
# 创建 .env
cat > .env << 'EOF'
POSTGRES_PASSWORD=change-me
JWT_SECRET=random-string-at-least-32-chars
DASHBOARD_URL=http://你的IP:3000
MEM0_CONFIG_PATH=/app/config.json
AUTH_DISABLED=false
EOF

docker compose up -d
```

> **注意**: `DASHBOARD_URL` 必须用 `http://` 而非 `https://`，否则 Dashboard cookie 在浏览器中会被拒绝。

**Step 3: 创建 Admin 用户**

```bash
docker exec -it mem0-mem0-1 python3 << 'EOF'
from passlib.hash import bcrypt
from sqlalchemy import text
from db import get_db
db = next(get_db())
ph = bcrypt.hash("your-password")
db.execute(text(
  "INSERT INTO users (id, name, email, password_hash, role, created_at) "
  "VALUES (gen_random_uuid(), 'Admin', 'admin@example.com', :ph, 'admin', now()) "
  "ON CONFLICT (email) DO NOTHING"
), {"ph": ph})
db.commit()
db.close()
EOF
```

**Step 4: 打开 Dashboard**

浏览器访问 `http://你的IP:3000`，用刚才创建的邮箱和密码登录。无需走注册向导 — admin 用户存在后 `/setup` 自动跳过。

### Python SDK Only

如果只需要 SDK 不需要 Dashboard：

```bash
git clone https://github.com/dlhermes/mem0_falkordb.git
cd mem0_falkordb
pip install build --break-system-packages
python3 -m build --wheel
pip install dist/mem0ai-*.whl --break-system-packages
pip install mem0-falkordb falkordb --break-system-packages
docker run -d --rm -p 6379:6379 falkordb/falkordb
```

```python
from mem0_falkordb import register
register()

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
m.add("I love pizza", user_id="alice")
results = m.search("what does alice like?", user_id="alice")
```

> **注意**: 如果在虚拟环境中安装，去掉 `--break-system-packages`。

## Key Improvements over Upstream

| 改动 | 文件 | 说明 |
|---|---|---|
| Graph Store 模块恢复 | `mem0/graphs/` | 支持 FalkorDB 图存储（通过 mem0-falkordb 插件） |
| GraphStoreFactory | `mem0/utils/factory.py` | Provider 注册机制，插件可用 monkey-patch 注册 |
| Memory 图集成 | `mem0/memory/main.py` | add/search/delete 同步+异步全覆盖 |
| pgvector 维度自动检测 | `mem0/configs/vector_stores/pgvector.py` | 从 `1536` 硬编码改为自动推断，切 embedder 不用清数据 |
| Provider 配置文件 | `server/server_state.py` | `MEM0_CONFIG_PATH=/app/config.json` 即可，不用调 API |
| Dockerfile 修复 | `server/Dockerfile` | 预装 libpq5，构建即可用 |
| CORS 修复 | `server/main.py` | allow_methods + allow_headers 已配置 |

## Requirements

- Python 3.10-3.12
- Docker（FalkorDB + PostgreSQL）
- mem0-falkordb ≥ 0.4.1
- FalkorDB ≥ 1.6.0

## License

Apache 2.0 — same as upstream [mem0ai/mem0](https://github.com/mem0ai/mem0).
