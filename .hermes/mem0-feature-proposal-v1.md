# mem0_falkordb 功能增补方案 v1.2

> 架构师审核反馈整合版。v1.2 更新：§1 Lane 分轨重写（LLM + importance 联动），新增完成状态表。

---

## 实现状态

| Phase | 功能 | 状态 | 说明 |
|-------|------|------|------|
| **Phase 1** | 相关性自适应检索深度 | ✅ **已完成** | 三级深度路由 + resolve_search_depth 关键词 DB 匹配 + LRU 缓存。已部署 10.200.1.163 |
| **Phase 2** | Lane 分轨衰减 | 🔄 待实施 | 见 §1 |
| **Phase 3** | 用户纠正感知 | ⏳ 待排期 | 见 §3 |

---

## 目录

1. [Lane 分轨衰减](#1-lane-分轨衰减)
2. [相关性自适应检索深度](#2-相关性自适应检索深度)
3. [用户纠正感知](#3-用户纠正感知)
4. [三功能交互矩阵](#4-三功能交互矩阵)
5. [v1.2 变更记录](#5-v12-变更记录)
6. [向后兼容总表](#6-向后兼容总表)
7. [附录：aiduMEM 参考代码状态](#7-附录aidumem-参考代码状态)

---

## 1. Lane 分轨衰减

### 1.1 现状

当前已经实现了记忆衰减（`MEM0_ENABLE_DECAY=true`），但有两个问题：

**问题一：全部记忆共享同一半衰期。**
身份类（"发哥用中文"）和情绪类（"今天心情好"）不该用同一衰减速度。

**问题二：`importance` 字段只读不写。**
`_decay_fn` 检查 `payload.get("importance") == 5` 来豁免衰减，但没有任何代码往 payload 写入过 `importance`。该项是死代码，豁免永不触发。

### 1.2 设计

#### 双字段：LLM 同时判 importance 和 lane

LLM extraction prompt 追加两个输出字段，不增加额外 LLM 调用（扩已有 prompt）：

```
在现有 entity extraction prompt 末尾追加：

"判断以下两项：
 1. importance（1-5整数）
    5 = 必须永远记住的身份/偏好/关键决策，永不衰减
    1-4 = 正常记忆，不重要也会自然腐化

 2. lane（轨道）
    slow  = 经验、流程、规则——需要慢速衰减
    normal = 一般知识——正常衰减
    fast  = 情绪、会话、临时内容——快速腐化

输出格式: importance: <值>
         lane: <值>"
```

#### 两条路径的关系

```
检索时 _decay_fn(payload):

    # 第 1 道：importance=5 硬豁免
    if payload.get("importance") == 5:
        return 1.0                      ← 永不衰减，无视 lane

    # 第 2 道：按 lane 轨道衰减
    lane = payload.get("lane", "normal")
    multiplier = lane_multipliers.get(lane, 1.0)
    return 0.5 ** (age_days / (30 * multiplier))
```

**不存在 priority 矛盾**——`importance=5` 是"这条特别重要"的硬豁免，过了才轮到 lane。

#### Lane 枚举（3 档）

| Lane | multiplier | 半衰期(基准30天) | 语义 |
|------|-----------|-----------------|------|
| slow | 0.3 | ~100 天 | 经验、流程、规则 |
| normal | 1.0 | ~30 天 | 一般知识事实 |
| fast | 1.5 | ~20 天 | 情绪、临时性内容 |

#### 写入分轨策略

```
写入文本进入 add()

  ├─ LLM 提取（扩 prompt）
  │   同时输出: importance=1-5, lane=slow/normal/fast
  │
  └─ LLM 未输出 lane →
       │
       ├─ 关键词兜底（只填 lane，importance 留给 LLM）
       │    踩坑/报错/修复/教训/必须/步骤/流程  → lane=slow
       │    开心/难过/心情/感觉/今天/刚才        → lane=fast
       │    未命中 → lane=normal
       │
       └─ importance 无兜底 → 不设值（_decay_fn 中 get 不到 = 不走豁免）
```

关键词只兜底 lane，不兜底 importance。`importance` 太难用关键词判断，留给 LLM。

#### 持久化

`lane` 和 `importance` 存入 memory payload（metadata dict），不加数据库列。

- 写入时：`payload.lane = "slow"`，`payload.importance = 5`
- 检索时：`_decay_fn` 从 payload 读取
- 存量记忆：`payload.get("lane")` → `None` → `lane_multipliers.get(None, 1.0)` → normal，行为不变
- migration：无

### 1.3 改动文件清单

| 文件 | 改动 | 内容 |
|------|------|------|
| `mem0/configs/base.py` | 新增 | `Lane` 枚举 + `LANE_MULTIPLIERS` + `MEM0_LANE_ENABLED` |
| `mem0/configs/prompts.py` | 修改 | entity extraction prompt 追加 importance + lane 输出指令 |
| `mem0/memory/main.py` | 修改 | `add()` 写入时 lane 检测（LLM→关键词→normal）；`_decay_fn` 读 lane multiplier |
| `mem0/memory/main.py` | 修改 | `_decay_fn` 补全 `importance` 写入路径（当前只读不写，修复） |

### 1.4 新增配置项

```
MEM0_LANE_ENABLED=false     # 总开关，默认关。开启后 LLM 分轨 + 关键词兜底生效
MEM0_DECAY_HALF_LIFE_DAYS=30  # 基准半衰期（已有，lane multiplier 在此基础上缩放）
```

### 1.5 效果验证

```
# 写入重要身份记忆
POST /add {"content": "发哥用中文沟通"}
→ LLM 提取 → importance=5, lane=normal
→ 一年后 search：importance=5 → 永不衰减 → 稳定排在前列

# 写入经验教训
POST /add {"content": "部署要点：先装 libpq5 再跑 pip install"}
→ LLM 提取 → importance=3, lane=slow
→ 90 天后 search：slow multiplier=0.3 → 保留程度高

# 写入情绪废话
POST /add {"content": "今天心情不错"}
→ LLM 提取或关键词兜底 → lane=fast
→ 30 天后 search：fast multiplier=1.5 → 快速腐化，排在后
```

---

## 2. 相关性自适应检索深度

### 2.1 现状

每次 `search()` 固定走完整链路：embedding 生成 → 向量检索 → BM25 全文搜 → FalkorDB 图查询 → 合并排序 → (可选 rerank)。

成本：
- embedding：API 调用（约 0.02 元/次 或 自建 GPU 推理）
- 向量检索：Qdrant 查询（约 10-50ms）
- 图查询：FalkorDB Cypher + 实体提取（约 20-100ms）
- Rerank：API 调用（约 0.01 元/次）

大量查询不需要完整链路。

### 2.2 设计

#### 三级深度

| 级别 | 执行链路 | 场景 | 节省 |
|------|---------|------|------|
| `minimal` | 跳过全部检索 | "你好""继续""谢谢"等废话 | 100% |
| `standard` | embedding + BM25 | 日常对话、例行 recall | 约 70%（跳过图 + rerank） |
| `full` | embedding + BM25 + 图 + rerank | 精确事实、含实体、纠正信号 | 0%（不变） |

#### 默认值决策

**v1 版本默认 `full`**，零行为变化。上线后通过指标确认 minimal/standard 触发率可接受后，再切默认 `standard`。

#### 自动判定规则

判定在 `search()` 入口执行，约 40 行字符串匹配，**不调 LLM**。

判定关键词从 `facts.db` 的 `search_keywords` 表读取，不硬编码：

```sql
CREATE TABLE IF NOT EXISTS search_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK(category IN ('minimal', 'full', 'correction')),
    keyword TEXT NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'exact' CHECK(match_type IN ('exact', 'contains')),
    lang TEXT NOT NULL DEFAULT 'zh' CHECK(lang IN ('zh', 'en')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sk_category ON search_keywords(category);
```

| 列 | 说明 |
|----|------|
| `category` | `minimal`(跳过全部检索)、`full`(触发全套)、`correction`(用户纠正感知) |
| `keyword` | 匹配的关键词文本 |
| `match_type` | `exact`=精准匹配(query==keyword)、`contains`=包含匹配(query 含 keyword) |
| `lang` | 语言标记，仅为可读性，匹配时不区分 |

**判定逻辑：**

```python
def resolve_depth(query: str) -> str:
    # 1. 显式指定 depth 参数 → 直接使用
    # 2. 查 DB 匹配
    q = query.strip()
    if not q or len(q) < 2:
        return "minimal"

    keywords = load_keywords_from_db()  # 按 category 分组缓存

    # minimal: exact 匹配（精准拦截废话）
    for kw in keywords["minimal"]["exact"]:
        if q.lower() == kw.lower():
            return "minimal"

    # full: contains 匹配（纠正/复杂查询信号）
    for kw in keywords["full"]["contains"]:
        if kw.lower() in q.lower():
            return "full"

    # full: 长查询
    if len(q) > 50:
        return "full"

    # 3. 兜底
    return "standard"
```

**关键词管理**：增删改直接操作 `search_keywords` 表，立刻生效，无需重启服务：

```sql
-- 加词
INSERT INTO search_keywords (category, keyword, match_type, lang)
VALUES ('minimal', '明白了', 'exact', 'zh');

-- 删词
DELETE FROM search_keywords WHERE category='minimal' AND keyword='好';

-- 查当前词表
SELECT * FROM search_keywords ORDER BY category, keyword;
```

#### 种子数据

首次启动时自动 INSERT 以下默认词表（`INSERT OR IGNORE` 防止重复）：

**minimal 类（exact 匹配——query 必须完全等于关键词才拦截，宁缺毋滥）：**

```sql
-- 中文问候/确认/回应
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '好', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '嗯', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '哦', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '嗨', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '好的', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '是的', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '好吧', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '好的吧', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '嗯嗯', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '知道', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '知道了', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '明白', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '明白了', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '收到', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '谢谢', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '谢了', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '多谢', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '继续', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '来吧', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '没事', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '算了', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '没关系', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '好的谢谢', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '行', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '对', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '可以', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '成', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '行吧', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '懂了', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '了解了', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '没问题', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '好嘞', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'okok', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '👌', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '👍', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', '了解', 'exact', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'okk', 'exact', 'zh');

-- 英文
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'hi', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'hello', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'hey', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'ok', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'okay', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'thanks', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'thankyou', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'yes', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'yeah', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'sure', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'great', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'gotit', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'anyway', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'alright', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'cool', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'np', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'nvm', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'fine', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'gotcha', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'yep', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'nope', 'exact', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('minimal', 'idk', 'exact', 'en');
```

**full 类（contains 匹配——query 含关键词就走全套检索）：**

```sql
-- 纠正信号（中）
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '不对', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '错了', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '不是这样', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '你记错', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '记错了', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '纠正', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '应该是', 'contains', 'zh');

-- 复杂查询信号（中）
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '为什么', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '怎么回事', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '什么原因', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '具体', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '详细', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '查一下', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '搜一下', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '怎么', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '如何', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '区别', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '对比', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '步骤', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '流程', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '原理', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '报错', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '排查', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '配置', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', '解决方案', 'contains', 'zh');

-- 纠正信号（英）
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'wrong', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'incorrect', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'actually', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'wait', 'contains', 'en');

-- 复杂查询（英）
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'why', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'how', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'explain', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'specifically', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'difference', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'compare', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'error', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'issue', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'debug', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'configure', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'setup', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('full', 'tutorial', 'contains', 'en');
```

**correction 类（contains 匹配——触发用户纠正感知）：**

```sql
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '不对', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '不是这样', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '你记错', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '记错了', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '说错了', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '应该是', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '纠正', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '我说的是', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'no', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'wrong', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'incorrect', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'actually', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'not really', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'mistake', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '不是', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '错了', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '搞错了', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '弄错了', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '记混了', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '上次说的是', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '之前说过', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '你说错了', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', '不是吧', 'contains', 'zh');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'i thought', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'i meant', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'you said', 'contains', 'en');
INSERT OR IGNORE INTO search_keywords (category, keyword, match_type, lang) VALUES ('correction', 'correction', 'contains', 'en');
```

> 全网搜索确认：没有公开的标准关键词路由表可以照搬。此领域主流做法是全量检索或用 LLM 分类，关键词路由是小众方案。种子数据基于语言直觉 + 实际对话场景整理，后期通过 INSERT 补充，无需改代码。

#### 链路分发逻辑

```python
def search(query, depth=None):
    depth = resolve_depth(query, depth)  # 显式 or 自动

    if depth == "minimal":
        return MemorySearchResult(results=[], ...)

    # 公共：embedding + 向量检索 + BM25
    results = vector_search(query)
    results = bm25_search(query, results)

    if depth == "standard":
        return score_and_sort(results)  # 不跑图

    if depth == "full":
        graph_results = graph_search(query)
        results = merge_graph(results, graph_results)
        if reranker_available:
            results = reranker.rerank(query, results)
        return score_and_sort(results)
```

#### LRU 缓存

- 缓存键：`query + depth + top_k`
- minimal 路径 TTL：`MEM0_SEARCH_CACHE_TTL=15` 秒（100% 节省）
- standard 路径 TTL：`MEM0_SEARCH_STD_CACHE_TTL=5` 秒（短 TTL 防止短时间重复检索——同 Agent 轮次内反复 search 常见）
- 淘汰策略：TTL 到期自动过期，LRU 淘汰最久未访问；standard 和 minimal 共享 LRU 池

### 2.3 改动文件清单

| 文件 | 改动 | 内容 |
|------|------|------|
| migration | **新增** | `CREATE TABLE search_keywords (id, category, keyword, match_type, lang)` + 种子 INSERT |
| `mem0/configs/base.py` | 新增 | `SearchDepth` 枚举 + `MEM0_SEARCH_DEPTH_DEFAULT` + `MEM0_SEARCH_DEPTH_CACHE_SECS` |
| `mem0/memory/main.py` | 修改 | `search()` 入口加载 `search_keywords` 表（含缓存）+ 深度路由 + LRU 缓存 |
| `mem0/configs/base.py` | 修改 | `MemoryConfig` 加 `search_depth_default` 字段（初始值 `full`） |
| Server `routers/memory.py` | 修改 | `/search` 端点加可选 `depth` query param |
| SDK `mem0/client/main.py` | 修改 | `search()` 方法加 `depth` 参数，透传到 Server 的 `depth` query param |

### 2.4 新增配置项

```yaml
MEM0_SEARCH_DEPTH_AUTO=true            # 启用自动深度判定（默认开，配 full 默认值确保零行为变化）
MEM0_SEARCH_DEPTH_DEFAULT=full         # 自动判定的兜底深度（v1 专用；下版本切 standard）
MEM0_SEARCH_DEPTH_CACHE_SECS=30        # search_keywords 表缓存秒数（0 每次查 DB，30 为推荐值）
MEM0_SEARCH_CACHE_TTL=15               # minimal 路径 LRU 缓存 TTL 秒（0 禁用）
MEM0_SEARCH_STD_CACHE_TTL=5            # standard 路径 LRU 缓存 TTL 秒（0 禁用）
```

关键词不再通过环境变量配置——全部存储在 `search_keywords` 表中，INSERT 即生效。
`MEM0_SEARCH_DEPTH_CACHE_SECS` 控制从 DB 读取关键词的缓存时间（避免每次 search 都查表）。

### 2.5 效果验证指标

```
search_depth:minimal_count     # minimal 命中次数 → 降本证据
search_depth:standard_count    # standard 次数
search_depth:full_count        # full 次数（不变部分）
search_depth:lru_hit_count     # 缓存命中 → 额外降本
search_depth:avg_latency_ms    # 按深度级分桶统计
search_depth:default_full_count # 走 full 默认值的实际次数（用于评估何时可切 standard）
correction:trigger_rate         # 纠正感知触发比例（监控误触发，§3.5.1）
```

### 2.6 边界情况

| 场景 | 判定 | 说明 |
|------|------|------|
| Agent 例行 recall | standard | 日常上下文，向量+BM25 足够 |
| 用户说"不对，上次不是这样的" | full | "不对"触发纠正词→full |
| 用户说"好的" | minimal | DB exact 匹配命中 |
| 空字符串或纯标点 | minimal | `<4` 字符拦截 |
| 长文本问题（>50 字） | full | 语义复杂度高 |

---

## 3. 用户纠正感知

### 3.1 现状

当前矛盾检测（contradiction detection）在写入时发现冲突并处理：

```
add("发哥喜欢喝茶") → 检测到已有"发哥喜欢喝咖啡" → DELETE 旧记忆 → INSERT 新记忆
```

但依赖写入触发。用户会话中说出"不对"时，Agent 靠标准 `search()` 找旧记忆——标准 threshold 可能已过滤掉，导致无法自我纠正。

### 3.2 设计

在 `search()` 入口检测纠正信号，命中时自动放宽搜索参数。

#### 判定规则

纠正关键词从 `search_keywords` 表中 `category='correction'` 读取（与 §2 深度路由共享词表），`contains` 匹配。命中任一即触发 correction mode：

```
输入 query → 查 search_keywords WHERE category='correction'
  ├─ query 含任一 correction 关键词 → 触发 correction mode
  └─ 不匹配 → 正常搜索
```

#### 初始默认词表

纠正关键词与 §2 深度路由共享 `search_keywords` 表，种子数据见 §2.2「correction 类」INSERT 语句。无需单独配置环境变量。如需增删改，直接操作表即可生效，无需重启。

#### 触发后行为

只调搜索参数，不改检索逻辑：

```python
if correction_mode:
    effective_threshold = min(config.threshold, MEM0_CORRECTION_THRESHOLD)
    effective_top_k = max(config.top_k, MEM0_CORRECTION_TOP_K)
    effective_depth = "full"         # 强制 full 深度
else:
    effective_threshold = config.threshold
    effective_top_k = config.top_k
```

不变：不调 rerank 参数，不改排序公式，不加额外 LLM。只是给搜索更大的"渔网"。

#### 与矛盾检测的关系

```
写入时                              检索时
add("发哥爱喝茶")                   search("不对，是喝咖啡")
  │                                    │
  ▼                                    ▼
矛盾检测：发现冲突                  纠正感知：检测"不对"
DELETE 旧记忆                          │
INSERT 新记忆                          ▼
                              threshold 降低，top_k 扩大
                                       │
                                       ▼
                              旧记忆进入候选（可能已被矛盾检测干掉）
```

两者互补不重叠：

- 矛盾检测：写入时自动化解冲突。
- 纠正感知：检索时被动兜底（当矛盾检测没触发、或旧记忆未写入时，用户仍然可以说"不对"找回旧记忆）。

**增强：`lane_filter` 搜索参数**（v1 包含）

在 `search()` 和 `/search` API 中新增 `lane_filter` 参数，按轨道过滤结果：

```python
search("配置怎么设", lane_filter="slow")
# 只返回 slow 轨道的记忆，排除 normal/fast
```

仅做最终结果过滤，不影响衰减计算和排序。实现很简单——search 结果返回前逐条检查 `memory.lane`，不匹配的直接丢弃。

### 3.3 改动文件清单

| 文件 | 改动 | 内容 |
|------|------|------|
| `mem0/memory/main.py` | 修改 | `search()` 入口查 `search_keywords` 表 `correction` 类 → 触发后覆盖 threshold/top_k/depth |
| Server `routers/memory.py` | 间接 | 复用 main.py 入口逻辑 |

### 3.4 新增配置项

```yaml
MEM0_CORRECTION_MODE=false              # 总开关，默认关
MEM0_CORRECTION_THRESHOLD=0.1          # 放宽后的相似度阈值
MEM0_CORRECTION_TOP_K=30                # 放宽后返回数量上限
MEM0_CORRECTION_MAX_RATE=0.3            # 纠正触发率告警阈值（0~1），超过此比例则 log warning。metric: correction:trigger_rate，告警实现见 §3.5.1
```

### 3.5 效果验证

```
# 正常搜索
POST /search {"query": "发哥喜欢喝什么"}
→ threshold=0.3，旧咖啡记忆被过滤 → 空结果

# 纠正信号触发
POST /search {"query": "不对，发哥喜欢喝咖啡"}
→ correction_mode → threshold=0.1 → 旧记忆进入候选
```

#### 3.5.1 误触发告警

`MEM0_CORRECTION_MAX_RATE` 用于防止纠正关键词过度宽松导致每轮都走 full 深度。每 N 次 `search()` 调用统计一次触发率：

```python
# 在 search() 入口，纠正模式触发后累加计数
correction_triggers += 1

if search_calls_since_check >= 100:  # 每 100 次检查一次
    rate = correction_triggers / search_calls_since_check
    if rate > MEM0_CORRECTION_MAX_RATE:
        logger.warning(
            f"correction:trigger_rate={rate:.2f} "
            f"exceeds threshold {MEM0_CORRECTION_MAX_RATE}"
        )
    correction_triggers = 0
    search_calls_since_check = 0
```

metric 名：`correction:trigger_rate`（对齐 §2.5 指标命名规范）。

### 3.6 边界情况

| 场景 | 表现 | 说明 |
|------|------|------|
| 纠正词在无关句中出现 | 误触发，只是放宽搜索，无害 | 不会改排序，只扩候选池 |
| Agent 端每轮都带纠正词 | 频率警告 | 建议设 `MEM0_CORRECTION_MAX_RATE` |

---

## 4. 三功能交互矩阵

三个功能同时开启时的综合行为：

| 查询场景 | 深度路由判定 | 纠正感知触发 | Lane 应用 | 综合行为 |
|---------|-------------|-------------|----------|---------|
| "你好" | minimal | 否 | 不进入 search | 不检索，零成本 |
| "上次说的配置怎么弄" | standard | 否 | slow 记忆保留更好排前 | 向量+BM25，按 Lane 调分 |
| "不对，我记得是另一个版本" | full（纠正词） | 是，threshold 0.1 | 按 Lane 衰减调分 | 全套检索+宽阈值+Lane 排序 |
| "今天心情不错" | standard | 否 | fast 轨道快速衰减 | 短期留存，不污染长期记忆 |
| "发哥的项目是什么" | standard | 否 | normal 基准衰减 | 正常检索 |
| 空白/<3 字符 | minimal | 否 | 不进入 search | 零成本 |
| "为什么我的配置不对" | full（>50字符+"为什么"） | 否 | 按 Lane 调分 | 全套检索，正常阈值 |
| "详细说说咖啡的做法" | full（"详细"触发） | 否 | 按 Lane 调分 | 全套检索 |

交互规则：

1. **depth=minimal 优先级最高**——纠正感知和 Lane 都不触发（不进入 search）。
2. **纠正感知强制 depth=full**——覆盖深度路由的自动判定。
3. **Lane 在 scoring 层生效**——独立于 depth 和纠正感知，只影响最终排分。
4. **纠正感知减阈值 + Lane 乘衰减**——两者独立叠加（纠正让更多人场，Lane 影响谁排前面）。

### 实施顺序与依赖关系

```
第一阶段（独立，无依赖）：
  自适应检索深度 —— 纯 search 入口改动，不碰写入路径

第二阶段（依赖数据库迁移）：
  Lane 分轨衰减 —— 需加列 + 改写入/检索两路径

第三阶段（依赖深度路由）：
  用户纠正感知 —— 复用深度路由的 depth=full 强制机制

三个功能可独立上线，但纠正感知建议最后（依赖 depth=full 链路已稳定）。
```

---

## 5. v1.2 变更记录

| 项目 | v1.1 | v1.2 | 原因 |
|------|------|------|------|
| **§1 Lane 设计** | LLM 仅判 lane；importance 字段只读不写（死代码） | **LLM 同时判 importance + lane；_decay_fn 两条路径都接活** | 审计发现 importance 从未被写入 |
| **§1 持久化** | memories 表加 lane 列 | **存入 payload metadata 不加列** | lane 随记忆 payload 走，无需 migration |
| **§1 文档** | 关键词兜底覆盖所有 | **关键词只兜底 lane，importance 留给 LLM** | importance 难用关键词判断 |
| **新增** 实现状态表 | 无 | **完成状态表**（Phase 1 ✅ / Phase 2 🔄 / Phase 3 ⏳） | 跟踪进度 |
| **关键词存储** | 环境变量硬编码 | **search_keywords 表**（DB 驱动，热更新） | Phase 1 工程优化：INSERT 即生效、无需重启、exact/contains 分级匹配 |
| **LRU 缓存覆盖** | 仅 minimal 路径 | **minimal + standard 双 TTL** | Phase 1 降本天花板：short TTL 防重复检索 |

---

## 6. 向后兼容总表

| 功能 | 开关 | 默认值 | 关闭时行为 |
|------|------|--------|-----------|
| Lane 分轨 | `MEM0_LANE_ENABLED` | `false` | 全部 memory 走 normal 轨道，multiplier=1.0，行为不变 |
| 自适应深度 | `MEM0_SEARCH_DEPTH_AUTO` | `true` | v1 默认 `depth=full`，零行为变化。切 `standard` 前需确认上游不依赖图查询 |
| 纠正感知 | `MEM0_CORRECTION_MODE` | `false` | 完全不触发，搜索参数不变 |

唯一兼容风险点：`depth=standard` 跳过图查询。当前 v1 默认 `full` 规避此风险。

---

## 7. 附录：aiduMEM 参考代码状态

以下标注三个功能对应的 aiduMEM 上游代码是否真实工作：

| 功能 | aiduMEM 代码路径 | 代码状态 | 说明 |
|------|----------------|---------|------|
| **Lane 分轨** | `ducky/salience/core.py` (LaneDetector, ~60 行) | ✅ **真实代码，完整实现** | 关键词检测 + Lane 枚举 + multiplier 映射，全部有工作逻辑 |
| **Lane 衰减** | `ducky/salience/decay.py` (EbbinghausDecay, ~80 行) | ✅ **真实代码，完整实现** | 衰减公式、half-life 计算、should_forget 判定，全部实现 |
| **相关性闸门**（本方案引为深度路由灵感） | `ducky/memory_gate.py` (MemoryGate, ~150 行) | ✅ **真实代码，完整实现** | LRU 缓存 + 纠正信号检测 + 关键词匹配 + cache 失效 |
| **用户纠正感知** | `ducky/memory_gate.py` 中的 `_correction_regex`（检测信号） | ⚠️ 检测部分真实 | 关键词匹配检测信号有实现。但核心"放宽搜索阈值"在 aiduMEM 中无对应——`api_server.py` search 端点是 `# TODO: implement real search logic`。本方案的设计是独立于 aiduMEM 的推理，不依赖 aiduMEM 的实现完整性 |

**结论**：三个功能的 aiduMEM 参考点中，Lane 分轨和 MemoryGate 有工作代码支撑。纠正感知在 aiduMEM 是半成品（检测有、行为无），本方案的设计是独立推理，不依赖 aiduMEM 代码。
