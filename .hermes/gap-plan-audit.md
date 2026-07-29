# gap-plan.md 自审计 — 架构师可能抓的痛脚

---

## 1. 🔴 图集成的工作量低估了

**原方案**：「factory.py 加一行注册即可，2 人时」

**问题**：`GraphStoreConfig.validate_config()`（`graphs/configs.py:34-40`）有个 Pydantic v2 field_validator，**只接受 `provider="memory"`**，其他一律 `raise ValueError`。这是硬编码的校验逻辑。

要内建 falkordb 需要改**两个地方**：
- `GraphStoreFactory.provider_to_class` — 加 falkordb 映射
- `GraphStoreConfig.validate_config` — 加 `falkordb` 分支，返回 `FalkorDBConfig`

前者一行，后者涉及 Pydantic v2 校验器 + 类型标注（参考 `patch.py:52-80` 的 monkey-patch 写法）。**工作量 2h 改为 4h**。

> 架构师必问：「那现有的 `register()` 和 `patch.py` 还保留吗？升级 mem0 后冲突怎么办？」

---

## 2. 🔴 衰减的 threshold 交互没说

**原方案**：「取 top_k * 5 候选 → 衰减 → 重排 → 截 top_k」

**问题**：`_search_vector_store()` 内部的 `score_and_rank()` 在返回前已经做了**threshold 过滤 + top_k 截断**。到衰减 hook 时，手头只有 top_k 条结果，没有多余的候选可以重排。

真实的调用链：
```
_search_vector_store(query, limit=20)
  → over-fetch: internal_limit = 80
  → score_and_rank(threshold=0.1, top_k=20)  ← 这里就截断了
  → 返回 20 条结果 ← 衰减插不进去
```

**修正**：衰减 hook 必须插入 `score_and_rank()` **之前**，在 full candidate pool 上计算衰减分数，再送 `score_and_rank()`。或者换思路——不改核心代码，在 server 层 `search_memories()` 返回值上做后处理衰减（代价：无法利用未过 threshold 的老记忆）。

> 架构师必问：「衰减后的 score 还保持在 [0,1] 吗？threshold=0.1 还能用吗？」

---

## 3. 🟡 清理依赖图集成，形成环

**原方案**：「cron 清理孤立节点」

**问题**：清理 FalkorDB 孤立节点需要调用 `self.graph.query(cypher)`。但如果图集成还没完成（`GraphStoreFactory` 注册的是 `memory` 空实现），`self.graph` 的 `delete_all()` 是个空方法——**什么都不会做**。

依赖链：`P0 #1(图集成) → P0 #3(清理)`

不是互斥问题，但在执行计划中必须串行。

---

## 4. 🟡 get_all() 不能扫全量用户

**原方案**：「get_all() 找出过期记忆」

**问题**：`get_all()` 要求 `filters` 必须含 `user_id`/`agent_id`/`run_id` 之一，否则 raise ValueError。没法一次性扫所有用户的过期记忆。

必须提前维护一份活跃用户/agent 列表，逐个遍历。要么从业务系统拿，要么在 mem0 history 表中查出现过哪些 user_id。

> 架构师必问：「用户列表从哪里来？首次运行时要扫全部历史吗？」

---

## 5. 🟡 合并不是原子操作

**原方案**：「delete 旧 + add 新」

**问题**：worker 在执行 `delete()` 之后、`add()` 之前 crash 了，旧记忆已删除、新记忆未写入——**数据丢失**。

不做完整回滚机制可以（SQLite 可追溯），但至少要：
- 先 add 新记忆，记下新 ID
- 再 delete 旧记忆
- 中间 crash → 下次合并会看到新旧共存，走正常覆盖流程

> 架构师必问：「worker crash 后怎么恢复？」

---

## 6. 🟡 矛盾检测工作量严重低估

**原方案**：「1 人天」

**问题**：全量扫所有用户的记忆 + 分批次 LLM 检测矛盾 + 标记持久化 + 搜索时过滤。生产级实现至少需要：

| 子任务 | 工作量 |
|:-------|:-------|
| 全量扫描 + 分页遍历所有 user | 4h |
| LLM 批处理调度（并发/限速/重试/超时） | 4h |
| 矛盾标记写入 metadata | 2h |
| 搜索时过滤逻辑 | 2h |
| 测试 + 验证 | 4h |
| **总计** | **~16h（2 人天）** |

**另外**：用户说"用户搬家后新旧地址同时存在"——这个场景里"旧地址"和"新地址"都是有效记忆，只是时间维度不同。真正的矛盾是逻辑矛盾（"用户用 Windows" vs "用户用 Mac"），但时间序列上可能都是真的。**LLM 检测需要理解时间上下文**，这又绕回到时间推理能力。

> 架构师必问：「批量 LLM 检测的准确率怎么保证？误报怎么处理？」

---

## 7. 🟡 时间推理的「80%」无依据

**原方案**：「metadata 过滤覆盖 80% 场景」

经不起推敲。metadata 精确匹配只能覆盖"我只要未来的记忆"这种场景，但覆盖不了"上周做了什么"（需要自然语言→时间范围解析）和"我现在应该做什么"（需要区分当前状态 vs 已过期状态）。80% 是随口说的。

应当改口为：「精确过滤可覆盖类别查询（PAST/PRESENT/FUTURE/TIMELESS），相对时间查询需额外 NLP 解析层，暂不纳入。」

---

## 8. 🟢 缺少验证与可观测性

6 项补齐上线后，怎么知道它们在 work？缺少：

| 缺失 | 建议 |
|:-----|:------|
| 衰减生效的自检 | 搜索老记忆，确认分数比新记忆低 |
| 合并触发的记录 | 每次合并记一条 log |
| 过期清理的成功率 | 每天 report 清理了多少条 |
| 矛盾检测的准确率 | 定期抽样确认 |

---

## 修正后计划（更新版）

| 优先级 | 能力 | 修正后工作量 | 关键风险 |
|:-------|:-----|:-------------|:---------|
| **P0** | 图集成 | 2h→**4h** | 需同时改 factory + config validator |
| **P0** | 衰减 | 1h→**2h** | threshold 交互需在 pipeline 正确位置插入 |
| **P0** | 清理 | 1h→**2h** | 依赖图集成先完成；需要用户列表 |
| **P1** | 时间推理 | 1h→**1h** | 不变，但去掉 80% 说法 |
| **P1** | 合并 | 2h→**3h** | 需先加后删保证 crash 安全 |
| **P2** | 矛盾检测 | 1d→**2d** | 需 LLM 批处理调度 |

> 注：上述均为纯开发工时，不含代码审查 + 部署 + 回归测试
