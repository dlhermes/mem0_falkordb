# 集成 FalkorDB 图存储

> 本文指导如何将 mem0-falkordb 插件与 FalkorDB 图数据库集成到本 Fork 的 mem0 中。

## 三者关系

```
┌──────────────────────────────────────────────────────────────┐
│  本 Fork (mem0 v2.0.14 + graphs)                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  恢复了 graph_store 接口层：                              │ │
│  │  · GraphStoreFactory（provider 注册机制）                 │ │
│  │  · MemoryGraph 存根（空壳，等插件替换）                   │ │
│  │  · graph_store 配置字段                                  │ │
│  │  · add/search/delete 中的图调用点                         │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────┘
                               │ monkey-patch 注册
┌──────────────────────────────▼───────────────────────────────┐
│  mem0-falkordb 插件 (v0.4.1)                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  patch.py — 把 FalkorDB 注入 GraphStoreFactory           │ │
│  │  graph_memory.py (775行) — 完整的 FalkorDB Cypher 实现   │ │
│  │  config.py — FalkorDBConfig（host/port/database）        │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────┘
                               │ Redis 协议
┌──────────────────────────────▼───────────────────────────────┐
│  FalkorDB (≥ 1.6.0)                                           │
│  · 真正的属性图数据库（可遍历、可查询）                       │
│  · 每用户独立图隔离                                          │
│  · 向量索引（cosine similarity）                              │
│  · 内置 Web UI（端口 3003）                                   │
└──────────────────────────────────────────────────────────────┘
```

## 工作原理

mem0-falkordb 通过 Python 运行时 monkey-patch 注册自身，**不修改 mem0 源码**：

```
register() 调用时:
  1. patch.py 修改 GraphStoreFactory.provider_to_class
     → 添加 "falkordb": "mem0_falkordb.graph_memory.MemoryGraph"

  2. patch.py 修改 GraphStoreConfig 的 Pydantic validator
     → 让 Union 类型接受 FalkorDBConfig

  3. Memory.from_config() 时:
     → 读到 graph_store.provider = "falkordb"
     → GraphStoreFactory.create("falkordb", config)
     → 动态加载 mem0_falkordb.graph_memory.MemoryGraph
     → 返回 FalkorDB 的完整实现
```

## Server 部署集成

> **启动后自动创建管理员**：Server 容器启动时会自动创建 `admin@mem0.dev` 并生成随机密码，查看容器日志即可获取凭据，无需手动执行创建脚本。Dashboard 访问端口为 `3002`。

### 1. 修改 docker-compose.yaml

在 `server/docker-compose.yaml` 中添加 FalkorDB 服务：

```yaml
  falkordb:
    image: falkordb/falkordb:latest
    ports:
      - "6379:6379"
      - "3003:3000"   # FalkorDB Web UI
    volumes:
      - falkordb_data:/data
    networks:
      - mem0_network
    command: ["redis-server", "--dir", "/data", "--save", "60", "1"]

volumes:
  # ... 现有的 postgres_db ...
  falkordb_data:
```

### 2. 安装依赖

修改 `server/requirements.txt`，添加：

```
mem0-falkordb>=0.4.1
falkordb>=1.6.0
rank-bm25>=0.2.0
```

或者通过 Dockerfile 安装：

```dockerfile
RUN pip install --no-cache-dir mem0-falkordb falkordb rank-bm25
```

### 3. 修改 server_state.py

让 server 启动时自动调用 `register()`：

```python
# server/server_state.py 顶部添加
from mem0_falkordb import register
register()
```

### 4. 配置 graph_store

在 `config.json` 中添加 `graph_store` 段：

```json
{
  "llm": { ... },
  "embedder": { ... },
  "graph_store": {
    "provider": "falkordb",
    "config": {
      "host": "falkordb",
      "port": 6379,
      "database": "mem0"
    }
  }
}
```

## Python SDK 集成

```bash
# 1. 安装本 Fork 的 mem0
pip install dist/mem0ai-*.whl --break-system-packages

# 2. 安装插件和 FalkorDB 客户端
pip install mem0-falkordb falkordb --break-system-packages

# 3. 启动 FalkorDB
docker run -d --rm -p 6379:6379 falkordb/falkordb
```

```python
from mem0_falkordb import register
register()  # ⚠️ 必须在 Memory.from_config() 之前

from mem0 import Memory

config = {
    "graph_store": {
        "provider": "falkordb",
        "config": {
            "host": "localhost",
            "port": 6379,
            "database": "mem0",
        },
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {"host": "localhost", "port": 6333, "collection_name": "mem0"},
    },
    "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
    "embedder": {
        "provider": "openai",
        "config": {"model": "text-embedding-3-small", "embedding_dims": 1536},
    },
}

m = Memory.from_config(config)

# add() 写入时自动抽取实体并构建图关系
m.add("我叫张三，住在北京，喜欢喝咖啡", user_id="alice")
m.add("张三上周搬到了上海", user_id="alice")

# search() 会合并向量搜索结果 + 图关系结果
results = m.search("张三住在哪里？", user_id="alice")
```

## 配置说明

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `host` | str | `localhost` | FalkorDB 服务器地址 |
| `port` | int | `6379` | FalkorDB 端口 |
| `database` | str | `mem0` | 图名前缀（每个用户自动创建 `{database}_{user_id}` 独立图） |
| `username` | str | `None` | 认证用户名（可选） |
| `password` | str | `None` | 认证密码（可选） |
| `base_label` | bool | `True` | 是否使用 `__Entity__` 基标签 |

## 每用户图隔离

每个用户自动获得独立的 FalkorDB 图（如 `mem0_alice`、`mem0_bob`），利用 FalkorDB 原生多图支持：

- **数据天然隔离** — Cypher 查询不需要 `WHERE user_id = xxx`
- **查询更简洁** — 没有 user_id 过滤条件，速度更快
- **清理方便** — `delete_all(user_id="alice")` 直接删除 alice 的整个图

## 关键 Cypher 差异

mem0-falkordb 的 MemoryGraph 将上游 Neo4j 语法翻译为 FalkorDB 语法：

| Neo4j | FalkorDB |
|---|---|
| `elementId(n)` | `id(n)` |
| `vector.similarity.cosine()` | `db.idx.vector.queryNodes()` 存储过程 |
| `db.create.setNodeVectorProperty()` | `SET n.embedding = vecf32($vec)` |
| `CALL { ... UNION ... }` 子查询 | 拆分为独立的 outgoing + incoming 查询 |

## 验证图存储是否生效

```python
m.add("张三喜欢咖啡和编程", user_id="alice")

# 查看图数据
from falkordb import FalkorDB
db = FalkorDB(host="localhost", port=6379)
graph = db.select_graph("mem0_alice")

# 列出所有节点
print(graph.query("MATCH (n) RETURN n.name, labels(n)").result_set)

# 列出所有关系
print(graph.query("MATCH (n)-[r]->(m) RETURN n.name, type(r), m.name").result_set)
```

或通过 FalkorDB Web UI 可视化查看：浏览器访问 `http://localhost:3003`（如果在 Docker 中映射了端口）。

## 常见问题

### register() 放在哪里？

必须在 `Memory.from_config()` **之前**调用。在 Server 部署中，放在 `server_state.py` 的 `initialize_state()` 之前；在 SDK 中，放在创建 Memory 实例之前。

### 安装后 import 报错 "No module named mem0.graphs"

说明 pip 装的是上游 mem0ai（不含 graphs 模块）。需要用本 Fork 的 wheel 安装：`pip install dist/mem0ai-*.whl` 而非 `pip install mem0ai`。

### FalkorDB 连接失败

检查 FalkorDB 是否运行：`docker ps | grep falkordb`。检查端口是否冲突——FalkorDB 默认 6379，可能与已有 Redis 冲突。

### 图数据不更新

图写入是 `add()` 中的 fire-and-forget 异步操作，不阻塞主流程。如果数据量大，等几秒再查询。查看日志确认 `_add_to_graph` 是否正常执行。
