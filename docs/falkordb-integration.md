# FalkorDB 图存储集成

> 本 Fork 已将 FalkorDB 直接编译进 `GraphStoreFactory`，配置 `graph_store.provider="falkordb"` 即可使用，无需额外插件或 monkey-patch。

---

## 目录

- [为什么用图存储](#为什么用图存储)
- [架构](#架构)
- [配置](#配置)
- [验证](#验证)
- [每用户图隔离](#每用户图隔离)
- [图记忆时效](#图记忆时效)
- [图数据生命周期](#图数据生命周期)
- [参数](#参数)
- [注意事项](#注意事项)

---

## 为什么用图存储

纯向量检索只能按「语义相似度」找记忆，回答不了关系型问题：

- 「发哥部署在哪台服务器？」——向量库里是两条独立记忆（`发哥` 和 `web-1.example.com`），没有边连接
- 图存储把实体抽成节点、关系抽成边：`(发哥)-[部署于]->(web-1.example.com)`

搜索时图召回的结果会**合并进最终结果**（full 深度），让 agent 拿到「谁和谁有什么关系」的结构化上下文。

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│ mem0 Memory 实例                                             │
│  config.graph_store.provider="falkordb"                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ GraphStoreFactory.create("falkordb")
┌──────────────────────────▼──────────────────────────────────┐
│  mem0/graphs/falkordb/MemoryGraph                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ · _retrieve_nodes_from_data        → LLM 实体提取       │  │
│  │ · _establish_nodes_relations       → LLM 关系提取       │  │
│  │ · _search_graph_db                 → BM25 重排图召回    │  │
│  │ · _add_entities                    → Cypher MERGE 写入  │  │
│  │ · _invalidate_entities             → 冲突失效标记       │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ FalkorDB driver
┌──────────────────────────▼──────────────────────────────────┐
│  FalkorDB（图数据库）                                        │
│  每用户独立图：mem0_{user_id}                                │
└─────────────────────────────────────────────────────────────┘
```

---

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

Docker Compose 环境下 `host` 用服务名 `falkordb`（容器间通信）。FalkorDB 默认端口 6379。

### Python SDK

```python
from mem0 import Memory

config = {
    "graph_store": {
        "provider": "falkordb",
        "config": {"host": "localhost", "port": 6379, "database": "mem0"},
    },
    "vector_store": {
        "provider": "pgvector",
        "config": {"host": "localhost", "port": 5432, "user": "postgres", "password": "...", "dbname": "mem0"},
    },
    "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
    "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small"}},
}

m = Memory.from_config(config)
```

> 不需要 `from mem0.graphs.falkordb import register; register()`——FalkorDB 已内置在工厂里。

---

## 验证

1. 调用 `m.add()` 写入记忆
2. 打开 FalkorDB Web UI（Docker 部署默认端口 **3003**）
3. 执行查询：

```
GRAPH.QUERY mem0_alice "MATCH (n)-[r]->(m) RETURN n, r, m"
```

应能看到实体节点（人物/地点/概念等）和关系边。

也可以通过搜索验证图召回生效（full 深度）：

```python
results = m.search("发哥部署在哪里", user_id="alice", depth="full")
# results 中会出现 source="graph" 的片段
```

---

## 每用户图隔离

每个 `user_id` 对应一个独立图，命名规则 `mem0_{user_id}`：

| user_id | FalkorDB 图名 |
|---------|---------------|
| `alice` | `mem0_alice` |
| `bob`   | `mem0_bob` |

用户之间的图数据完全隔离，互不干扰。

---

## 图记忆时效

冲突消解采用**失效保留**策略，而非物理删除：

| 行为 | 说明 |
|------|------|
| 冲突消解 | 旧关系写入 `invalidated_at` 标记失效，不删除 |
| 检索 | 默认只返回有效关系（`invalidated_at IS NULL`） |
| 同事实重现 | 自动复活（MERGE 命中失效边时重置标记） |
| 存量数据 | 无标记视为有效，向后兼容 |
| LLM 成本 | 零额外调用（失效时间取冲突发生时戳） |

**价值**：① 被推翻的事实不再污染图上下文；② LLM 判断错了只是「误失效」，可追溯、可恢复，而非永久丢失。

---

## 图数据生命周期

```
add() 调用链：
1. _retrieve_nodes_from_data()        LLM 提取实体
2. _establish_nodes_relations()       LLM 提取关系
3. _search_graph_db()                 BM25 重排已有关系
4. _add_entities()                    Cypher MERGE 写入

search() 调用链（full 深度）：
1. 从查询提取实体
2. _search_graph_db() 查询实体关联
3. BM25 重排后合并进搜索结果

delete() / delete_all()：自动清理对应图数据
```

---

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `host` | `localhost` | FalkorDB 服务器地址 |
| `port` | `6379` | FalkorDB 端口 |
| `database` | `mem0` | 图名前缀 |
| `username` | — | 认证用户名 |
| `password` | — | 认证密码 |
| `base_label` | `true` | 是否使用 `__Entity__` 基础标签 |

---

## 注意事项

- FalkorDB 使用 Cypher 查询语言（与 Neo4j 兼容）
- 中文 entity_type / relationship 经 backtick 转义后直接写入（FalkorDB v42001+ 原生支持 CJK 标识符，无需英文映射）；非法字符（`;`/括号等注入面）替换为下划线
- 每用户独立图，互不干扰
- 图搜索为 full 深度的可选增强：`MEM0_SEARCH_DEPTH_DEFAULT=standard` 时跳过图查询（降本但丢失关系召回）
- 清理脚本会同步清理 FalkorDB 孤立实体节点（无任何关系的节点）
