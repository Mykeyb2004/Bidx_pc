# Prompt Contract

## 1. 文档目的

本文说明当前代码中 system prompt 与 user prompt 的真实拼接合同，重点回答：

1. system prompt 从哪里来
2. `auto` / `full_context` 两条链路分别给模型什么材料
3. user prompt 按什么顺序拼接
4. trace 中的 prompt contract block 如何理解

相关代码入口：

- `bid_writer/ai_writer.py`
- `bid_writer/context_pruner.py`
- `bid_writer/config.py`
- `bid_writer/h2_project_background.py`

## 2. 调用链

章节生成时的 prompt 链路固定为：

1. `AIWriter.prepare_generation(...)`
2. `AIWriter.build_prompt_result(...)`
3. 若 `context_pruning_enabled=True`，调用 `ChapterContextPruner.build_context(heading)`
4. `AIWriter.build_system_prompt()`
5. 组装 `messages = [{"role": "system", ...}, {"role": "user", ...}]`
6. `_build_request_options(...)`
7. `expand_raw()` 调用大模型

真正进入正文生成模型的只有两段：

- `system prompt`
- `user prompt`

没有隐藏的第三段 prompt。

## 3. System Prompt

`system prompt` 由两部分组成：

1. `Config.role`
2. 固定门禁文件 `roles/system_gate_rules.md`

如果配置里没有角色设定，默认角色是：

```text
你是一位专业的标书撰写专家。
```

`roles/system_gate_rules.md` 会被放入“最高优先级输出强约束”区块。运行时只做必要校验和 `{bidder_name}` 替换；如果门禁文件缺失或为空，会 fail fast。

以下内容不进入 system prompt：

- 采购需求原文
- 评分标准原文
- 用户附加要求
- 旧 `prompt.hard_constraints`
- 旧 `prompt.output_format`
- 旧 `prompt.first_line_template`

## 4. ChapterContext

`ChapterContext` 是章节级裁剪结果。当前字段包括：

- `response_labels`
- `chapter_focus_terms`
- `match_keywords`
- `scoring_items`
- `scoring_candidates`
- `scoring_must_respond`
- `scoring_reference`
- `retrieval_mode`
- `fallback_reason`
- `selected_scoring_unit_ids`

当前不会再生成以下旧字段：

- `requirement_seed`
- `requirement_blocks`
- `requirement_brief`
- `requirement_brief_status`
- `selected_requirement_unit_ids`

也就是说，pruned/auto 分支已经取消“当前章节需求要点”设计。

## 5. User Prompt 拼接规则

### 5.1 pruned / auto 分支

当 `ChapterContextPruner.build_context()` 成功返回时，进入 pruned 分支。当前顺序是：

1. 可选 `project_background`
2. 可选 `scoring_focus`
3. `scope_reference`
4. 可选 `fact_card_context`
5. `structure_contract`
6. 可选 `additional_requirements`
7. `task_card`

其中：

- `project_background` 只在 H2 项目背景可用时出现
- `scoring_focus` 只在命中评分项时出现
- 不再出现 `## 需求要点`
- 不再出现 `requirement_brief` / `requirement_points`

### 5.2 full_context 分支

以下情况进入 full-context 分支：

- `processing.path: full_context`
- `context_pruning_enabled=False`
- `context_pruner.build_context(...)` 异常并被回退

当前顺序是：

1. `structure_contract`
2. 可选 `bid_requirements`
3. 可选 `scoring_criteria`
4. `scope_reference`
5. 可选 `fact_card_context`
6. 可选 `additional_requirements`
7. `task_card`

`full_context` 已经把完整采购需求和评分标准放入 prompt，因此不会额外生成 `project_background`。

## 6. Section 一览

| Section id | 最终标题 | 何时出现 |
|---|---|---|
| `task_card` | `## 章节任务卡` | 总是出现 |
| `structure_contract` | 无独立标题 | 总是出现 |
| `scope_reference` | `## 章节边界参考` | 总是出现 |
| `project_background` | `## 项目背景` | pruned/auto 分支中 H2 项目背景非空时 |
| `scoring_focus` | `## 评分关注` | pruned/auto 分支且命中评分项时 |
| `fact_card_context` | `## 事实卡片参考` | 启用事实卡片且本章有可用卡片时 |
| `bid_requirements` | `## 招标需求参考` | full_context 分支且有采购需求原文时 |
| `scoring_criteria` | `## 评分标准参考` | full_context 分支且有评分标准原文时 |
| `additional_requirements` | `## 用户附加要求` | 运行时附加要求非空时 |

## 7. 章节任务卡

`task_card` 当前固定包含：

- 写作场景
- 当前章节路径
- 本章重点
- 篇幅目标区间
- 输出方式
- 表格控制
- 可选流程图控制
- 写作依据
- 可选章节写作计划

`pruned` 分支中的写作依据现在是：

```text
- 写作依据：优先根据前文项目背景、评分关注和章节边界组织内容。
```

`full_context` 分支会根据是否存在完整采购需求和评分标准，改成引用前文固定参考材料，避免“下方”指代错位。

## 8. H2 项目背景

`auto` 且 `processing.project_background.enabled=true` 时，`H2ProjectBackgroundGenerator.get_for_heading()` 会为当前章节所属 H2 提供项目背景。

默认 `content_mode: excerpts`：

- 背景正文直接来自采购需求原文摘录
- 证据片段写入 trace
- 不调用辅助模型生成摘要

只有 `content_mode: summary` 时，才调用辅助模型基于证据片段生成 H2 摘要。

H2 项目背景的职责是提供章级项目语境，不再和“需求要点”并列。

## 9. 评分关注

`scoring_focus` 来自 `ChapterContext.scoring_items`，或 auto 模式下的：

- `scoring_must_respond`
- `scoring_reference`

评分检索可以走规则表格解析，也可以走 hybrid retrieval。若开启 verifier，辅助模型只返回候选 ID，程序再回填原文。

## 10. Prompt Contract Blocks

trace 中的 `prompt_contract_blocks` 是维护者摘要层，不会发送给模型。

当前 block 固定为：

1. `system_constraints`
2. `chapter_task`
3. `structure_rules`
4. `chapter_scope`
5. `project_background`
6. `fact_card_context`
7. `scoring_context`

已经移除：

- `requirement_context`

## 11. 示例形态

### pruned / auto

```text
[system]
{role}

【最高优先级输出强约束】
...

[user]
## 项目背景
...

## 评分关注
...

## 章节边界参考
...

## 事实卡片参考
...

请严格遵守 system 中全部硬门禁，直接输出当前章节投标正文。
...

## 用户附加要求
...

## 章节任务卡
...
```

### full_context

```text
[system]
{role}

【最高优先级输出强约束】
...

[user]
请严格遵守 system 中全部硬门禁，直接输出当前章节投标正文。
...

## 招标需求参考
...

## 评分标准参考
...

## 章节边界参考
...

## 章节任务卡
...
```

## 12. 调 prompt 时的直接结论

1. 改 system 角色，改 `Config.role` 或角色文件。
2. 改最高优先级门禁，改 `roles/system_gate_rules.md`。
3. 改任务卡、章节边界、评分关注、项目背景拼接，改 `AIWriter.build_prompt_result()` 相关方法。
4. 改评分召回和分类，改 `context_pruner.py`。
5. 改 H2 背景证据和摘要生成，改 `h2_project_background.py`。
6. 需要采购需求全文直接进入模型时，使用 `full_context`；`auto` 只通过 H2 项目背景使用采购需求证据。
