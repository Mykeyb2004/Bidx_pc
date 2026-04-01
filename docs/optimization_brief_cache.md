# 优化方案：按共享 h2 章节缓存 requirement_brief LLM 调用

## 背景

扩写时每个 h3/h4 节点都调用 `ChapterContextPruner.build_context(heading)`，其中：

- **评分条目提取**（scoring_items）：纯文本关键词匹配，无 LLM，快
- **需求块选择**（requirement_seed）：文本相似度打分，无 LLM，快
- **需求摘要生成**（requirement_brief）：调用二级 LLM（gpt-5.4-mini），**慢且贵** ← 唯一瓶颈

关键观察：真正慢的是 `_build_requirement_brief()` 里的 LLM 调用。  
而在当前业务里，同一 `h2` 章节下的 `h3/h4` 通常共享同一批“采购需求”和“评分标准”，适合共用一份 brief。

---

## 方案：在 ChapterContextPruner 内部按共享 h2 路径缓存 brief

### 核心思路

`requirement_brief` 是唯一的 LLM 瓶颈。其他字段（`scoring_items`、`requirement_seed`）仍按当前叶子标题独立计算，保留精度。

只对 brief 做共享章节级别的缓存：

```
h3-2.1.1 / h3-2.1.2 / h4-2.1.x → 共享所属 h2 = "2.1"
第一次命中该 h2 → 用 h2 上下文生成 brief → 写入 cache["2.1"]
后续同 h2 下标题 → 直接复用 cache["2.1"]
```

也就是说，缓存的不是“第一个子节点的 brief”，而是“共享 h2 章节的 brief”。

### 实现

**文件**：`bid_writer/context_pruner.py`

**步骤 1**：在 `__init__` 中添加 brief 缓存：

```python
self._brief_cache: dict[str, str] = {}  # scope_path → brief
```

**步骤 2**：把 `build_context()` 拆成两层：

- `_build_base_context(heading)`：只算 `scoring_items` / `requirement_seed`
- `_build_requirement_brief_with_cache(heading, context)`：决定是否走共享 h2 brief

**步骤 3**：为当前标题解析共享作用域：

```python
if heading.level >= 3:
    scope_heading = nearest_h2_ancestor(heading) or heading.parent or heading
else:
    scope_heading = heading
```

**步骤 4**：先尝试共享缓存，再生成共享 brief：

```python
if scope_heading.full_path in self._brief_cache:
    return cached_brief

scope_context = current_context if scope_heading is heading else _build_base_context(scope_heading)
brief = _build_requirement_brief(scope_heading, scope_context)
if brief generated:
    cache[scope_heading.full_path] = brief
```

**步骤 5**：如果共享 h2 brief 生成失败或为空，则回退到当前章节自己的 brief，避免因为共享摘要失败而损失当前章节质量。

**步骤 6**：调用方 `ai_writer.py` 无需修改，透明复用。

---

## 调用次数估算

| 场景 | 当前 | 优化后 |
|------|------|--------|
| 5 h2 × 4 h3 × 3 h4 = 60 个 h4 | 60 次 LLM | 5 次左右（理想情况每 h2 1 次） |
| 5 h2 × 4 h3 = 20 个 h3 | 20 次 LLM | 5 次（每 h2 首次触发） |

---

## 精度影响分析

- **brief 精度**：brief 由共享 h2 章节驱动，不再绑定某个首个子节点，语义更稳定
- **scoring_items 精度**：不受影响（仍按各自叶子标题独立匹配）
- **潜在损失**：个别 h4 的独特细节不会进入共享 brief，但仍会体现在各自的 `scoring_items` / `requirement_seed` 中
- **兜底策略**：共享 brief 不可用时，自动回退到当前章节自己的 brief

---

## 验证方式

1. 批量扩写同一 `h2` 下多个 `h3/h4`，观察日志中 `requirement_brief_status`：
   第一个应为 `generated_shared_h2`，后续应为 `cached_shared_h2`
2. 对比 brief 内容：同一 `h2` 下不同叶子节点应拿到相同 brief
3. 对比 `scoring_items`：不同叶子节点仍应保持各自命中结果
4. 计时对比：同一 `h2` 下批量扩写总耗时应接近单次 brief 生成 + 多次正文生成
