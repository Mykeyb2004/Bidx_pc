# 知识库方案：双来源知识注入与三层过滤

## 一、问题背景

### 1.1 当前现状

系统已有三层上下文注入机制：

| 组件 | 职责 | 注入位置 |
|------|------|----------|
| `ProjectBackgroundGenerator` | 从招标需求提炼项目背景摘要（~800 字） | prompt `project_background` 区块 |
| `ChapterContextPruner` | 按章节裁剪评分项和需求要点 | prompt `scoring_focus` / `requirement_brief` 区块 |
| `ChapterSummaryGenerator` | 对已生成/已规划章节生成 160-220 字叙述摘要 | 通过 `additional_requirements` 注入 |

### 1.2 实际 prompt 数据（183 个 trace 样本）

| 指标 | 典型值 | 带依赖注入 |
|------|--------|-----------|
| system prompt | ~1555 字 | ~1555 字 |
| user prompt | ~5300 字 | ~11500 字 |
| 招标需求 | ~1800 字（33.8%） | ~1800 字（15.8%） |
| 评分标准 | ~2450 字（46.1%） | ~2450 字（21.4%） |
| 任务卡+边界+背景 | ~1000 字（20%） | ~1000 字（8.7%） |
| 用户附加要求（含依赖） | 0 | ~6226 字（54.2%） |

**核心矛盾**：依赖内容注入后，章节生成指令（任务卡+边界）被压缩到不足 9%。模型注意力被大量参考材料稀释，导致生成内容对当前章节的针对性下降。

### 1.3 缺失的能力

1. **无投标方事实源**：招标需求和评分标准描述的是甲方要求，但投标方自身信息（公司名称、团队架构、技术选型、服务承诺）没有统一维护的地方。不同章节各自编造，互相矛盾。
2. **依赖注入缺乏筛选**：当前把依赖章节的完整叙述摘要拼接注入，不区分"哪些信息和当前章节相关"。
3. **事实与概述混为一谈**：叙述摘要适合告诉模型"前面大概写了什么"，但无法精确锚定具体数字、人名、日期等硬事实。

---

## 二、设计目标

1. **一致性**：所有章节引用同一事实时，输出保持一致（人名、数字、日期、承诺不矛盾）。
2. **针对性**：每个章节只接收与自己相关的知识，不被无关信息稀释。
3. **可控性**：知识注入有明确的 token 预算，不会让 prompt 失控膨胀。
4. **渐进性**：新机制与现有摘要并行，验证效果后逐步替代，不一次性破坏现有链路。

---

## 三、整体架构

```
┌─────────────────────────────────────────────────────┐
│                    知识库（KnowledgeBase）              │
│                                                       │
│  来源一：用户手写文档          来源二：章节事实提炼       │
│  knowledge/*.md              ChapterFactStore          │
│  + config.yaml 声明           (自动/手动触发)           │
│                                                       │
└──────────────┬─────────────────────┬─────────────────┘
               │                     │
               ▼                     ▼
       ┌───────────────────────────────────┐
       │      KnowledgeAssembler            │
       │                                     │
       │  第一层：scope 过滤                  │
       │    global 事实 → 始终保留            │
       │    local 事实 → 关键词匹配           │
       │                                     │
       │  第二层：去重合并                    │
       │    同一事实出现在多个章节 → 合并      │
       │                                     │
       │  第三层：预算截断                    │
       │    超出 budget → 按优先级截断        │
       │                                     │
       └──────────────┬──────────────────────┘
                      │
                      ▼
              ┌─────────────────┐
              │  build_prompt_result  │
              │                       │
              │  knowledge_context    │ ← 新增区块
              │  (结构化事实清单)      │
              └─────────────────────┘
```

### 与现有组件的关系

```
现有组件（保留）                    新增组件
─────────────                    ─────────
ChapterDependencyStore           KnowledgeAssembler
  → 查依赖关系（不变）               → 整合双来源、三层过滤

ChapterSummaryGenerator          ChapterFactExtractor
  → 叙述摘要（阶段一并行保留）        → 结构化事实提炼
  → 阶段二被事实清单逐步替代

ProjectBackgroundGenerator       用户手写知识文档
  → 项目背景摘要（不变）             → knowledge/ 目录 + config 声明
```

---

## 四、来源一：用户手写知识文档

### 4.1 文档组织

支持两种方式并存（config 声明 + 目录自动扫描）：

**方式 A：config.yaml 声明**

```yaml
project:
  inputs:
    knowledge_files:
      - ./knowledge/公司简介.md
      - ./knowledge/项目团队.md
      - ./knowledge/服务承诺.md
```

路径解析规则与现有 `bid_requirements_file` 一致，相对于配置文件所在目录。

**方式 B：自动扫描 knowledge/ 目录**

```yaml
project:
  inputs:
    knowledge_directory: ./knowledge/
```

扫描该目录下所有 `.md` 文件，按文件名排序加载。

**合并逻辑**：`knowledge_files` 中声明的文件 + `knowledge_directory` 下扫描到但未在 `knowledge_files` 中重复声明的文件。声明文件优先排序。

### 4.2 文档格式规范

推荐 key-value 清单式，便于模型精确提取：

```markdown
# 项目团队

- 项目经理：张三，PMP认证，15年政府信息化项目管理经验
- 技术负责人：李四，高级架构师，10年大数据平台经验
- 驻场人员：不少于5人
- 项目组总人数：不少于12人
- 组织架构：项目管理组、技术开发组、质量保障组、运维服务组
```

不强制格式校验。用户也可以写散文段落，系统原样注入。

### 4.3 Config 属性

```python
# Config 类新增属性

@property
def knowledge_files(self) -> list[str]:
    """用户声明的知识文档路径列表。"""

@property
def knowledge_directory(self) -> str:
    """知识文档自动扫描目录。"""

@property
def knowledge_enabled(self) -> bool:
    """是否启用知识库注入。默认 True。"""

@property
def knowledge_max_chars(self) -> int:
    """知识库注入的最大字符数预算。默认 800。"""
```

---

## 五、来源二：章节事实提炼

### 5.1 提炼模型

新增 `ChapterFactExtractor`，与现有 `ChapterSummaryGenerator` 平行：

```
bid_writer/
├── chapter_summary_generator.py   # 已有：叙述摘要
├── chapter_summary_store.py       # 已有：摘要缓存
├── chapter_fact_extractor.py      # 新增：事实提炼
└── chapter_fact_store.py          # 新增：事实缓存
```

### 5.2 提炼 prompt

```
请从以下标书章节正文中提取所有可被其他章节引用的事实性信息。

提取规则：
1. 只提取具体的事实断言：时间节点、人员数量/姓名、技术选型、服务承诺、数量指标、流程阶段划分等。
2. 不要提取概括性描述或修饰性表述。
3. 每条事实用以下格式输出：
   - [global] 类别: 具体内容
   - [local] 类别: 具体内容
4. 判断标准：如果这条信息在"售后服务""质量保障""技术方案""项目团队"等不同主题章节中都可能被引用，标 [global]；仅与当前章节主题密切相关的标 [local]。
5. 如果正文没有可提取的硬事实，只输出"无可提取事实"。

章节标题：{heading.title}
章节路径：{heading.full_path}
章节正文：
{content}
```

### 5.3 存储格式

文件位置：`{project_root}/.bid_writer/chapter_facts.json`

```json
{
  "version": 1,
  "updated_at": "2026-04-14T10:00:00+08:00",
  "items": {
    "项目名 > 3. 项目实施计划 > 3.1 总体进度安排": {
      "title": "3.1 总体进度安排",
      "source_hash": "output:a1b2c3d4",
      "extracted_at": "2026-04-14T10:00:00+08:00",
      "facts": [
        {
          "scope": "global",
          "category": "实施总周期",
          "value": "合同签订后6个月内完成全部交付"
        },
        {
          "scope": "global",
          "category": "驻场人数",
          "value": "项目实施期间驻场不少于5人"
        },
        {
          "scope": "local",
          "category": "阶段划分",
          "value": "需求调研(1月) → 系统开发(3月) → 测试部署(1月) → 试运行(1月)"
        },
        {
          "scope": "local",
          "category": "样本目标",
          "value": "每个县市区130-140个成功样本"
        }
      ]
    }
  }
}
```

### 5.4 缓存与失效

复用现有 `ChapterSummaryStore` 的 `source_hash` 机制：

- 对章节正文内容计算 SHA-1 hash
- 如果 hash 未变，直接返回缓存的事实列表
- 如果 hash 变化（章节重新生成），重新提炼
- 读取 facts 时如果缓存 `source_hash` 与当前正文不一致，则视为 stale，旧 facts 不再注入 prompt
- 如果异步提炼失败，保留用户手写知识注入，但不回退使用 stale facts；只记录日志并标记该章节待刷新

### 5.5 触发时机

采用混合模式：

| 场景 | 触发方式 | 原因 |
|------|----------|------|
| 批量生成 | 自动（章节保存后异步提炼） | 批量流程中用户不希望逐个手动操作 |
| 单章节生成 | 手动（右键菜单"提炼事实"） | 单章节场景下用户可能还在调整内容，不宜自动触发 |
| 手动入口 | 右键菜单 / 工具栏按钮 | 用户主动控制 |

自动触发实现方式：在 `_generate_into_workspace` 中 `file_saver.save()` 成功后，按本次生成模式显式判断 `auto_extract_facts`（或等价标记），仅批量生成路径启动异步线程提炼。不要仅凭调用了 `_generate_into_workspace()` 就默认自动提炼，否则单章节生成也会被误触发。整体执行方式与现有 `finalize_generation` 的 trace 写入模式一致，不阻塞 UI。

### 5.6 LLM 调用配置

复用现有 pruning model 配置（`BID_WRITER_PRUNING_*` 系列环境变量）。事实提炼属于轻量辅助任务，适合用成本更低的模型执行。

---

## 六、三层过滤机制

在进入三层过滤前，`KnowledgeAssembler` 的输入范围固定如下：

- 用户手写知识：始终读取，作为独立来源参与预算分配
- 章节事实：默认只读取**当前章节依赖项对应章节**的 facts，不扫描全项目所有章节
- “全项目 global facts 跨依赖自动注入”不纳入本期范围，作为后续增强能力单独评估

### 6.1 第一层：scope 过滤（零 LLM 成本）

```python
def filter_relevant_facts(
    facts: list[ExtractedFact],
    heading: HeadingNode,
    focus_terms: list[str],
) -> list[ExtractedFact]:
    result = []
    for fact in facts:
        if fact.scope == "global":
            result.append(fact)
            continue
        # local 事实：类别或内容与当前章节关键词有交集才保留
        fact_text = fact.category + fact.value
        if any(term in fact_text for term in focus_terms):
            result.append(fact)
    return result
```

`focus_terms` 复用现有 `AIWriter._chapter_focus_terms()` 的输出，不额外计算。

### 6.2 第二层：去重合并

同一事实可能从多个依赖章节中提炼出来（如"项目经理：张三"可能同时出现在"项目团队"和"项目实施计划"的事实中）。

去重规则：
- 先按 `category` 做归一化分组
- 若同组内 `value` 归一化后相同，则视为重复项，合并来源标签（如 `[项目团队, 项目实施计划]`）
- 若同组内 `value` 明显不同，则默认并存，不强行覆盖；仅对明确的单值事实类别（如项目经理、实施总周期）保留信息更完整的那条

### 6.3 第三层：预算截断

总预算默认 `knowledge_max_chars: 800`（约占典型 user prompt 的 15%）。

截断优先级（从高到低）：

| 优先级 | 内容 | 理由 |
|--------|------|------|
| 1 | 用户手写知识 | 用户主动提供，意图最明确 |
| 2 | global 事实 | 跨章节一致性保障 |
| 3 | local 匹配事实 | 当前章节细节对齐 |

超出预算时，从优先级最低的 local 事实开始截断；如果仍然超标，再截断低优先级 global 事实；最后才处理用户手写知识。阶段一仅做按段落/条目边界的硬截断，不引入额外 LLM 调用；阶段三起如仍有需要，再对用户手写知识启用摘要压缩（调用 pruning model）。

### 6.4 预算依据

基于实际 prompt 数据：

```
典型 user prompt ≈ 5300 字

知识预算 800 字注入后：
  user prompt ≈ 6100 字
  知识占比 ≈ 13%
  任务卡+边界 占比 ≈ 16%  (从 20% 降到 16%，可接受)

对比当前依赖注入：
  user prompt ≈ 11500 字
  依赖内容占比 ≈ 54%
  任务卡+边界 占比 ≈ 9%   (严重稀释)
```

800 字预算可容纳约 12-15 条结构化事实，足以覆盖一个章节需要对齐的所有关键信息。

---

## 七、Prompt 注入设计

### 7.1 新增 `knowledge_context` 区块

在 `_PROMPT_CONTRACT_BLOCKS` 中，插入到 `project_background` 之后、`requirement_context` 之前：

```python
_PROMPT_CONTRACT_BLOCKS: tuple[tuple[str, str, str], ...] = (
    ("system_constraints", "System Constraints", "system"),
    ("chapter_task", "Chapter Task", "user"),
    ("structure_rules", "Structure Rules", "user"),
    ("chapter_scope", "Chapter Scope", "user"),
    ("project_background", "Project Background", "user"),
    ("knowledge_context", "Knowledge Context", "user"),    # ← 新增
    ("requirement_context", "Requirement Context", "user"),
    ("scoring_context", "Scoring Context", "user"),
)
```

实现上需要分两处接入：

- 在 `build_prompt_result()` 中实际追加 `knowledge_context` section，确保内容进入最终 user prompt
- 在 `_build_prompt_contract_blocks()` 中补充 `knowledge_context` 的 block spec，并同步 `_PROMPT_CONTRACT_BLOCKS` 顺序，确保 trace/contract 与真实 prompt 一致

### 7.2 注入格式

```markdown
## 投标方知识库
以下为投标方提供的事实性参考信息和已生成章节中确立的关键事实。
正文涉及相关内容时必须与以下保持一致，不得编造矛盾信息。

### 投标方信息
- 项目经理：张三，PMP认证，15年政府信息化项目管理经验
- 驻场人员：不少于5人
- 项目组总人数：不少于12人
（来自 knowledge/项目团队.md）

### 已确立事实
- 实施总周期：合同签订后6个月内完成全部交付 [来源: 3.1 总体进度安排]
- 阶段划分：需求调研(1月) → 系统开发(3月) → 测试(1月) → 试运行(1月) [来源: 3.1 总体进度安排]
```

关键设计：
- **"必须与以下保持一致"** — 硬约束措辞，比"可以参考"的遵从度显著更高
- **key: value 格式** — 每条事实独占一行，模型 attention 对结构化数据召回率高于段落
- **标注来源** — 便于 trace 追溯和人工审查

### 7.3 与现有叙述摘要的并行方案

阶段一（并行）：

```
knowledge_context 区块 → 结构化事实清单（新）
additional_requirements → 叙述摘要（现有，不变）
```

过渡期如果叙述摘要与 `knowledge_context` 出现冲突，以 `knowledge_context` 为准；叙述摘要只承担章节概述与边界提醒，不覆盖结构化事实。

阶段二（替代）：

验证事实清单效果后，将 `ChapterSummaryGenerator` 的叙述摘要从 `additional_requirements` 中移除。`additional_requirements` 回归只承载用户手动输入的附加要求。

---

## 八、新增模块清单

### 8.1 新增文件

| 文件 | 职责 |
|------|------|
| `bid_writer/chapter_fact_extractor.py` | 事实提炼引擎，调用 LLM 从正文提取结构化事实 |
| `bid_writer/chapter_fact_store.py` | 事实缓存持久化，JSON 文件读写 + hash 失效 |
| `bid_writer/knowledge_assembler.py` | 知识整合器，合并双来源 + 三层过滤 + 格式渲染 |

### 8.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `bid_writer/config.py` | 新增 `knowledge_*` 系列属性 |
| `bid_writer/main.py` | `BidWriter` 持有 `ChapterFactExtractor`、`KnowledgeAssembler` 实例 |
| `bid_writer/ai_writer.py` | `build_prompt_result()` 中增加 `knowledge_context` 区块拼装 |
| `bid_writer/gui.py` | `_generate_into_workspace()` 保存后触发异步事实提炼；右键菜单增加"提炼事实"入口 |

### 8.3 不修改的文件

| 文件 | 原因 |
|------|------|
| `chapter_summary_generator.py` | 阶段一保持不变，并行运行 |
| `chapter_summary_store.py` | 不变 |
| `chapter_dependency_store.py` | 不变，知识组装器直接消费其输出 |
| `context_pruner.py` | 不变，知识组装器复用其 focus_terms |

---

## 九、Config 新增字段

```yaml
project:
  inputs:
    # 知识文档路径列表（相对于配置文件目录）
    knowledge_files:
      - ./knowledge/公司简介.md
      - ./knowledge/项目团队.md

    # 知识文档自动扫描目录
    knowledge_directory: ./knowledge/

processing:
  knowledge:
    # 是否启用知识库注入
    enabled: true

    # 单章节知识注入最大字符数
    max_chars: 800

  chapter_facts:
    # 是否启用章节事实提炼
    enabled: true

    # 批量生成后是否自动提炼
    auto_extract_on_batch: true

    # 单章节最大提炼事实条数
    max_facts_per_chapter: 15
```

---

## 十、实施阶段

### 阶段一：用户手写知识注入（最小可用版本）

**范围**：仅来源一，零 LLM 调用。

- `Config` 新增 `knowledge_files`、`knowledge_directory`、`knowledge_enabled`、`knowledge_max_chars` 属性
- 新增 `KnowledgeAssembler`，仅实现文件读取 + 拼接 + 预算硬截断
- `build_prompt_result()` 增加 `knowledge_context` 区块
- 不触碰现有摘要链路
- 本阶段不做知识摘要压缩，确保新增链路保持零 LLM 调用

**验证方法**：对比同一章节注入知识前后的 trace，检查生成内容中事实一致性。

### 阶段二：章节事实提炼

**范围**：来源二，需 LLM 调用。

- 新增 `ChapterFactExtractor` + `ChapterFactStore`
- GUI 中增加右键菜单"提炼事实"
- 批量生成流程中保存后自动触发异步提炼，并通过显式标记区分批量/单章触发路径
- `KnowledgeAssembler` 扩展为合并双来源

**验证方法**：生成 3-5 个有依赖关系的章节，检查后续章节是否正确引用先前章节的具体数字和承诺。

### 阶段三：三层过滤 + scope 标签

**范围**：过滤优化。

- 提炼 prompt 中加入 `[global]` / `[local]` 标签
- `KnowledgeAssembler` 实现关键词匹配过滤 + 去重 + 预算截断
- 配置 `max_chars` 精调

**验证方法**：对比过滤前后的 prompt 大小和生成质量。观察 trace 中 `knowledge_context` 区块的实际字符数是否稳定在预算内。

### 阶段四：替代叙述摘要

**范围**：清理冗余。

- 从 `additional_requirements` 中移除 `dependency_summary_block` 注入
- `additional_requirements` 回归只承载用户手动输入
- 评估是否保留 `ChapterSummaryGenerator` 作为 UI 展示用途（树形结构中显示章节概要）

**验证方法**：A/B 对比替代前后的生成质量。重点关注章节间边界清晰度是否下降。

---

## 十一、关键设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 事实与摘要的关系 | 逐步替代 | 两者并存会双重注入，增加 token 开销；但需先验证事实清单效果 |
| 事实提炼触发方式 | 混合（批量自动 + 单章手动） | 批量流程需自动化；单章节用户可能还在调试内容 |
| 知识文档管理方式 | config 声明 + 目录扫描并存 | 声明方式精确控制顺序和范围；扫描方式降低配置负担 |
| 知识预算默认值 | 800 字 | 占典型 prompt 的 ~13%，可容纳 12-15 条事实，不显著稀释任务指令 |
| LLM 选择 | 复用 pruning model | 事实提炼是轻量任务，不需要主力模型 |
| 事实清单格式 | key: value 清单 | 结构化格式比散文的 attention 召回率更高 |
| 注入位置 | project_background 之后、requirement_context 之前 | 紧跟背景信息，在评分/需求之前建立事实锚点 |

---

## 十二、实现约束（避免落地分叉）

以下规则作为本期默认实现约束，除非后续方案文档明确修订，否则按此执行：

1. `knowledge_context` 必须同时接入真实 prompt 拼装和 prompt contract/trace 映射，不能只改 `_PROMPT_CONTRACT_BLOCKS`。
2. 章节事实自动提炼必须通过显式运行时标记区分“批量自动”和“单章手动”，不能因为共用了 `_generate_into_workspace()` 就默认两者都自动触发。
3. `KnowledgeAssembler` 默认只汇总两类输入：用户手写知识，以及当前章节依赖项对应章节的 facts；不扫描全项目所有章节。
4. facts 缓存一旦与当前正文 `source_hash` 不一致，就视为 stale，不允许把旧 facts 注入到新 prompt 中。
5. 阶段一保持零 LLM 调用；预算超限时只做硬截断，不做知识摘要压缩。压缩能力最早从阶段三引入。
6. 过渡期若 `knowledge_context` 与依赖摘要存在冲突，以 `knowledge_context` 为准；依赖摘要只保留概述和边界提醒职责。
7. facts 去重不能只按 `category` 粗暴覆盖；同类不同值默认并存，仅对明确的单值事实类别做“保留更完整一条”的合并策略。

---

## 十二、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 提炼出错误事实 | 后续章节引用错误信息 | 事实存储后支持用户在 GUI 中审查和编辑 |
| 用户手写文档过长 | 超出 token 预算 | 超标时对用户文档做 LLM 摘要压缩 |
| global/local 标签判断不准 | 该注入的事实被过滤掉 | 阶段三上线前用 trace 验证过滤准确率 |
| 批量生成时事实提炼延迟 | 后续章节开始生成时前序章节的事实尚未提炼完成 | 批量生成按顺序执行，章节 N 保存+提炼完成后再开始章节 N+1 |
