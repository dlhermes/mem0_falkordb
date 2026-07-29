# Mem0 + FalkorDB 部署后：短板补齐 SOP

> **文档代号**：MEM0-FALKORDB-GAP-001
> **版本**：v3.0.0
> **创建**：2026-07-27
> **更新**：2026-07-27（二次审计后修订）
> **目标读者**：架构师 / Agent 基础设施团队
> **前置条件**：Mem0 v2.0.14+ 已部署，FalkorDB 已通过 mem0-falkordb 插件接入

---

## 0. 文档目的

本文档解决一个核心问题：**mem0 + FalkorDB 组合能用，但还不够好。** 具体而言：

- mem0 OSS 在 v2.0.0 中移除了外部图数据库支持，但通过 mem0-falkordb 插件恢复了图能力
- 然而图能力只是记忆系统的"骨架"，Agent 仍面临金鱼脑（遗忘、矛盾、记忆膨胀）问题
- 本文档逐项列出已部署架构的剩余短板，并给出可落地的补齐方案
- **v2.0 修订**：补齐接口完整性、运维考量、风险评估、回滚方案、成本估算
- **v3.0 修订**：修复代码缺陷、新增决策树、替代方案对比、多模型成本对照

---

## 1. 已部署架构现状

### 1.1 组件栈

```
┌─────────────────────────────────────────────────────────────────┐
│                         AI Agent                                 │
│              (Claude Code / Cursor / Custom Agent)               │
└──────────────────────────────┬──────────────────────────────────┘
                               │ add() / search() / update() / delete()
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     补齐层 (Gap Layer)                            │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │ Decay      │  │Contradiction│  │Consolidation│  │ Cleanup   │  │
│  │ Filter     │  │ Detector   │  │ Service     │  │ Scheduler │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Feature Flags (per-user / percentage rollout)              │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Mem0 SDK (v2.0.14+)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ vector_store  │  │ entity_store │  │ history (SQLite)       │  │
│  │ (Qdrant/      │  │ (第二向量集合) │  │                        │  │
│  │  Pgvector/    │  │              │  │                        │  │
│  │  Pinecone)    │  │              │  │                        │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────────────────┘  │
│         │                 │                                       │
│         │    ┌────────────┘                                       │
│         │    │ (entity linking)                                   │
│         ▼    ▼                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              FalkorDB (via mem0-falkordb v0.4.1 plugin)      │ │
│  │  - 实体节点 (人名/地名/组织/概念)                              │ │
│  │  - 关系边 (source → relationship → target)                  │ │
│  │  - 每用户独立图 (mem0_alice, mem0_bob)                       │ │
│  │  - 向量索引 (cosine similarity)                              │ │
│  │  - 多图隔离 (native multi-graph)                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 当前能力清单

| 能力 | 状态 | 实现方式 |
|------|------|----------|
| 语义搜索 | ✅ | vector_store (dense embedding) |
| BM25 关键词搜索 | ✅ | fastembed / 向量库原生全文索引 |
| 实体抽取 + 链接 | ✅ | entity_store + spaCy |
| 图结构存储 | ✅ | FalkorDB (via mem0-falkordb 插件) |
| 图关系遍历 | ✅ | Cypher 查询 |
| 每用户数据隔离 | ✅ | FalkorDB 多图机制 |
| 记忆版本历史 | ✅ | SQLite history 表 |
| 记忆过期 (TTL) | ✅ | expiration_date 字段 |
| 去重 | ✅ | MD5 hash + 向量相似度 |
| 批量搜索 | ✅ | search_batch API |
| 过程性记忆 | ✅ | memory_type=procedural |

### 1.3 已知缺失（v2.0.14 OSS 明确不含）

| 缺失能力 | 影响严重度 | 备注 |
|----------|-----------|------|
| 时间推理 (Temporal Reasoning) | 🔴 高 | Platform(云端 mem0) only，OSS 无 |
| 记忆衰减 (Memory Decay) | 🔴 高 | Platform(云端 mem0) only，OSS 无 |
| 自动合并/压缩 | 🔴 高 | 记忆只增不减，无智能整合 |
| 矛盾检测/解决 | 🟡 中 | 冲突记忆共存 |
| 自动遗忘/清理 | 🟡 中 | 需应用层实现 |
| Dream Consolidation | 🟡 中 | 仅在第三方插件 (OpenCode/Pi Agent) |
| 可视化图谱面板 | 🟢 低 | Platform(云端 mem0) Pro+ 功能，OSS 无 Dashboard |

### 1.4 前置依赖与版本兼容性

| 组件 | 版本 | 兼容性说明 |
|------|------|-----------|
| mem0ai | v2.0.14+ | 必须 ≥ v2.0.0（v3 算法） |
| mem0-falkordb | v0.4.1 | **Alpha 状态**，社区维护 |
| FalkorDB | ≥ 1.6.0 | 插件依赖 |
| Python | 3.10-3.12 | spaCy 约束 |
| spaCy | ≥ 3.7.0 | 实体抽取需要 |
| Qdrant | ≥ 1.12.0 | 向量库（推荐） |

> ⚠️ **版本锁定警告**：mem0-falkordb 使用 monkey-patching 注入 mem0 内部，mem0 升级可能导致插件失效。升级前必须在 staging 环境验证。

---

## 2. 短板详细分析 + 补齐方案

### 2.1 短板一：无自动记忆合并 (Auto-Merge)

#### 问题描述

当前 ADD-only 策略下，每次对话产生的新事实独立存储。例如：

```
记忆 #1: "用户养了一只狗叫 Max"        (2026-01-15)
记忆 #2: "Max 是金毛犬"                 (2026-02-20)
记忆 #3: "用户带 Max 去露营"            (2026-03-10)
记忆 #4: "Max 在露营时游泳和爬山"        (2026-03-10)
```

搜索"用户有什么宠物"时返回 4 条独立记忆，Agent 需要自己拼凑完整图景。随着记忆数量增长，检索噪音增大、token 消耗增加。

#### 根因

- `ADDITIVE_EXTRACTION_PROMPT` 明确只 ADD 不 UPDATE/DELETE
- `linked_memory_ids` 只是链接，不是合并
- OSS 无 Dream Consolidation 能力

#### 补齐方案

**方案 A：应用层定期合并（推荐）**

```python
# 完整实现：带备份、entity_store 清理、history 审计
class ConsolidationService:
    def __init__(self, mem0_client, archive_store, llm_client):
        self.mem0 = mem0_client
        self.archive = archive_store  # 归档存储（SQLite/PostgreSQL）
        self.llm = llm_client  # LLM 客户端
    
    def consolidate_user(self, user_id: str, topic: str, dry_run: bool = False):
        """
        合并指定用户某主题的记忆。
        
        Args:
            user_id: 用户 ID
            topic: 合并主题（实体名或关键词）
            dry_run: 为 True 时只返回合并方案，不实际执行
        
        Returns:
            ConsolidationResult(old_count, new_count, archived_ids)
        """
        # 1. 检索同一主题下的所有记忆
        existing = self.mem0.search(
            topic, 
            filters={"user_id": user_id}, 
            top_k=50,
            show_expired=False
        )
        
        if len(existing) < 3:
            return ConsolidationResult(0, 0, [])  # 太少不合并
        
        # 2. 调用 LLM 合并
        prompt = f"""
        以下是关于同一主题的 {len(existing)} 条记忆。
        请合并为 1-3 条精炼的、不重复的记忆。
        保留所有关键事实，去除冗余。
        输出 JSON 格式：{{"merged": ["记忆1", "记忆2", ...]}}
        
        原始记忆：
        {json.dumps([m["memory"] for m in existing], ensure_ascii=False, indent=2)}
        """
        response = self.llm.generate(prompt)
        merged_texts = json.loads(response)["merged"]
        
        if dry_run:
            return ConsolidationResult(len(existing), len(merged_texts), [])
        
        # 3. 备份到归档表（支持回滚）
        archive_ids = []
        for mem in existing:
            aid = self.archive.store({
                "original_id": mem["id"],
                "text": mem["memory"],
                "metadata": mem.get("metadata", {}),
                "created_at": mem.get("created_at"),
                "consolidated_at": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
            })
            archive_ids.append(aid)
        
        # 4. 删除旧记忆（mem0 自动清理 entity_store）
        for mem in existing:
            self.mem0.delete(mem["id"])
        
        # 5. 插入合并后记忆
        for text in merged_texts:
            self.mem0.add(text, user_id=user_id)
        
        # 6. 写入 history 审计
        self.mem0.db.add_history(
            memory_id=None,
            prev_value=f"{len(existing)} separate memories",
            new_value=f"{len(merged_texts)} consolidated memories",
            event="CONSOLIDATE",
            metadata={"archived_ids": archive_ids, "user_id": user_id}
        )
        
        return ConsolidationResult(len(existing), len(merged_texts), archive_ids)
    
    def rollback_consolidation(self, archive_ids: list):
        """从归档恢复原始记忆"""
        for aid in archive_ids:
            record = self.archive.get(aid)
            self.mem0.add(record["text"], user_id=record["user_id"])
            self.archive.delete(aid)
```

**方案 B：接入 Platform(云端 mem0) 的 Dream Consolidation**

如果未来升级到 Platform(云端 mem0)，此能力原生可用。

**方案 C：使用 OpenCode/Pi Agent 插件的 Dream 能力**

这些插件已实现：
- 合并重复项
- 解决矛盾
- 修剪过期记忆
- 按 session/时间/数量门控

#### 实施建议

| 维度 | 建议 |
|------|------|
| 触发频率 | 每日凌晨或记忆数超阈值（如 100 条/用户） |
| 合并粒度 | 按实体（同一人名/地名）分组合并 |
| 安全阀 | 合并前必须归档，支持 30 天内回滚 |
| 并发保护 | 合并期间对该用户记忆加分布式锁 |
| 优先级 | 🔴 高 — 直接影响 Agent 长期可用性 |

---

### 2.2 短板二：无矛盾检测 (Contradiction Detection)

#### 问题描述

Agent 可能同时持有两条矛盾记忆：

```
记忆 #A: "用户住在北京"     (2026-01-10, 用户明确说)
记忆 #B: "用户住在上海"     (2026-06-15, 用户明确说)
```

当前系统两条都保留，搜索时可能返回矛盾信息，导致 Agent 回答不一致。

#### 根因

- OSS 无矛盾检测逻辑
- `update()` 只能按 ID 单条更新，无法跨记忆推理
- LLM 提取时只看当前对话，不对比已有记忆的全貌

#### 补齐方案

**方案 A：add() 前矛盾检查**

```python
class ContradictionDetector:
    def __init__(self, mem0_client, llm_client):
        self.mem0 = mem0_client
        self.llm = llm_client  # LLM 客户端
    
    def check(self, text: str, filters: dict) -> ContradictionResult:
        """
        检测新记忆是否与已有记忆矛盾。
        
        Returns:
            ContradictionResult(has_contradiction, conflicting_memories, confidence)
        """
        # 1. 提取新记忆中的实体和断言
        new_facts = self._extract_facts(text)
        
        # 2. 检索相关已有记忆
        contradictions = []
        for fact in new_facts:
            existing = self.mem0.search(
                fact["subject"],
                filters=filters,
                top_k=10
            )
            
            # 3. 调用 LLM 检测矛盾
            for mem in existing:
                result = self._detect_contradiction(fact, mem)
                if result.is_contradictory and result.confidence > 0.7:
                    contradictions.append(Contradiction(
                        new_fact=fact,
                        existing_memory=mem,
                        confidence=result.confidence
                    ))
        
        return ContradictionResult(
            has_contradiction=len(contradictions) > 0,
            contradictions=contradictions
        )
    
    def _detect_contradiction(self, fact: dict, existing: dict) -> DetectionResult:
        """调用 LLM 判断两条记忆是否矛盾"""
        prompt = f"""
        判断以下两条记忆是否矛盾。
        
        新记忆：{fact["text"]}
        已有记忆：{existing["memory"]}
        
        输出 JSON：{{"is_contradictory": true/false, "confidence": 0-1, "reason": "..."}}
        """
        response = self.llm.generate(prompt)
        return DetectionResult(**json.loads(response))
```

**方案 B：利用 FalkorDB 图结构检测**

> ⚠️ 注意：mem0-falkordb 插件使用**无 schema** 的关系（类型由 LLM 动态决定，不固定）。
> 实际查询需要遍历所有关系类型：

```cypher
-- 查找同一实体的所有属性值（发现矛盾）
MATCH (e:Entity {name: "用户"})-[r]-(x)
WHERE e.user_id = $user_id
RETURN type(r) as relationship, x.name as value, r.mentions as mentions
ORDER BY relationship, mentions DESC

-- 查找同一关系类型下有多个不同目标的情况（潜在矛盾）
MATCH (e:Entity)-[r]->(x)
WHERE e.user_id = $user_id
WITH e, type(r) as rel_type, collect(DISTINCT x.name) as targets
WHERE size(targets) > 1
RETURN e.name, rel_type, targets
```

**方案 C：时间推理（Platform(云端 mem0) 能力）**

Platform(云端 mem0) v3 的时间推理可自动判断"上海"是最新状态，"北京"是历史状态。

#### 实施建议

| 维度 | 建议 |
|------|------|
| 检测时机 | add() 时异步检测（不阻塞写入），结果写入 metadata |
| 处理策略 | 不自动删除，标记 `contradiction_flag=true` 并通知 Agent |
| 并发保护 | 检测期间新记忆仍可写入（最终一致性） |
| 优先级 | 🟡 中 — 矛盾不频繁但影响严重 |

---

### 2.3 短板三：无记忆衰减 (Memory Decay)

#### 问题描述

所有记忆在检索时权重相同（除 entity_boost 外），导致：

- 一年前的记忆和一天前的记忆同等对待
- 用户已放弃的计划仍被检索出来
- 临时偏好（如"最近在减肥"）长期影响推荐

#### 根因

- Platform(云端 mem0) v3 有 Memory Decay（搜索时衰减旧记忆），OSS 无
- `search()` 的 `score` 只考虑语义相似度 + BM25 + entity_boost

#### 补齐方案

**方案 A：搜索时时间衰减（推荐）**

```python
class DecayFilter:
    def __init__(self, half_life_days: int = 30, whitelist: set = None):
        """
        Args:
            half_life_days: 半衰期（天数），默认 30 天
            whitelist: 不衰减的记忆 ID 集合（如核心事实）
        """
        self.half_life_days = half_life_days
        self.whitelist = whitelist or set()
    
    def apply(self, results: list, top_k: int = 20, buffer_multiplier: int = 5) -> list:
        """
        对搜索结果应用时间衰减。
        
        Args:
            results: mem0.search() 返回的结果列表（已按 score 排序）
            top_k: 最终返回数量
            buffer_multiplier: 缓冲区倍数（避免有效结果被丢弃）
        
        Returns:
            衰减重排后的结果
        """
        now = datetime.now(timezone.utc)
        decayed = []
        
        for r in results:
            # 白名单记忆不衰减
            if r.get("id") in self.whitelist:
                r["score"] *= 1.0
                r["decay_applied"] = False
            else:
                # 计算记忆年龄（天）
                age_days = self._calculate_age(r, now)
                
                # 指数衰减：score *= 0.5^(age/half_life)
                decay_multiplier = 0.5 ** (age_days / self.half_life_days)
                r["score"] *= decay_multiplier
                r["decay_applied"] = True
                r["decay_multiplier"] = decay_multiplier
            
            decayed.append(r)
        
        # 重排序
        decayed.sort(key=lambda x: x["score"], reverse=True)
        
        # 返回 top_k（从 buffer_multiplier * top_k 的池中选取，避免丢弃有效结果）
        buffer_size = min(len(decayed), top_k * buffer_multiplier)
        return decayed[:buffer_size][:top_k]
    
    def _calculate_age(self, memory: dict, now: datetime) -> float:
        """计算记忆年龄（天）"""
        created = memory.get("created_at")
        if created is None:
            return 0  # 无时间戳视为最新
        
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        
        delta = now - created
        return max(0, delta.total_seconds() / 86400)
```

**方案 B：写入时 TTL**

利用已有的 `expiration_date` 字段：

```python
# 为临时偏好设置较短 TTL
mem0.add(
    "用户最近在生酮饮食", 
    user_id="alice",
    expiration_date=datetime(2026, 10, 1)  # 3个月后自动过期
)
```

**方案 C：mentions 计数衰减**

FalkorDB 插件已维护 `mentions` 计数。被频繁提及的实体自然获得更高权重，长期不被提及的实体自然衰退。

#### 实施建议

| 维度 | 建议 |
|------|------|
| 衰减曲线 | 指数衰减，半衰期 30 天（可调） |
| 白名单 | 核心事实（如"用户姓名"、"用户 ID"）不衰减 |
| 缓冲区 | 取 `top_k * 5` 衰减后重排，避免有效结果被丢弃 |
| 优先级 | 🔴 高 — 直接影响搜索质量 |

---

### 2.4 短板四：无时间推理 (Temporal Reasoning)

#### 问题描述

用户问"我现在应该做什么？"，系统无法区分：

```
记忆 #1: "用户计划下周去东京"    (2026-07-20)
记忆 #2: "用户刚从东京回来"      (2026-07-25)
```

两条记忆都可能被检索回来，但一条是未来计划，一条是已完成事件。

#### 根因

- Platform(云端 mem0) v3 有 Temporal Reasoning，OSS 无
- 记忆只有 `created_at` 时间戳，无"事件发生时间"语义

#### 补齐方案

**方案 A：提取时标注时间语义 + 格式校验**

```python
# 在 custom_instructions 中增强（带输出格式校验）
TEMPORAL_INSTRUCTIONS = """
提取事实时，为每条记忆标注时间属性：
- PAST: 已发生的事件（如"用户昨天去了医院"）
- PRESENT: 当前状态（如"用户住在北京"）
- FUTURE: 计划/意图（如"用户下周要去东京"）
- TIMELESS: 永恒事实（如"用户姓名是张三"）

输出格式（严格 JSON）：
{
  "facts": [
    {
      "text": "用户昨天去了医院",
      "temporal": "PAST",
      "temporal_date": "2026-07-26",
      "importance": 3
    }
  ]
}

校验规则：
- temporal 必须是 PAST/PRESENT/FUTURE/TIMELESS 之一
- temporal_date 可选，但如果 temporal 为 PAST/FUTURE 则建议提供
- importance 为 1-5 整数（5=最重要，不衰减）
"""

def validate_temporal_output(output: dict) -> bool:
    """校验 LLM 输出的 temporal 格式"""
    valid_temporals = {"PAST", "PRESENT", "FUTURE", "TIMELESS"}
    
    for fact in output.get("facts", []):
        temporal = fact.get("temporal")
        if temporal not in valid_temporals:
            # 格式错误：降级为 TIMELESS
            fact["temporal"] = "TIMELESS"
        
        importance = fact.get("importance", 3)
        if not isinstance(importance, int) or importance < 1 or importance > 5:
            fact["importance"] = 3
    
    return True
```

**方案 B：搜索时时间过滤**

```python
def search_temporal(
    mem0_client, 
    query: str, 
    filters: dict,
    temporal_filter: str = None,
    **kwargs
) -> list:
    """
    带时间过滤的搜索。
    
    Args:
        temporal_filter: "PAST" | "PRESENT" | "FUTURE" | None
    """
    results = mem0_client.search(query, filters=filters, top_k=50, **kwargs)
    
    if temporal_filter:
        results = [
            r for r in results 
            if r.get("metadata", {}).get("temporal") == temporal_filter
        ]
    
    return results
```

#### 实施建议

| 维度 | 建议 |
|------|------|
| 实现成本 | 低 — 只需改 prompt + 元数据字段 + 格式校验 |
| 降级策略 | LLM 输出格式错误时降级为 TIMELESS |
| 优先级 | 🟡 中 — 对时间敏感型 Agent 重要 |

---

### 2.5 短板五：无自动遗忘/清理

#### 问题描述

记忆只增不减，导致：

1. 存储膨胀
2. 过时信息污染搜索结果
3. 临时信息（如"用户感冒了"）长期存在

#### 补齐方案

**方案 A：过期自动清理（带归档）**

```python
class CleanupScheduler:
    def __init__(self, mem0_client, archive_store, graph_client):
        self.mem0 = mem0_client
        self.archive = archive_store
        self.graph = graph_client
    
    def daily_cleanup(self, user_id: str = None):
        """每日清理任务"""
        # 1. 清理过期记忆（expiration_date < now）
        expired = self._find_expired_memories(user_id)
        for mem in expired:
            # 归档后再删除
            self.archive.store({
                "original_id": mem["id"],
                "text": mem["memory"],
                "metadata": mem.get("metadata", {}),
                "deleted_reason": "expired",
                "deleted_at": datetime.now(timezone.utc).isoformat(),
            })
            self.mem0.delete(mem["id"])
        
        # 2. 标记长期未被引用的记忆（90天无 mentions）
        stale = self._find_stale_memories(days=90, user_id=user_id)
        for mem in stale:
            metadata = mem.get("metadata", {})
            metadata["stale"] = True
            metadata["stale_since"] = datetime.now(timezone.utc).isoformat()
            self.mem0.update(mem["id"], metadata=metadata)
        
        # 3. FalkorDB 图清理（孤立节点）
        self._cleanup_graph(user_id)
    
    def _cleanup_graph(self, user_id: str):
        """清理 FalkorDB 中的孤立节点"""
        cypher = """
        MATCH (n:Entity)
        WHERE n.user_id = $user_id 
          AND n.mentions <= 1 
          AND n.last_updated < timestamp() - 90*86400000
        WITH n, size((n)--()) as connections
        WHERE connections = 0
        DETACH DELETE n
        """
        self.graph.query(cypher, {"user_id": user_id})
```

**方案 B：分级存储**

| 存储层 | 保留时间 | 检索权重 | 实现方式 |
|--------|----------|----------|----------|
| 热存储 (vector_store) | 90 天 | 1.0 | 默认 |
| 冷存储 (归档表) | 永久 | 0.3 | 手动迁移 |
| 已删除 | - | 0 | 删除 |

#### 实施建议

| 维度 | 建议 |
|------|------|
| 清理频率 | 每日凌晨 |
| 安全阀 | 清理前先归档，支持 30 天内恢复 |
| 并发保护 | 清理期间暂停该用户的 Consolidation |
| 优先级 | 🟡 中 — 影响长期运维成本 |

---

### 2.6 短板六：无可视化图谱面板

#### 问题描述

Platform(云端 mem0) 提供交互式 Graph View（实体关系可视化），OSS 无此能力。

#### 补齐方案

**方案 A：FalkorDB 原生可视化**

FalkorDB 自带 Web UI，可直接查看图结构：

```bash
docker run --rm -p 6379:6379 -p 3000:3000 falkordb/falkordb
# 访问 http://localhost:3000 查看图可视化
```

**方案 B：自定义面板**

基于 FalkorDB 的 Cypher 查询构建简单面板：

```python
# 查询某用户的实体关系图
MATCH path = (e1:Entity)-[r]-(e2:Entity)
WHERE e1.user_id = "alice"
RETURN path
```

#### 实施建议

| 维度 | 建议 |
|------|------|
| 优先级 | 🟢 低 — 运维需求，不影响 Agent 功能 |
| 实现成本 | 低 — FalkorDB 自带 |

---

## 3. 补齐优先级矩阵

| 优先级 | 短板 | 影响 | 实施成本 | 建议时间 |
|--------|------|------|----------|----------|
| P0 | 记忆合并 | 高 | 中 | 部署后 2 周内 |
| P0 | 记忆衰减 | 高 | 低 | 部署后 1 周内 |
| P1 | 矛盾检测 | 中 | 中 | 部署后 1 月内 |
| P1 | 自动清理 | 中 | 低 | 部署后 1 月内 |
| P2 | 时间推理 | 中 | 低 | 部署后 2 月内 |
| P3 | 可视化面板 | 低 | 低 | 按需 |

---

## 4. 推荐补齐架构

### 4.1 补齐层完整接口

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class GapConfig:
    """补齐层配置"""
    decay_half_life_days: int = 30
    decay_whitelist: set = field(default_factory=set)
    decay_buffer_multiplier: int = 5
    archive_store: object = None  # 归档存储实例
    llm_client: object = None     # LLM 客户端实例
    enable_metrics: bool = True


class MemoryGapLayer:
    """
    mem0 + FalkorDB 补齐层 — 完整接口
    
    设计原则：
    1. 透明包装：所有 mem0 方法均可通过 gap_layer 调用
    2. 功能开关：每个补齐能力可独立启用/禁用
    3. 可观测：所有操作记录 metrics 和 logs
    4. 可回滚：支持按用户/百分比灰度发布
    """
    
    def __init__(
        self, 
        mem0_client: Memory, 
        graph_client = None,
        config: GapConfig = None
    ):
        self.mem0 = mem0_client
        self.graph = graph_client
        self.config = config or GapConfig()
        
        # 补齐服务
        self.consolidator = ConsolidationService(
            mem0_client, 
            self.config.archive_store,
            self.config.llm_client
        )
        self.contradiction_detector = ContradictionDetector(
            mem0_client, 
            self.config.llm_client
        )
        self.decay_filter = DecayFilter(
            half_life_days=self.config.decay_half_life_days,
            whitelist=self.config.decay_whitelist
        )
        self.cleanup_scheduler = CleanupScheduler(
            mem0_client, 
            self.config.archive_store, 
            graph_client
        )
        
        # 功能开关
        self.feature_flags = FeatureFlags()
        
        # 指标收集
        self.metrics = GapMetrics()
    
    # ─── 核心 CRUD 接口（完整覆盖 mem0 所有方法）───
    
    def add(self, messages, *, user_id=None, agent_id=None, run_id=None,
            metadata=None, expiration_date=None, infer=True,
            memory_type=None, prompt=None, **kwargs):
        """
        写入时：矛盾检测 → 正常写入 → 异步实体链接
        """
        with self.metrics.timer("add"):
            # 功能开关：矛盾检测
            if self.feature_flags.is_enabled("contradiction_detection", user_id):
                contradiction = self.contradiction_detector.check(messages, filters={
                    "user_id": user_id, "agent_id": agent_id, "run_id": run_id
                })
                if contradiction.has_contradiction:
                    # 标记但不阻止写入
                    metadata = metadata or {}
                    metadata["contradiction_flag"] = True
                    metadata["contradiction_details"] = contradiction.to_dict()
                    self.metrics.increment("contradiction_detected")
            
            # 正常写入
            result = self.mem0.add(
                messages, user_id=user_id, agent_id=agent_id, run_id=run_id,
                metadata=metadata, expiration_date=expiration_date,
                infer=infer, memory_type=memory_type, prompt=prompt, **kwargs
            )
            
            return result
    
    def search(self, query, *, top_k=20, filters=None, threshold=0.1,
               rerank=False, explain=False, show_expired=False, **kwargs):
        """
        搜索时：正常搜索 → 时间衰减 → 返回
        """
        with self.metrics.timer("search"):
            # 扩大搜索范围（衰减后重排需要更多候选）
            search_top_k = top_k * self.config.decay_buffer_multiplier
            
            results = self.mem0.search(
                query, top_k=search_top_k, filters=filters,
                threshold=threshold, rerank=rerank, explain=explain,
                show_expired=show_expired, **kwargs
            )
            
            # 功能开关：时间衰减
            if self.feature_flags.is_enabled("decay_filter", filters.get("user_id") if filters else None):
                results = self.decay_filter.apply(results, top_k=top_k)
            else:
                results = results[:top_k]
            
            return results
    
    def get(self, memory_id):
        """按 ID 获取记忆"""
        return self.mem0.get(memory_id)
    
    def get_all(self, *, filters=None, top_k=20, show_expired=False, **kwargs):
        """获取所有记忆"""
        return self.mem0.get_all(filters=filters, top_k=top_k, show_expired=show_expired, **kwargs)
    
    def update(self, memory_id, text=None, metadata=None, expiration_date=_UNSET):
        """
        更新记忆：同步清理 entity_store
        """
        with self.metrics.timer("update"):
            result = self.mem0.update(memory_id, text=text, metadata=metadata, expiration_date=expiration_date)
            
            # 如果文本变化，需要重新链接实体
            if text is not None:
                # mem0 内部会自动处理 entity_store 清理
                pass
            
            return result
    
    def delete(self, memory_id):
        """
        删除记忆：同步清理 entity_store + FalkorDB
        """
        with self.metrics.timer("delete"):
            # 获取记忆详情（用于清理）
            mem = self.mem0.get(memory_id)
            
            # 删除（mem0 内部自动清理 entity_store）
            result = self.mem0.delete(memory_id)
            
            # 清理 FalkorDB 中的孤立节点
            if self.graph and mem:
                self._cleanup_orphan_nodes(mem)
            
            return result
    
    def delete_all(self, user_id=None, agent_id=None, run_id=None):
        """删除所有记忆"""
        return self.mem0.delete_all(user_id=user_id, agent_id=agent_id, run_id=run_id)
    
    def history(self, memory_id):
        """获取记忆变更历史"""
        return self.mem0.history(memory_id)
    
    def reset(self, confirm: bool = False):
        """
        重置所有记忆（危险操作，需要确认）
        
        Args:
            confirm: 必须为 True 才会执行重置
        """
        if not confirm:
            raise ValueError(
                "reset() 是危险操作，将清除所有记忆。"
                "如需执行，请传入 confirm=True"
            )
        
        logger.warning("MemoryGapLayer.reset() called - clearing all memories")
        return self.mem0.reset()
    
    def close(self):
        """关闭连接"""
        return self.mem0.close()
    
    # ─── 补齐层特有接口 ───
    
    def consolidate(self, user_id: str, topic: str = None, dry_run: bool = False):
        """手动触发记忆合并"""
        with self.metrics.timer("consolidate"):
            return self.consolidator.consolidate_user(user_id, topic, dry_run)
    
    def rollback_consolidation(self, archive_ids: list):
        """回滚合并操作"""
        return self.consolidator.rollback_consolidation(archive_ids)
    
    def daily_cleanup(self, user_id: str = None):
        """执行每日清理"""
        with self.metrics.timer("cleanup"):
            return self.cleanup_scheduler.daily_cleanup(user_id)
    
    def search_batch(self, queries: list, **kwargs):
        """批量搜索"""
        return self.mem0.search_batch(queries, **kwargs)
    
    # ─── 内部方法 ───
    
    def _cleanup_orphan_nodes(self, memory: dict):
        """
        清理 FalkorDB 中的孤立节点。
        
        当删除记忆时，关联的实体节点可能变成孤立节点（无任何关系）。
        此方法通过 Cypher 查询找到并删除这些节点，防止图膨胀。
        """
        if not self.graph:
            return
        
        try:
            # 从记忆文本中提取关联的实体名
            entity_names = memory.get("metadata", {}).get("entity_names", [])
            
            for name in entity_names:
                # 检查该实体是否还有其他关系
                cypher = """
                MATCH (n:Entity {name: $name})
                WHERE n.user_id = $user_id
                WITH n, size((n)--()) as connections
                WHERE connections = 0
                DELETE n
                """
                self.graph.query(cypher, {
                    "name": name,
                    "user_id": memory.get("metadata", {}).get("user_id")
                })
        except Exception as e:
            logger.warning(f"Failed to cleanup orphan nodes: {e}")
```

### 4.2 功能开关设计

```python
class FeatureFlags:
    """
    功能开关 — 支持按用户/百分比灰度
    
    配置示例：
    {
        "decay_filter": {
            "enabled": true,
            "rollout_percentage": 50,  // 50% 用户启用
            "user_whitelist": ["alice", "bob"],  // 这些用户强制启用
            "user_blacklist": ["charlie"]  // 这些用户强制禁用
        },
        "contradiction_detection": {
            "enabled": false,
            "rollout_percentage": 0
        }
    }
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
    
    def is_enabled(self, feature: str, user_id: str = None) -> bool:
        feature_config = self.config.get(feature, {})
        if not feature_config.get("enabled", False):
            return False
        
        # 白名单优先
        if user_id and user_id in feature_config.get("user_whitelist", []):
            return True
        
        # 黑名单
        if user_id and user_id in feature_config.get("user_blacklist", []):
            return False
        
        # 百分比灰度
        rollout = feature_config.get("rollout_percentage", 100)
        if user_id:
            # 基于 user_id 哈希决定（保证同一用户始终在同一组）
            hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 100
            return hash_val < rollout
        
        return True
    
    def enable(self, feature: str, rollout_percentage: int = 100):
        """启用功能"""
        self.config.setdefault(feature, {})["enabled"] = True
        self.config[feature]["rollout_percentage"] = rollout_percentage
    
    def disable(self, feature: str):
        """禁用功能"""
        self.config.setdefault(feature, {})["enabled"] = False
    
    def disable_all(self):
        """禁用所有功能"""
        for feature in self.config:
            self.config[feature]["enabled"] = False
    
    def enable_all(self):
        """启用所有功能"""
        for feature in self.config:
            self.config[feature]["enabled"] = True
            self.config[feature]["rollout_percentage"] = 100
    
    def add_to_blacklist(self, user_id: str, feature: str = None):
        """将用户加入黑名单"""
        if feature:
            self.config.setdefault(feature, {}).setdefault("user_blacklist", []).append(user_id)
        else:
            for f in self.config:
                self.config[f].setdefault("user_blacklist", []).append(user_id)
```

### 4.3 回滚方案

```python
class RollbackManager:
    """
    回滚管理器 — 支持快速降级到纯 mem0
    
    降级策略：
    1. 全量降级：禁用所有补齐功能
    2. 按用户降级：只禁用特定用户的补齐功能
    3. 按功能降级：只禁用某一补齐功能（如衰减）
    """
    
    def __init__(self, gap_layer: MemoryGapLayer):
        self.gap = gap_layer
    
    def full_rollback(self):
        """全量降级：所有用户、所有功能"""
        self.gap.feature_flags.disable_all()
        logger.warning("Gap Layer fully rolled back to pure mem0")
    
    def rollback_user(self, user_id: str):
        """按用户降级"""
        self.gap.feature_flags.add_to_blacklist(user_id)
    
    def rollback_feature(self, feature: str):
        """按功能降级"""
        self.gap.feature_flags.disable(feature)
    
    def restore_feature(self, feature: str, rollout_percentage: int = 100):
        """恢复功能（可指定灰度比例）"""
        self.gap.feature_flags.enable(feature, rollout_percentage)
```

---

## 5. 为何必须补齐

### 5.1 不补齐的后果

| 时间线 | 问题 | 影响 |
|--------|------|------|
| 部署后 1 周 | 记忆开始膨胀 | 搜索延迟增加，token 消耗上升 |
| 部署后 1 月 | 矛盾记忆积累 | Agent 回答不一致，用户信任下降 |
| 部署后 3 月 | 过时记忆污染 | 推荐质量下降，Agent "看起来傻了" |
| 部署后 6 月 | 存储成本显著 | FalkorDB 节点数膨胀，查询变慢 |

### 5.2 补齐后的收益

| 维度 | 改善 |
|------|------|
| 搜索质量 | 时间衰减 + 合并 → 返回更精准 |
| 存储效率 | 清理 + 合并 → 减少 60-80% 冗余记忆 |
| Agent 一致性 | 矛盾检测 → 减少自相矛盾回答 |
| 用户体验 | 时间推理 → 正确理解"之前/现在/计划" |
| 运维成本 | 自动清理 → 减少人工干预 |

---

## 6. 风险评估

### 6.1 FalkorDB 插件风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| mem0 升级导致插件失效 | 高 | 图功能不可用 | 1. 锁定 mem0 版本<br>2. staging 环境先验证<br>3. 维护 fork |
| 插件维护者停止更新 | 中 | 安全漏洞无人修 | 1. 评估自维护能力<br>2. 准备降级方案（回退到 entity_store） |
| monkey-patching 冲突 | 低 | 运行时异常 | 1. 集成测试覆盖<br>2. 监控异常日志 |
| FalkorDB 性能瓶颈 | 中 | 查询变慢 | 1. 监控图节点数<br>2. 定期清理孤立节点 |

### 6.2 补齐层风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 合并时 LLM 丢失细节 | 中 | 信息不可逆丢失 | 1. 归档原始记忆<br>2. 支持回滚<br>3. dry_run 模式 |
| 误删有效记忆 | 低 | 用户体验下降 | 1. 先归档后删除<br>2. 30 天保留期 |
| 矛盾检测误报 | 中 | 有效记忆被标记 | 1. 不自动删除<br>2. 只标记待审核 |
| 衰减导致旧知识丢失 | 低 | 长期偏好被遗忘 | 1. 白名单机制<br>2. importance=5 不衰减 |

### 6.3 回滚触发条件

| 条件 | 动作 |
|------|------|
| 搜索延迟 p95 > 1000ms 持续 5 分钟 | 禁用衰减功能 |
| 合并服务错误率 > 5% | 暂停合并，人工介入 |
| FalkorDB 不可用 | 降级到纯 mem0（entity_store） |
| 用户投诉记忆丢失 | 全量回滚，恢复归档 |

---

## 7. 测试策略

### 7.1 单元测试

```python
# test_decay_filter.py
def test_decay_filter_basic():
    """测试基本衰减逻辑"""
    decay = DecayFilter(half_life_days=30)
    results = [
        {"id": "1", "score": 0.9, "created_at": "2026-07-27T00:00:00Z"},  # 今天
        {"id": "2", "score": 0.9, "created_at": "2026-06-27T00:00:00Z"},  # 30天前
    ]
    
    filtered = decay.apply(results, top_k=2)
    
    # 30天前的记忆分数应该减半
    assert filtered[0]["id"] == "1"  # 新记忆排前面
    assert filtered[1]["decay_multiplier"] == 0.5

def test_decay_whitelist():
    """测试白名单不衰减"""
    decay = DecayFilter(half_life_days=30, whitelist={"old_important"})
    results = [
        {"id": "old_important", "score": 0.8, "created_at": "2025-01-01T00:00:00Z"},
        {"id": "new_normal", "score": 0.7, "created_at": "2026-07-27T00:00:00Z"},
    ]
    
    filtered = decay.apply(results, top_k=2)
    
    # 白名单记忆不衰减，可能排前面
    old_mem = next(r for r in filtered if r["id"] == "old_important")
    assert old_mem["decay_applied"] == False

# test_contradiction_detector.py
def test_contradiction_detection():
    """测试矛盾检测"""
    llm_mock = Mock()
    llm_mock.generate.return_value = '{"is_contradictory": true, "confidence": 0.9, "reason": "不同城市"}'
    mem0_mock = Mock()
    mem0_mock.search.return_value = [{"memory": "用户住在上海", "id": "mem_001"}]
    
    detector = ContradictionDetector(mem0_mock, llm_mock)
    result = detector.check("用户住在北京", {"user_id": "alice"})
    
    assert result.has_contradiction == True
    assert result.contradictions[0].confidence == 0.9
    llm_mock.generate.assert_called_once()

# test_consolidation.py
def test_consolidation_with_backup():
    """测试合并时备份原始记忆"""
    mem0_mock = Mock()
    mem0_mock.search.return_value = [
        {"id": "1", "memory": "Max 是狗"},
        {"id": "2", "memory": "Max 是金毛"},
    ]
    archive_mock = Mock()
    archive_mock.store.side_effect = ["arc_001", "arc_002"]
    llm_mock = Mock()
    llm_mock.generate.return_value = '{"merged": ["Max 是金毛犬"]}'
    
    service = ConsolidationService(mem0_mock, archive_mock, llm_mock)
    result = service.consolidate_user("alice", "宠物")
    
    # 验证归档被调用
    assert archive_mock.store.call_count == 2
    assert len(result.archived_ids) == 2
    assert result.old_count == 2
    assert result.new_count == 1

def test_consolidation_rollback():
    """测试合并回滚"""
    mem0_mock = Mock()
    archive_mock = Mock()
    archive_mock.get.side_effect = [
        {"text": "Max 是狗", "user_id": "alice"},
        {"text": "Max 是金毛", "user_id": "alice"},
    ]
    llm_mock = Mock()
    
    service = ConsolidationService(mem0_mock, archive_mock, llm_mock)
    
    # 回滚
    service.rollback_consolidation(["arc_001", "arc_002"])
    
    # 验证原始记忆被恢复
    assert mem0_mock.add.call_count == 2
    assert archive_mock.delete.call_count == 2

def test_consolidation_dry_run():
    """测试 dry_run 模式不实际执行"""
    mem0_mock = Mock()
    mem0_mock.search.return_value = [
        {"id": "1", "memory": "Max 是狗"},
        {"id": "2", "memory": "Max 是金毛"},
    ]
    archive_mock = Mock()
    llm_mock = Mock()
    llm_mock.generate.return_value = '{"merged": ["Max 是金毛犬"]}'
    
    service = ConsolidationService(mem0_mock, archive_mock, llm_mock)
    result = service.consolidate_user("alice", "宠物", dry_run=True)
    
    # dry_run 不应调用 delete 或 add
    mem0_mock.delete.assert_not_called()
    mem0_mock.add.assert_not_called()
    archive_mock.store.assert_not_called()
```

### 7.2 集成测试

```python
# test_gap_layer_integration.py
def test_add_with_contradiction_detection():
    """测试写入时矛盾检测集成"""
    mem0_mock = Mock()
    llm_mock = Mock()
    llm_mock.generate.return_value = '{"is_contradictory": false, "confidence": 0.1, "reason": ""}'
    
    gap = MemoryGapLayer(mem0_mock, llm_client=llm_mock)
    gap.feature_flags.enable("contradiction_detection")
    
    # 写入记忆
    gap.add("用户住在北京", user_id="alice")
    
    # 验证 LLM 被调用检测矛盾
    llm_mock.generate.assert_called()
    
    # 验证写入成功
    mem0_mock.add.assert_called_once()

def test_search_with_decay():
    """测试搜索时衰减集成"""
    mem0_mock = Mock()
    mem0_mock.search.return_value = [
        {"id": "1", "score": 0.9, "memory": "新记忆", "created_at": "2026-07-27T00:00:00Z"},
        {"id": "2", "score": 0.85, "memory": "旧记忆", "created_at": "2026-06-27T00:00:00Z"},
    ]
    
    gap = MemoryGapLayer(mem0_mock)
    gap.feature_flags.enable("decay_filter")
    
    # 搜索
    results = gap.search("测试", user_id="alice", top_k=10)
    
    # 验证结果已衰减重排
    assert len(results) <= 10
    # 新记忆应该排前面
    assert results[0]["id"] == "1"

def test_full_rollback():
    """测试全量回滚"""
    mem0_mock = Mock()
    llm_mock = Mock()
    
    gap = MemoryGapLayer(mem0_mock, llm_client=llm_mock)
    rollback = RollbackManager(gap)
    
    # 启用所有功能
    gap.feature_flags.enable_all()
    
    # 回滚
    rollback.full_rollback()
    
    # 验证所有功能已禁用
    assert not gap.feature_flags.is_enabled("decay_filter")
    assert not gap.feature_flags.is_enabled("contradiction_detection")

def test_reset_requires_confirmation():
    """测试 reset 需要确认"""
    mem0_mock = Mock()
    gap = MemoryGapLayer(mem0_mock)
    
    # 不传 confirm 应该报错
    try:
        gap.reset()
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "confirm=True" in str(e)
    
    # 传 confirm=True 应该成功
    gap.reset(confirm=True)
    mem0_mock.reset.assert_called_once()
```

### 7.3 回归测试

| 场景 | 测试内容 | 通过标准 |
|------|----------|----------|
| 纯 mem0 行为 | 禁用所有补齐功能，验证与原生 mem0 行为一致 | API 返回结果完全一致 |
| 单功能启用 | 逐个启用补齐功能，验证不影响其他功能 | 其他功能行为不变 |
| 全功能启用 | 所有功能启用，验证整体行为 | 无异常，性能达标 |
| 回滚后行为 | 回滚后验证恢复到纯 mem0 | 与原生 mem0 一致 |

---

## 8. 成本估算

### 8.1 LLM 调用成本（多模型对照）

| 操作 | 每次调用 token 数 | GPT-4o-mini | Claude Sonnet 3.5 | Ollama (本地) |
|------|------------------|-------------|-------------------|---------------|
| 记忆合并 | ~500 in + 200 out | ~$0.00019 | ~$0.00225 | $0 |
| 矛盾检测 | ~300 in + 100 out | ~$0.00011 | ~$0.00075 | $0 |
| 时间推理 | 已在提取时完成 | $0 | $0 | $0 |
| **1000 用户/日总计** | | **~$0.30/日** | **~$3.00/日** | **$0/日** |
| **月成本** | | **~$9/月** | **~$90/月** | **$0/月** |

> 注：GPT-4o-mini 定价 $0.15/1M input, $0.60/1M output；Claude Sonnet 3.5 定价 $3/1M input, $15/1M output

### 8.2 存储成本

| 资源 | 规格 | 月成本 (AWS) |
|------|------|-------------|
| FalkorDB | 1 GB RAM, 10 GB 存储 | ~$50 (ElastiCache) |
| Qdrant | 2 GB RAM, 20 GB 存储 | ~$40 (managed) |
| 归档存储 | 100 GB PostgreSQL | ~$25 (RDS) |
| **总计** | | **~$115/月** |

### 8.3 计算资源

| 组件 | 规格 | 说明 |
|------|------|------|
| Gap Layer | 0.5 vCPU, 512 MB | 轻量 Python 服务 |
| Cleanup Worker | 0.2 vCPU, 256 MB | 定时任务 |
| **总计** | 0.7 vCPU, 768 MB | ~$30/月 |

### 8.4 总成本

| 项目 | 月成本 (GPT-4o-mini) | 月成本 (Claude Sonnet) | 月成本 (Ollama) |
|------|---------------------|----------------------|-----------------|
| LLM 调用 | ~$9 | ~$90 | $0 |
| 存储 | ~$115 | ~$115 | ~$115 |
| 计算 | ~$30 | ~$30 | ~$30 |
| **总计** | **~$154/月** | **~$235/月** | **~$145/月** |

> 注：以上为 1000 活跃用户的估算，实际成本随用户数线性增长。

---

## 9. 隐私与合规

### 9.1 数据分类

| 数据类别 | 示例 | 保护级别 |
|----------|------|----------|
| 个人身份信息 (PII) | 姓名、地址、电话 | 高 — 加密存储 |
| 行为数据 | 搜索历史、偏好 | 中 — 访问控制 |
| 系统数据 | 记忆 ID、时间戳 | 低 — 常规保护 |

### 9.2 GDPR 合规

| 要求 | 实现方式 |
|------|----------|
| 删除权 (Right to Erasure) | `delete_all(user_id=...)` 删除所有记忆 |
| 数据可携带权 | `get_all(user_id=...)` 导出所有记忆 |
| 同意管理 | 见下方实现 |
| 数据最小化 | 只提取必要事实，不存储原始对话 |

**同意管理实现**：

```python
class ConsentManager:
    """
    用户同意管理器
    
    存储结构：
    - user_id: 用户 ID
    - consent_given: 是否同意记忆存储
    - consent_date: 同意日期
    - consent_purpose: 同意用途（如"个性化推荐"）
    - data_retention_days: 数据保留天数
    
    存储位置：独立 PostgreSQL 表（与记忆数据分离）
    """
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    def check_consent(self, user_id: str) -> bool:
        """检查用户是否同意记忆存储"""
        result = self.db.query(
            "SELECT consent_given FROM consent WHERE user_id = %s",
            (user_id,)
        )
        if not result:
            return False  # 无记录 = 未同意
        return result[0]["consent_given"]
    
    def record_consent(self, user_id: str, purpose: str, retention_days: int = 365):
        """记录用户同意"""
        self.db.execute("""
            INSERT INTO consent (user_id, consent_given, consent_date, consent_purpose, data_retention_days)
            VALUES (%s, true, NOW(), %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                consent_given = true,
                consent_date = NOW(),
                consent_purpose = %s,
                data_retention_days = %s
        """, (user_id, purpose, retention_days, purpose, retention_days))
    
    def revoke_consent(self, user_id: str):
        """撤销同意（触发数据删除）"""
        self.db.execute(
            "UPDATE consent SET consent_given = false WHERE user_id = %s",
            (user_id,)
        )
        # 触发删除所有记忆
        # mem0.delete_all(user_id=user_id)
```

### 9.3 数据驻留

| 部署方式 | 数据位置 | 适用场景 |
|----------|----------|----------|
| 自部署 | 用户指定 | 有数据驻留要求 |
| Platform(云端 mem0) | US (expandable) | 无特殊要求 |

---

## 10. 多 Agent 隔离

### 10.1 隔离级别

```python
# mem0 支持五级隔离
filters = {
    "user_id": "alice",      # 用户级
    "agent_id": "assistant_1",  # Agent 级
    "run_id": "session_123",    # 会话级
    "app_id": "my_app",         # 应用级
    "actor_id": "admin"         # 行为者级
}
```

### 10.2 跨 Agent 记忆共享

```python
# 场景：多个 Agent 共享用户偏好
# 方案：使用相同的 user_id，不同 agent_id

# Agent A 写入
mem0.add("用户喜欢咖啡", user_id="alice", agent_id="agent_a")

# Agent B 搜索（只能看到 user_id=alice 的记忆）
results = mem0.search("用户喜欢什么", filters={"user_id": "alice", "agent_id": "agent_b"})

# 如果需要跨 Agent 共享，搜索时不指定 agent_id
results = mem0.search("用户喜欢什么", filters={"user_id": "alice"})
```

### 10.3 隔离策略建议

| 场景 | 策略 |
|------|------|
| 同一用户、不同 Agent | 共享 user_id，隔离 agent_id |
| 不同用户 | 严格隔离 user_id |
| 管理员查看 | 使用 actor_id 审计 |

---

## 11. 冷启动

### 11.1 新用户无记忆

当新用户首次使用 Agent 时，记忆系统为空，搜索返回空结果。此时 Agent 无法提供个性化体验。

### 11.2 冷启动策略

| 策略 | 实现 | 适用场景 |
|------|------|----------|
| 种子记忆 | 注册时添加基本偏好 | 已知用户画像 |
| 探索模式 | 前 N 轮对话主动询问偏好 | 未知用户画像 |
| 默认行为 | 无记忆时使用通用回复 | 所有场景 |
| 迁移学习 | 从相似用户迁移初始记忆 | 有用户分群数据 |

### 11.3 种子记忆示例

```python
def onboard_new_user(user_id: str, initial_preferences: dict):
    """新用户注册时添加种子记忆"""
    for key, value in initial_preferences.items():
        mem0.add(f"用户{key}是{value}", user_id=user_id)

# 使用示例
onboard_new_user("alice", {
    "姓名": "Alice",
    "职业": "软件工程师",
    "兴趣": "阅读、徒步"
})
```

### 11.4 探索模式示例

```python
def explore_user_preferences(user_id: str, turn_count: int):
    """
    前 N 轮主动询问用户偏好
    
    Args:
        user_id: 用户 ID
        turn_count: 当前对话轮次
    """
    exploration_questions = [
        "你平时喜欢做什么？",
        "你有什么特别感兴趣的领域吗？",
        "你更喜欢哪种工作方式？",
    ]
    
    if turn_count <= len(exploration_questions):
        return exploration_questions[turn_count - 1]
    
    return None  # 探索结束
```

---

## 12. 备份与恢复

### 12.1 FalkorDB 备份

```bash
# 方法 1：RDB 持久化备份（推荐，所有版本支持）
docker exec falkordb redis-cli SAVE
docker cp falkordb:/data/backup.rdb ./backup.rdb

# 方法 2：AOF 持久化备份（如果启用）
docker exec falkordb redis-cli BGREWRITEAOF
docker cp falkordb:/data/appendonly.aof ./appendonly.aof

# 方法 3：图导出（如果 GRAPH.EXPORT 可用）
docker exec falkordb redis-cli GRAPH.EXPORT "mem0_alice" > alice_backup.graph
```

### 12.2 记忆备份

```python
# 导出所有记忆
all_memories = mem0.get_all(user_id="alice")
with open("alice_memories.json", "w") as f:
    json.dump(all_memories, f)
```

### 12.3 灾难恢复

| 场景 | 恢复步骤 |
|------|----------|
| FalkorDB 数据丢失 | 1. 重启 FalkorDB<br>2. 从 RDB/AOF 备份恢复<br>3. 重新运行 Consolidation |
| 记忆误删 | 1. 从归档表恢复<br>2. 重新添加到 mem0 |
| 全量灾难 | 1. 恢复 PostgreSQL<br>2. 恢复 FalkorDB<br>3. 验证数据一致性 |

---

## 13. 评估体系

### 13.1 记忆质量指标

| 指标 | 计算方式 | 目标值 |
|------|----------|--------|
| 召回率 | 相关记忆被检索到的比例 | > 90% |
| 精确率 | 检索结果中相关的比例 | > 80% |
| 矛盾率 | 矛盾记忆数 / 总记忆数 | < 1% |
| 记忆膨胀率 | 每日新增记忆数 / 用户 | < 5 |

### 13.2 A/B 测试框架

```python
def ab_test_search(user_id: str, query: str):
    """A/B 测试：对比有无衰减的搜索质量"""
    # 对照组：无衰减
    baseline = mem0.search(query, filters={"user_id": user_id})
    
    # 实验组：有衰减
    decayed = gap.search(query, user_id=user_id)
    
    # 记录指标
    metrics.log_comparison(user_id, baseline, decayed)
```

### 13.3 性能基线

| 指标 | 当前值（待测量） | 目标值 |
|------|------------------|--------|
| 搜索延迟 p50 | ___ ms | < 100ms |
| 搜索延迟 p95 | ___ ms | < 500ms |
| 写入延迟 p95 | ___ ms | < 1000ms |
| FalkorDB 查询 p95 | ___ ms | < 200ms |

### 13.4 记忆质量自动评估

```python
class MemoryQualityAssessor:
    """
    记忆质量自动评估器
    
    定期运行，输出质量报告，触发告警。
    """
    
    def __init__(self, gap_layer: MemoryGapLayer):
        self.gap = gap_layer
    
    def assess_user(self, user_id: str) -> QualityReport:
        """评估指定用户的记忆质量"""
        all_memories = self.gap.get_all(filters={"user_id": user_id})
        
        # 计算指标
        total = len(all_memories)
        expired = sum(1 for m in all_memories if self._is_expired(m))
        stale = sum(1 for m in all_memories if m.get("metadata", {}).get("stale"))
        contradictions = self._count_contradictions(all_memories)
        
        return QualityReport(
            user_id=user_id,
            total_memories=total,
            expired_ratio=expired / total if total > 0 else 0,
            stale_ratio=stale / total if total > 0 else 0,
            contradiction_count=contradictions,
            health_score=self._calculate_health(total, expired, stale, contradictions)
        )
    
    def _calculate_health(self, total, expired, stale, contradictions) -> float:
        """计算健康分数 (0-100)"""
        if total == 0:
            return 100.0
        
        # 过期记忆扣分
        expired_penalty = (expired / total) * 30
        # 陈旧记忆扣分
        stale_penalty = (stale / total) * 20
        # 矛盾记忆扣分
        contradiction_penalty = min(contradictions * 5, 30)
        
        return max(0, 100 - expired_penalty - stale_penalty - contradiction_penalty)
```

---

## 14. 何时不需要补齐（决策树）

### 14.1 决策流程

```
你的 Agent 是否需要补齐层？
│
├─ 预期记忆总量 < 100 条/用户？
│   └─ 是 → 不需要合并和清理，只需衰减
│
├─ 单用户、单 Agent？
│   └─ 是 → 不需要多 Agent 隔离
│
├─ 无时间敏感场景（如静态知识库）？
│   └─ 是 → 不需要时间推理
│
├─ 短期项目（< 3 个月）？
│   └─ 是 → 记忆膨胀不是问题，只需基础监控
│
├─ 已有 Platform(云端 mem0) 订阅？
│   └─ 是 → 直接使用 Platform(云端 mem0) 的衰减/时间推理，无需自建
│
└─ 以上都不满足 → 需要完整补齐层
```

### 14.2 场景对照表

| 场景 | 需要的能力 | 不需要的能力 |
|------|-----------|-------------|
| 个人助手（单用户） | 衰减、合并 | 多 Agent 隔离 |
| 企业多 Agent 平台 | 全部 | - |
| 客服机器人 | 衰减、矛盾检测、清理 | 时间推理 |
| 编程助手 | 衰减、合并 | 矛盾检测 |
| 短期原型验证 | 基础监控 | 全部补齐 |

---

## 15. 替代方案对比

### 15.1 方案对比矩阵

| 维度 | mem0 + FalkorDB | OpenViking | Zep | Letta |
|------|-----------------|------------|-----|-------|
| **开源** | ✅ Apache 2.0 | ✅ MIT | ❌ 商业 | ✅ MIT |
| **自部署** | ✅ | ✅ | ❌ (云优先) | ✅ |
| **图数据库** | ✅ FalkorDB | ✅ 内置 | ✅ 内置 | ❌ |
| **时间推理** | ❌ (需补齐) | ✅ | ✅ | ✅ |
| **记忆衰减** | ❌ (需补齐) | ✅ | ✅ | ✅ |
| **自动合并** | ❌ (需补齐) | ✅ | ✅ | ✅ |
| **多 Agent** | ✅ 五级隔离 | ✅ | ✅ | ✅ |
| **成熟度** | 高 (YC S24) | 中 | 高 | 中 |
| **社区** | 大 (10k+ stars) | 小 | 中 | 中 |
| **成本** | 低 (自部署) | 低 | 高 (按量) | 低 |

### 15.2 选择建议

| 场景 | 推荐方案 |
|------|----------|
| 需要完全控制 + 已有 mem0 投入 | mem0 + FalkorDB + 补齐层 |
| 需要开箱即用的时间推理/衰减 | Zep 或 OpenViking |
| 需要最强的图能力 | mem0 + FalkorDB |
| 需要最快的开发速度 | Letta 或 Zep |
| 预算有限 + 技术能力强 | mem0 + FalkorDB |
| 预算充足 + 需要企业级支持 | Zep |

### 15.3 mem0 + FalkorDB 的独特价值

1. **图关系是真正的图**：不是模拟的向量链接，而是可遍历的 Cypher 图
2. **数据完全自主**：所有数据存储在用户自有基础设施
3. **灵活的补齐层**：可按需选择补齐能力，避免过度工程
4. **成熟的向量搜索**：mem0 的语义搜索 + BM25 融合是生产验证的

### 15.4 mem0 + FalkorDB 的妥协

1. **需要自建补齐层**：衰减、合并、时间推理都需要额外开发
2. **插件是 Alpha**：mem0-falkordb 不是 mem0.ai 官方维护
3. **无官方 Dashboard**：可视化需要自建或使用 FalkorDB Web UI
4. **运维复杂度**：需要维护向量库 + 图数据库 + 补齐层三个组件

---

## 16. 实施路线图

### Phase 1：快速见效（1-2 周）

- [ ] 实现 Decay Filter（搜索时时间衰减）
- [ ] 配置 FalkorDB + mem0-falkordb 插件
- [ ] 设置基础监控（记忆数量/用户、搜索延迟）
- [ ] 测量性能基线

### Phase 2：核心补齐（1 月）

- [ ] 实现 Consolidation Service（自动合并 + 归档 + 回滚）
- [ ] 实现 Cleanup Scheduler（定时清理）
- [ ] 添加矛盾检测（标记 + 通知）
- [ ] 实现功能开关（Feature Flags）

### Phase 3：增强能力（2 月）

- [ ] 实现 Temporal Reasoner（时间推理 + 格式校验）
- [ ] 构建运维面板（记忆健康度、图谱可视化）
- [ ] 接入告警（记忆膨胀、矛盾积累）
- [ ] 实现 A/B 测试框架

### Phase 4：长期演进

- [ ] 评估是否升级到 Platform(云端 mem0)（原生支持衰减/时间推理）
- [ ] 实现自适应衰减曲线（根据用户行为动态调整）
- [ ] 构建记忆质量评估体系（自动评估记忆系统健康度）
- [ ] 实现多 Agent 隔离策略配置

---

## 17. 附录

### 17.1 关键参考资源

| 资源 | 路径/链接 |
|------|-----------|
| mem0 官方文档 | https://docs.mem0.ai |
| mem0-falkordb GitHub | https://github.com/FalkorDB/mem0-falkordb |
| mem0 v2→v3 迁移指南 | `docs/migration/oss-v2-to-v3.mdx` |
| Graph Memory 说明 | `docs/Platform(云端 mem0)/features/graph-memory.mdx` |
| Platform(云端 mem0) vs OSS 对比 | `docs/Platform(云端 mem0)/Platform(云端 mem0)-vs-oss.mdx` |
| ADDITIVE_EXTRACTION_PROMPT | `mem0/configs/prompts.py` L468 |

### 17.2 完整配置示例

```python
# ─── 完整部署配置：mem0 + FalkorDB + 补齐层 ───

from mem0 import Memory
from mem0_falkordb import register
from gap_layer import MemoryGapLayer, GapConfig, FeatureFlags, SQLiteArchiveStore

# 1. 注册 FalkorDB 插件（必须在 Memory.from_config 之前）
register()

# 2. Mem0 配置
mem0_config = {
    "graph_store": {
        "provider": "falkordb",
        "config": {
            "host": "localhost",
            "port": 6379,
            "database": "mem0",
        }
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": "localhost",
            "port": 6333,
            "collection_name": "mem0",
        }
    },
    "llm": {
        "provider": "openai",
        "config": {"model": "gpt-4o-mini"}
    },
    "embedder": {
        "provider": "openai",
        "config": {"model": "text-embedding-3-small", "embedding_dims": 1536}
    },
    "custom_instructions": """
    提取事实时标注时间属性 (PAST/PRESENT/FUTURE/TIMELESS)。
    为每条记忆评估重要性 (1-5)，用于后续衰减和合并。
    """
}

# 3. 创建 Mem0 客户端
mem0_client = Memory.from_config(mem0_config)

# 4. 创建补齐层
archive_store = SQLiteArchiveStore("archive.db")
gap_config = GapConfig(
    decay_half_life_days=30,
    decay_whitelist=set(),  # 可添加不衰减的记忆 ID
    decay_buffer_multiplier=5,
    archive_store=archive_store,
    llm_client=mem0_client.llm,
)

gap = MemoryGapLayer(mem0_client, config=gap_config)

# 5. 配置功能开关
gap.feature_flags.enable("decay_filter", rollout_percentage=50)  # 50% 用户启用
gap.feature_flags.enable("contradiction_detection", rollout_percentage=10)  # 10% 用户启用

# 6. 使用补齐层（替代直接使用 mem0）
gap.add("用户喜欢咖啡", user_id="alice")
results = gap.search("用户喜欢什么", user_id="alice", top_k=10)

# 7. 每日清理（cron 调用）
gap.daily_cleanup()

# 8. 手动触发合并
result = gap.consolidate("alice", topic="宠物", dry_run=True)  # 先预览
print(f"将合并 {result.old_count} 条记忆为 {result.new_count} 条")
result = gap.consolidate("alice", topic="宠物", dry_run=False)  # 实际执行

# 9. 回滚（如需要）
gap.rollback_consolidation(result.archived_ids)

# 10. 全量回滚（紧急情况）
from gap_layer import RollbackManager
rollback = RollbackManager(gap)
rollback.full_rollback()
```

### 17.3 监控指标建议

| 指标 | 告警阈值 | 说明 |
|------|----------|------|
| 记忆总数/用户 | > 500 | 需要合并 |
| 搜索延迟 p95 | > 500ms | 需要优化 |
| 写入延迟 p95 | > 1000ms | 需要优化 |
| 矛盾记忆数 | > 0 | 需要审核 |
| 过期记忆占比 | > 30% | 需要清理 |
| FalkorDB 节点数 | > 10000 | 需要图清理 |
| FalkorDB 内存使用率 | > 80% | 需要扩容 |
| FalkorDB 查询延迟 p95 | > 200ms | 需要优化 |
| 合并服务错误率 | > 5% | 暂停合并 |
| LLM 调用成本/日 | > $10 | 检查异常 |

### 17.4 Docker Compose 完整示例

```yaml
# docker-compose.yml
version: "3.8"

services:
  # ─── 向量数据库 ───
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  # ─── 图数据库 ───
  falkordb:
    image: falkordb/falkordb:latest
    ports:
      - "6379:6379"
      - "3000:3000"  # Web UI
    volumes:
      - falkordb_data:/data
    command: ["redis-server", "--dir", "/data", "--save", "60", "1"]

  # ─── 归档数据库 ───
  postgres:
    image: pgvector/pgvector:pg17
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: mem0
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: mem0_archive
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # ─── 补齐层 Worker ───
  gap-worker:
    image: mem0-gap-layer:latest  # 需要自行构建镜像
    environment:
      MEM0_CONFIG: ${MEM0_CONFIG}
      DECAY_HALF_LIFE_DAYS: 30
      ARCHIVE_DB_URL: postgresql://mem0:${POSTGRES_PASSWORD}@postgres:5432/mem0_archive
      QDRANT_URL: http://qdrant:6333
      FALKORDB_URL: redis://falkordb:6379
    depends_on:
      - qdrant
      - falkordb
      - postgres
    restart: unless-stopped

volumes:
  qdrant_data:
  falkordb_data:
  postgres_data:
```

### 17.5 Dockerfile 示例

```dockerfile
# gap-layer/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY src/ ./src/

# 运行
CMD ["python", "-m", "src.gap_worker"]
```

---

> **文档结束**
>
> 如有疑问或需要进一步细化某个补齐方案的实施细节，请联系架构团队。
>
> **变更记录**：
> - v1.0.0 (2026-07-27)：初始版本
> - v2.0.0 (2026-07-27)：审计后修订，补齐接口完整性、运维考量、风险评估、回滚方案、成本估算
> - v3.0.0 (2026-07-27)：二次审计后修订，修复代码缺陷、新增决策树、替代方案对比、多模型成本对照
