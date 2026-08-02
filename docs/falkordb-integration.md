# 集成 FalkorDB 图存储

> 本文指导如何配置 FalkorDB 图存储到本 Fork 的 mem0 中。

## 架构

FalkorDB 图存储已直接编译进 `GraphStoreFactory`，无需额外插件或 monkey-patch。配置 `graph_store.provider="falkordb"` 即可使用。

```
┌─────────────────────────────────────────────────────────────┐
│ mem0 Memory 实例                                              │
│  config.graph_store.provider="falkordb"                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ GraphStoreFactory.create("falkordb")
┌──────────────────────────▼──────────────────────────────────┐
│  mem0/graphs/falkordb/MemoryGraph (797 行)                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  · _FalkorDBGraphWrapper → FalkorDB() client            │  │
│  │  · _retrieve_nodes_from_data → LLM 实体提取              │  │
│  │  · _establish_nodes_relations_from_data → LLM 关系提取    │  │
│  │  · _search_graph_db → BM25 重排实体关系                   │  │
│  │  · _add_entities → Cypher MERGE 写入                    │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ FalkorDB driver
┌──────────────────────────▼──────────────────────────────────┐
│  FalkorDB (图数据库)                                          │
│  每用户独立图：mem0_{user_id}                                  │
└─────────────────────────────────────────────────────────────┘
```

## 配置

### Server 部署

在 `config.json` 中配置：

```json
{
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

`host` 使用 Docker Compose 服务名 `falkordb`（容器间通信）。FalkorDB 容器默认端口 6379。

### Python SDK

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
```

> ⚠️ 不再需要 `from mem0.graphs.falkordb import register; register()`。FalkorDB 已直接编译进 `GraphStoreFactory`。

## 验证

部署后登陆 FalkorDB Web UI（Docker 部署默认端口 3003）查看图结构：

1. 调用 `m.add()` 写入记忆
2. 打开 `http://你的IP:3003`
3. 用 FalkorDB Web UI 查询：`GRAPH.QUERY mem0_alice "MATCH (n)-[r]->(m) RETURN n, r, m"`

应能看到实体节点（人物/地点/概念等）和关系边。

## 每用户图隔离

每个 `user_id` 对应一个独立的 FalkorDB 图，命名规则 `mem0_{user_id}`。例如：

| user_id | FalkorDB 图名 |
|---------|---------------|
| `alice` | `mem0_alice` |
| `bob`   | `mem0_bob` |

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `host` | `localhost` | FalkorDB 服务器地址 |
| `port` | `6379` | FalkorDB 端口 |
| `database` | `mem0` | 图名前缀 |
| `username` | — | 认证用户名 |
| `password` | — | 认证密码 |
| `base_label` | `true` | 是否使用 `__Entity__` 基础标签 |

## 集成细节

### 实体提取

`add()` 调用链：
1. `MemoryGraph.add()` → `_retrieve_nodes_from_data()`（LLM 提取实体）
2. `_establish_nodes_relations_from_data()`（LLM 提取关系）
3. `_search_graph_db()` → BM25 重排已有关系
4. `_add_entities()` → Cypher MERGE 写入

### 搜索增强

`search()` 返回向量存储结果 + 图关系合并结果：

1. `_retrieve_nodes_from_data()` 从查询提取实体
2. `_search_graph_db()` 查询实体关联
3. BM25 重排后合并到搜索结果

### 删除

`delete()` / `delete_all()` 自动清理图数据。

## 注意事项

- FalkorDB 使用 Cypher 查询语言（与 Neo4j 兼容）
- 中文 entity_type / relationship 经 backtick 转义后直接写入（FalkorDB v42001+ 原生支持 CJK 标识符，无需映射英文）；非法字符（`;`/括号等注入面）替换为下划线
- 每用户独立图，互不干扰
