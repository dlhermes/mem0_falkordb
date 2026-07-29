# mem0 Fork 短板补齐方案（v2 — 代码审计后修正版）

> 文档目标：供架构师审核的技术方案，不涉及具体代码实现
> 基准代码库：`dlhermes/mem0_falkordb` v2.0.14.post1，路径 `/tmp/mem0-push`
> 部署环境：内网自部署，server + pgvector + FalkorDB
> 审计日期：2026-07-28
> 最后更新：2026-07-29

---

## 进度状态

| 优先级 | # | 补齐项 | 状态 | 完成日期 |
|:-------|:-:|:-------|:----|:---------|
| **P0** | **1** | **图搜索集成：内建 FalkorDB provider** | **✅ 已完成** | **2026-07-29** |
| **P0** | **2** | **记忆衰减：搜索时按时间加权** | **✅ 已完成** | **2026-07-29** |
| **P0** | **3** | **cron 清理过期记忆和孤立节点** | **✅ 已完成** | **2026-07-29** |
| **P1** | **4** | **时间推理（轻量方案）** | **✅ 已完成** | **2026-07-29** |
| **P1** | **5** | **定期合并同主题记忆** | **✅ 已完成** | **2026-07-29** |
| P2 | 6 | 矛盾检测（写入时实时判定，带开关） | ⬜ 待开始 | — |

---

## 〇、审计摘要

对照项目实际代码（`/tmp/mem0-push`）逐项验证后，方案整体**可行**。以下 4 处修正：

| # | 修正项 | 原方案 | 修正后 |
|:--|:-------|:-------|:-------|
| 2 | 衰减 threshold 交互 | 未定案 | **方案 B**：原始分截断、衰减排位 |
| 3 | 用户列表来源 | 三选一待决策 | **方案 B**：history 表推导 |
| 5 | 合并后实体重建 | 未提及 | 依赖 `add()` 自动重建，但需 merge prompt 保留实体名 |
| 6 | 矛盾检测方案 | 异步批处理 O(n²) | **写入时实时（复用 add 调用），代码量从 ~500 行降至 ~80 行** |

工时修正：原估 28h → **18.5h ≈ 2.5 人天**（#6 方案变更后）。

---

## 一、现状

当前架构可正常工作：记忆存储 / 检索 / 图集成 / 重排序 / REST API 均通过审计。
以下 6 项能力缺失，随使用时间增长会逐步暴露问题。

### 已就绪（不需补充）

| 能力 | 依据 |
|:-----|:------|
| 复合过滤（Filters v2） | `mem0/memory/main.py` `_process_metadata_filters()` 实现 AND/OR/NOT + 比较运算符（eq/ne/gt/gte/lt/lte/in/nin/contains/icontains）；pgvector `_build_filter_conditions()`、Qdrant `_create_filter()` 均已实现对应转换。**可直接使用** |
| BM25 混合搜索 | vector store 层支持 keyword_search，含 CJK 适配 |
| 实体抽取 + 语义搜索 | spaCy + dense embedding 正常 |
| 基础图存储 | `mem0/graphs/falkordb/` 代码存在于仓库中（见下文补齐项 #1） |


## 二、补齐项

### P0 — 必须补齐，否则功能残缺

---

#### 1. 图搜索集成：内建 FalkorDB provider

**问题**

当前 `GraphStoreFactory.provider_to_class` 只注册了一个空实现（`factory.py:284-287`）：
```
"memory": "mem0.graphs.memory.MemoryGraph"  # 所有方法返回空，不做实际工作
```

FalkorDB 的图存储代码存在于 `mem0/graphs/falkordb/`，但需要通过 `register()` 调用 monkey-patch 才能激活。不调 `register()`，配置了 `graph_store.provider="memory"` 的用户得到的图搜索零结果。

**方案**

将 FalkorDB 直接编译进 factory，去掉 `register()` 依赖。需要修改两个位置：

- `mem0/utils/factory.py` `GraphStoreFactory.provider_to_class`：添加 `"falkordb"` 映射指向 `mem0.graphs.falkordb.graph_memory.MemoryGraph`
- `mem0/graphs/configs.py` `GraphStoreConfig.validate_config`：当前 Pydantic v2 field_validator（`configs.py:37-40`）硬编码只接受 `provider="memory"`，其他一律 raise ValueError。需要添加 `"falkordb"` 分支，返回 `FalkorDBConfig` 实例

**⚠️ 实现注意**：`patch.py:56-93` 的 monkey-patch 包含 3 步——改类型注解、wrap validator、`model_rebuild(force=True)`。内建化时需确保 `validate_config` 正确处理两种 config 类型：
- `MemoryGraphConfig` — 空类，无字段（`configs.py:8-9`）
- `FalkorDBConfig` — 5 个字段：host/port/database/username/password/base_label（`falkordb/config.py:6-29`）

用户传 dict 时需正确路由到对应 Config 类。

**注意**：`register()` 和 `patch.py` 在改造后不再必要，建议保留一段时间用于外部脚本兼容，后续移除。

**工作量**：6 人时（原估 4h 偏紧，Pydantic v2 validator 分支 + 回归测试需要更多时间）

**依赖**：无

---

#### 2. 记忆衰减：搜索时按时间加权

**问题**

所有记忆在检索时权重相同。一年前的偏好和今天刚说的偏好分数一样。导致：
- 临时偏好（"最近在减肥"）长期影响推荐
- 用户已放弃的计划仍排在前面
- Agent 看起来"记忆很好但判断力差"

**方案**

方向：在搜索 pipeline 中对旧记忆做指数衰减。

**衰减函数**：`decayed_score = original_score * 0.5 ^ (age_days / half_life)`

- half_life 默认 30 天（可配置）
- 30 天前的记忆分数减半，60 天前再减半
- 纯数学运算，不调用 LLM

**插入位置（代码审计后确认）**：

`_search_vector_store()` 的 pipeline（`main.py:1692-1751`）：
```
Step 1-2: embed + semantic search (over-fetch limit*4)
Step 3-6: keyword search + BM25 normalize + entity boost
Step 7: build candidates list from semantic_results
Step 8: score_and_rank(candidates, bm25_scores, entity_boosts, threshold, top_k)
```

`score_and_rank()` 内部（`scoring.py:105-139`）：
```
L110: semantic_score = result.get("score") or 0.0
L111: if semantic_score < threshold: continue     ← threshold 门
L118: raw_combined = semantic_score + bm25_score + entity_boost
L119: combined = min(raw_combined / max_possible, 1.0)
```

**⚠️ threshold 交互问题（代码审计后定案为方案 B）**：

L111 的 threshold 作用于**原始 semantic_score**。如果衰减乘在 L110 之前，老记忆可能直接跌破 threshold 被踢出——衰减形同虚设。

**定案方案 B**：threshold 比较用原始 semantic_score（保持入选资格），排序用衰减后分数：
```python
# 修改 score_and_rank:
# 1. 增加可选 decay_fn 参数
# 2. L111 threshold 比较用原始 semantic_score
# 3. L118 替换为: raw_combined = (semantic_score * decay_fn(age)) + bm25 + entity_boost
```

修改位置：`scoring.py` 的 `score_and_rank()` 函数签名 + L110/L118，以及 `main.py:1744` 的调用处传入 decay 参数。

**半衰期选择依据**：
- 30 天为经验值，对标 Platform 的衰减曲线
- 应做成环境变量 `MEM0_DECAY_HALF_LIFE_DAYS`，允许按业务场景调整
- 核心事实（如用户姓名/ID）应豁免衰减——通过 `metadata.importance=5` 标记，在 decay_fn 中检测后跳过乘法

**现有 notice 代码**：`notices.py:17-18` 已有 `DECAY_FEATURE_NOTICE_ID`，上游已预留入口框架。方案只需补齐 OSS 侧的实际衰减逻辑（`project.update(decay=True)` 目前 raise ValueError——`main.py:448-449`）。

**工作量**：3 人时（原估 2h，需改 scoring.py 函数签名 + threshold 分离逻辑）

**依赖**：无

---

#### 3. cron 清理过期记忆和孤立节点

**问题**

记忆只增不减，导致：
- 存储线性增长
- 过时记忆（如 "用户感冒了" 三个月前的记录）污染搜索结果
- FalkorDB 中孤立实体节点（无任何关联关系的节点）累积，拖慢查询

**方案**

三部分：

**3a. 清理过期记忆**
- mem0 已有 `expiration_date` 字段（`main.py:421-430` `_payload_is_expired()`）和 `show_expired` 控制
- 当前行为：过期记忆只在搜索/查询时通过 `_payload_is_expired()` 过滤，**并未物理删除**
- 清理动作：调用 `delete(memory_id)` 实际删除（`main.py` 已有 + `server/main.py:590-597` DELETE 端点）
- 需要维护活跃用户列表（`get_all()` 要求 filters 必含 user_id/agent_id/run_id 之一）

**3b. 清理 FalkorDB 孤立节点**
- Cypher：`MATCH (n:Entity) WHERE size((n)--()) = 0 DETACH DELETE n`
- 超过 90 天无更新的单次提及实体优先清理
- **依赖**：此项依赖补齐项 #1（图集成必须先完成，否则清理代码走到的是空实现）

**3c. 调度**
- 复用现有 `server/scripts/prune_request_logs.py` 的脚本模式
- 新增 `server/scripts/prune_expired_memories.py`
- 打包为 Hermes cronjob，每日凌晨执行
- 每次执行后记录：清理了 N 条过期记忆、M 个孤立节点

**用户列表来源方案（定案 B）**：

| 方案 | 优点 | 缺点 | 
|:-----|:-----|:-----|
| A. 业务系统提供 | 准确 | 需要跨系统对接 |
| **B. 从 mem0 history 表推导** ✅ | 零耦合，`SQLiteManager`（`storage.py`）已有 user_id 记录 | 仅覆盖有操作记录的用户 |
| C. 全量扫描 vector store 的 payload | 完整 | 依赖 vector store 的 list 能力 |

**定案 B**。当前用户量小，从 history 表取 distinct user_id 最简。未来用户增长后如需全量覆盖，可切方案 C。

**工作量**：2 人时

**依赖**：补齐项 #1（图集成）

---

### P1 — 搜索质量优化

---

#### 4. 时间推理（轻量方案）

**问题**

用户问"我现在应该做什么"，系统无法区分：
- "用户计划下周去东京"（FUTURE）
- "用户刚从东京回来"（PAST）
- "用户住在北京"（PRESENT）

Platform v3 有完整 temporal ranking 引擎（OSS 无）。本方案用 metadata 标记 + 过滤模拟，不实现 ranking 引擎。

**方案**

三层，逐层增强：

| 层 | 做法 | 覆盖场景 |
|:---|:-----|:---------|
| 1 | `custom_instructions` 要求 LLM 提取时标注 `temporal` 字段（PAST / PRESENT / FUTURE / TIMELESS），写入 `metadata.temporal` | 精确分类查询：`filters: {"metadata.temporal": "FUTURE"}` |
| 2 | 提取时同时写入 `metadata.temporal_date`（ISO 日期） | 按日期范围过滤：`filters: {"metadata.temporal_date": {"gte": "2026-07-01"}}` |
| 3 | （未来阶段）搜索时 NL → 时间表达式解析 | 自然语言查询："上周做了什么" → 自动翻译为时间范围过滤 |

当前仅实现第 1、2 层。第 3 层需要 NLP 时间解析器（如 duckling），暂不入范围。

**代码审计确认**：

`custom_instructions` 已直接拼接到 LLM prompt 的 `## Custom Instructions` 段（`prompts.py:628-629`）：
```python
if custom_instructions:
    sections.append(f"## Custom Instructions\n{custom_instructions}")
```

只需在 `config.json` 的 `custom_instructions` 字段追加 temporal 标注规则即可，**零代码改动**。metadata 字段已被 server 和 SDK 透传（`main.py:1785-1789` additional_metadata 自动带入 payload）。

**server API**：当前 server 的 `search()` 已透传 `filters` 参数（`server/main.py:519-551`），metadata 过滤直接可用。

**与已有记忆的兼容性**：旧记忆 metadata 中无 temporal 字段，搜索时不参与 temporal 过滤。这是期望行为——未标记的记忆被视为 TIMELESS。

**工作量**：0.5 人时（原估 1h 偏多，纯 config 改动）

**依赖**：无

---

#### 5. 定期合并同主题记忆

**问题**

当前 ADD-only 策略下，每次对话产生独立记忆：
```
记忆 #1: "用户养了一只狗叫 Max"       (2026-01-15)
记忆 #2: "Max 是金毛"                (2026-02-20)
记忆 #3: "带 Max 去露营"             (2026-03-10)
记忆 #4: "Max 在露营时游泳和爬山"     (2026-03-10)
```
搜索"用户有什么宠物"返回 4 条碎片，Agent 需自行拼凑，token 浪费。

**方案**

cron worker，每日或超过阈值触发：

1. **分组**：从 FalkorDB 读取实体节点（需补齐项 #1），按实体名分组合并候选记忆。FalkorDB 未就绪时降级为关键词搜索分组。
2. **合并**：调用 LLM 将同一组内 3+ 条记忆合并为 1-3 条精炼事实。少于 3 条不合并。
3. **写入**：先 `add()` 新合并记忆，记录新 ID。再 `delete()` 旧记忆。
   - **反序原因**：worker crash 在 delete 之后 add 之前会导致数据丢失。先 add 后 delete，即使中间 crash，下次运行会看到新旧共存，不会丢信息。
4. **失败处理**：LLM 解析失败 / 超时 → 跳过该组，记录日志，不影响其他组。

**⚠️ 实体关系重建（代码审计补充）**：

合并后的新记忆调用 `add()` 时，`MemoryGraph.add()`（`graph_memory.py:237-254`）会**自动触发实体抽取 + 关系建立**——LLM 重新走 `_retrieve_nodes_from_data` → `_establish_nodes_relations_from_data`。只要合并 prompt **明确要求保留所有实体名称**（如"Max"不能简化为"宠物"），实体关系会自然重建。

**时序说明**：合并后 delete 旧记忆 → 旧 graph 关系残留为孤立节点 → 等下次 #3b cron 清理。这是预期行为，无数据丢失风险。

**不做**：
- 不做回滚机制（SQLite history 表已有变更记录可追溯）
- 不做分布式锁（单机 cron 无竞争）
- 不合并少于 3 条的分组（避免无意义消耗）

**工作量**：3 人时

**依赖**：补齐项 #1（图集成用于实体分组）。图集成未完成时可用关键词搜索降级。

---

### P2 — 运维完善

---

#### 6. 矛盾检测（写入时实时判定）

**调研结论**

mem0 官方没有独立的"矛盾检测"模块。它通过 `add()` 流程中的 `DEFAULT_UPDATE_MEMORY_PROMPT`（`prompts.py:179`）内置实现：

```
新消息 → LLM 提取 facts
       → 向量搜索拉回 top-10 existing_memories
       → LLM 拿到 {新facts + 已有memories} → 逐条判定：

  ADD    → 新信息
  UPDATE → 信息更新（"喜欢奶酪披萨"→"喜欢鸡肉披萨"）
  DELETE → 矛盾（"喜欢奶酪披萨"→"不喜欢奶酪披萨"）★
  NONE   → 无变化
```

矛盾在写入那一刻就被 DELETE 解决。不额外调用 LLM——判定逻辑复用 `add()` 流程的已有调用。

**当前状态**

我们的 Fork 使用 `ADDITIVE_EXTRACTION_PROMPT`（仅 ADD 模式），但**基础设施已就绪**：

- `main.py:915-920` — 已有 `vector_store.search()` 拉取 `existing_results`
- `main.py:923-927` — 已构造 `existing_memories` 列表（含 id + text）
- `main.py:962-963,992-993` — 已传入 `generate_additive_extraction_prompt()` 的 `existing_memories` 参数
- `prompts.py:484-486` — `## Existing Memories` 段已格式化在 prompt 中

**缺失**：system prompt 用的是 `ADDITIVE_EXTRACTION_PROMPT`（line 931），而非 `DEFAULT_UPDATE_MEMORY_PROMPT`。前者要求 LLM 只输出 ADD，后者要求判 ADD/UPDATE/DELETE/NONE。

**方案：切回 UPDATE 模式（带开关）**

核心改动三处：

| # | 文件 | 改动 | 说明 |
|:--|:-----|:-----|:-----|
| 1 | `mem0/memory/main.py:931` | `system_prompt = ADDITIVE_EXTRACTION_PROMPT` → 按开关选择 `UPDATE_MEMORY_PROMPT` | 读 `MEM0_ENABLE_CONTRADICTION` 环境变量，为 true 时切到 UPDATE prompt |
| 2 | `mem0/memory/main.py:1054-1084` | Phase 4 处理逻辑需区分 event 类型 | 当前只处理 ADD（写向量、写 history）。需新增：event=UPDATE → 调 `_update_memory()`；event=DELETE → 调 `_delete_memory()`；event=NONE → 跳过 |
| 3 | `prompts.py` | 新建中文版 `UPDATE_MEMORY_PROMPT` | 复制 `DEFAULT_UPDATE_MEMORY_PROMPT`（`prompts.py:179-327`），将示例和指令翻译为中文，保持与 Fork 全链路中文一致 |

**UPDATE prompt 响应格式**：

```json
{
  "memory": [
    {"id": "0", "text": "名字是张三", "event": "NONE"},
    {"id": "1", "text": "不喜欢奶酪披萨", "event": "DELETE"},
    {"id": "2", "text": "喜欢鸡肉披萨", "event": "ADD"}
  ]
}
```

ID 语义：
- `event=ADD` → 新 ID（字符串数字，后续会被替换为 UUID）
- `event=UPDATE/DELETE/NONE` → 必须保留输入的 ID（对应 `existing_memories` 中的 id）
- `uuid_mapping`（`main.py:926`）将整数 ID 映射回真实 UUID

**处理逻辑伪代码**：

```python
for mem in extracted_memories:
    event = mem.get("event", "ADD")
    if event == "NONE":
        continue
    elif event == "DELETE":
        real_id = uuid_mapping.get(mem["id"])
        if real_id:
            _delete_memory(real_id)
    elif event == "UPDATE":
        real_id = uuid_mapping.get(mem["id"])
        if real_id:
            _update_memory(real_id, mem["text"], ...)
    elif event == "ADD":
        # 现有逻辑：embed + insert
        ...
```

**开关与环境变量**：

```bash
MEM0_ENABLE_CONTRADICTION=false  # 默认关闭。置 true 启用 UPDATE 模式
```

- 默认 false → 行为不变，零风险
- 置 true → 切到 UPDATE prompt，LLM 开始判断 ADD/UPDATE/DELETE
- 运行时切换：下次 `add()` 调用时生效（每次 `add()` 读 `os.environ.get`）

**风险与缓解**：

| 风险 | 概率 | 缓解 |
|:-----|:-----|:-----|
| LLM 误判 DELETE（删了不该删的记忆） | 低 | `DEFAULT_UPDATE_MEMORY_PROMPT` 第 267 行有明确规则：仅当「包含与记忆中现有信息相矛盾的信息」才 DELETE。先灰度 10% 用户验证 1 周 |
| LLM 漏判（矛盾未被发现） | 中 | `existing_memories` 仅取 top-10，不相关的记忆不在上下文中。可通过增大 `top_k` 缓解 |
| UPDATE/DELETE 对应的 ID 在 uuid_mapping 中不存在 | 低 | LLM 可能编造 ID。处理时检查 `uuid_mapping.get(id)`，不存在则降级为 ADD |
| 中文 prompt 与英文示例不一致导致 LLM 困惑 | 低 | 翻译时保留 JSON 输出格式不变，仅翻译中文指令和示例文本 |

**为什么不用 gap-plan 原方案**：

| 维度 | 原方案（异步批处理） | 新方案（写入时实时） |
|------|---------------------|---------------------|
| LLM 调用 | 额外 ~5000 对/天（pairwise） | **0**（复用 add 调用） |
| 代码量 | ~500 行（embedding 聚类 + pairwise + 标记 + 过滤） | **~80 行**（prompt 切换 + event 分发） |
| 检测时机 | 延迟（cron 一天一次） | **实时**（写入即检测） |
| 粗筛依赖 | FalkorDB 实体聚类 + embedding 相似度 | 无（向量搜索 top-K 即粗筛） |
| 误报处理 | 标记不删除 | **直接 DELETE**（history 表可追溯恢复） |

**工作量**：4 人时（prompt 中文化 1h + switch 逻辑 1h + event 分发 1h + 测试 1h）

**依赖**：无。temporal 字段已在 `ADDITIVE_EXTRACTION_PROMPT` 中实现（prompts.py:526-527），UPDATE prompt 复用同一 LLM 调用，不受影响。


## 三、架构决策

### 补齐层位置

| 方案 | 做法 | 优点 | 缺点 |
|:-----|:-----|:-----|:-----|
| **A. 嵌入 server**（推荐） | 在 server search/add 流程中插入 hook；cron 作为 Hermes cronjob | 零额外基础设施，原有 Docker Compose 不动 | 与 server 进程耦合 |
| B. 独立补齐服务 | 另起 gap-worker 进程 | 解耦，可独立扩缩 | 多一层网络开销，部署复杂度增加 |

建议先走 A，6 项补齐完成后评估搜索延迟，如 p95 > 500ms 再考虑 B。

**附加建议**：补齐完成后增加 `/health/readiness` 端点，聚合各 feature flag 状态 + cron 最近执行时间。

### 功能开关

每个补齐能力应支持独立开关：

```
MEM0_ENABLE_DECAY=true
MEM0_ENABLE_CONSOLIDATION=false     # 先关闭，灰度后开启
MEM0_ENABLE_CONTRADICTION=false     # 先关闭，灰度后开启
MEM0_DECAY_HALF_LIFE_DAYS=30
```

### 现有限制（不在此方案范围内）

- `get_all()` 要求 filters 含实体 ID——无法一次性扫全量用户，需要外部用户列表
- `score_and_rank()` 内部完成了 threshold 过滤 + top_k 截断——衰减需改内部 pipeline


## 四、依赖与执行顺序

```
P0 #1 图集成 ─────── 起点，无外部依赖
    │
    ├── P0 #2 记忆衰减 ─── 无依赖
    │
    └── P0 #3 cron 清理 ─── 依赖 #1
            │
            ├── P1 #4 时间推理 ─── 无依赖，可随时开始
            │
            ├── P1 #5 定期合并 ─── 依赖 #1（可降级）
            │
            └── P2 #6 矛盾检测 ─── 无依赖（复用已有 add 基础设施）

```

建议执行顺序：`#1 → #2 → #4（可并行） → #3 → #5 → #6`

#4 与 #1/#2 无依赖，可并行开工。总工期可从串行 5 天压缩至 **4 天**（#1+#4 并行启动）。


## 五、风险

| 风险 | 概率 | 影响 | 缓解 |
|:-----|:-----|:-----|:-----|
| **图集成 config 校验不兼容** | 中 | server 启动失败 | `validate_config` 加 falkordb 分支 + 单元测试覆盖两种 config 类型 |
| **衰减半衰期不当** | 中 | 过短遗忘核心事实；过长衰减无效 | 做成环境变量，默认 30 天；importance=5 豁免 |
| **衰减后 score 低于 threshold 导致老记忆消失** | **高** | 衰减形同虚设 | 已定案方案 B：原始分截断 + 衰减排位 |
| **合并 LLM 丢失实体名称** | 中 | graph 关系断裂 | merge prompt 明确要求保留所有实体名称 |
| **合并后孤立节点短期累积** | 低 | FalkorDB 查询轻微变慢 | 下次 #3b cron 自动清理 |
| **矛盾检测 LLM 误判 DELETE** | 低 | 有效记忆被误删 | `DEFAULT_UPDATE_MEMORY_PROMPT` 有明确 DELETE 规则约束；默认关闭开关，灰度 10% 验证；history 表可追溯恢复 |
| **矛盾检测 LLM 漏判** | 中 | 矛盾未发现 | `existing_memories` 取 top-10，可通过增大 `top_k` 提升召回；不影响现有 ADD 行为 |
| **FalkorDB 清理误删有效节点** | 低 | 实体丢失 | 只清理 `size(--)=0` 的孤立节点 |
| **合并时 LLM 限流 / 超时** | 低 | 跳过该组 | 不做重试，跳过该组保整体进度 |


## 六、验证方法

| 补齐项 | 验证方法 |
|:-------|:---------|
| #1 图集成 | 配置 `graph_store.provider="falkordb"`，调 `m.add()`，确认 FalkorDB 中出现实体节点和关系 |
| #2 衰减 | 搜索一条 60 天前的记忆，确认分数低于相同语义相关度的新记忆；确认 importance=5 的记忆不受影响 |
| #3 cron 清理 | 手动触发清理，确认过期记忆被 delete、孤立节点被 DETACH DELETE |
| #4 时间推理 | 写入含 `metadata.temporal="FUTURE"` 的记忆，搜索时用 `filters: {metadata.temporal: "PAST"}` 确认不返回 |
| #5 定期合并 | 写入 5 条同主题记忆（含实体名），触发合并，确认合并后记忆保留实体名且 FalkorDB 关系重建 |
| #6 矛盾检测 | 设置 `MEM0_ENABLE_CONTRADICTION=true`，写入两条矛盾记忆（如先 add "喜欢咖啡"再 add "讨厌咖啡"），确认旧记忆被 DELETE；检查 history 表有 DELETE 记录可追溯 |


## 七、未纳入范围

- 实时 temporal ranking 引擎（Platform v3 算法级能力）—— metadata 分类过滤方案已覆盖
- Dream Consolidation（跨 session 智能整合）—— 超出 OSS 定位
- Webhooks / Memory Export —— 上游代码中已有的平台客户端存根，内网不需要
- 多模态输入 —— 内网 Python SDK 场景有限
- Dashboard 分析面板 —— 已有请求日志满足运维需求


## 八、工作量汇总（v2 修正）

| 优先级 | 补齐项 | 原估 | 修正 | 理由 |
|:-------|:-------|:-----|:-----|:-----|
| P0 | #1 图集成 | 4h | **6h** | Pydantic v2 validator 双 config 分支 + 回归 |
| P0 | #2 衰减 | 2h | **3h** | 改 scoring.py 函数签名 + threshold 分离 |
| P0 | #3 cron 清理 | 2h | **2h** | 不变 |
| P1 | #4 时间推理 | 1h | **0.5h** | 纯 config 改动 |
| P1 | #5 合并 | 3h | **3h** | 不变 |
| P2 | #6 矛盾检测 | 24h | **4h** | 方案从异步批处理改为写入时实时（复用 add 调用，代码量从 ~500 行降至 ~80 行） |
| **总计** | | **28h** | **18.5h ≈ 2.5 人天** | |

> 注：以上为纯开发工时。代码审查、部署、回归测试另计。若 #4 与 #1 并行开工可压缩总工期至约 4 天。
