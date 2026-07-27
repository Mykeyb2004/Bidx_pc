# Prompt Contract

## 1. 文档目的

本文说明章节正文生成时 system prompt、user prompt 与 trace 摘要的当前合同。维护时以本文和 `tests/test_prompt_contract.py` 为准。

相关入口：

- `bid_writer/ai_writer.py`
- `bid_writer/config.py`
- `bid_writer/context_pruner.py`
- `bid_writer/h2_project_background.py`

## 2. API 消息边界

章节生成只发送两条模型消息：

1. `system`：`Config.role` 加固定门禁文件 `roles/system_gate_rules.md`
2. `user`：当前章节上下文、输出提醒、事实卡片、节点撰写计划和最终任务卡

system prompt 始终是单独、更高优先级的 API message。采购需求、评分标准、事实卡片和节点撰写计划都不会拼入 system；它们只作为 user message 中的当前任务材料。

`roles/system_gate_rules.md` 负责正式文风、投标人称谓、禁用自解释等硬门禁。Mermaid 代码块只有在任务明确要求图示时允许出现必要的英文语法。

## 3. User Prompt 业务顺序

`auto`、pruned 和 `full_context` 分支现在共享同一业务阅读顺序：

1. `chapter_context`：`## 当前章节边界及招标/评分要求`
2. `output_constraint_reminder`：`## 输出硬约束提醒`
3. 可选 `fact_card_context`：`## 事实卡片参考`
4. 可选 `node_writing_plan`：`## 节点撰写计划`
5. `task_card`：`## 章节任务卡`，始终最后

差异只在 `chapter_context` 内部材料来源：

- `auto` / pruned：可包含 H2 项目背景、命中的评分关注和当前章节边界；不会再注入“需求要点”。
- `full_context`：可包含完整采购需求、完整评分标准和当前章节边界；不会额外生成 H2 项目背景。

`output_constraint_reminder` 是 user-side reminder，用于提醒模型遵守 system 硬门禁和当前章节边界；它不改变 system 的优先级。

## 4. 节点撰写计划

运行时传入 `AIWriter.build_prompt_result(..., additional_requirements=...)` 的业务含义已经统一为“节点撰写计划”。

行为规则：

- 空文本不生成 `## 节点撰写计划` 区块，任务卡也不写计划执行要求。
- 非空文本原样放在事实卡片之后、章节任务卡之前。
- 任务卡会要求“按照节点撰写计划组织本节点正文”，但计划与章节边界、招标/评分要求或 system 硬约束冲突时不得照搬。
- 配置 `project.inputs.writing_plan_file` 后，旧的 `processing.full_context.chapter_writing_plan` 自动生成计划不会同时启用，避免两套计划冲突。

## 5. Section 一览

| Section id | 最终标题 | 何时出现 |
|---|---|---|
| `chapter_context` | `## 当前章节边界及招标/评分要求` | 总是出现 |
| `output_constraint_reminder` | `## 输出硬约束提醒` | 总是出现 |
| `fact_card_context` | `## 事实卡片参考` | 启用事实卡片且本章有可用卡片时 |
| `node_writing_plan` | `## 节点撰写计划` | 当前节点计划非空时 |
| `task_card` | `## 章节任务卡` | 总是出现且最后出现 |

不再出现：

- `## 用户附加要求`
- `## 需求要点`
- source-oriented 的 `structure_contract` 独立块

## 6. Prompt Contract Blocks

trace 中的 `prompt_contract_blocks` 是维护者摘要层，不会发送给模型。当前固定 block 顺序与 user prompt 业务顺序一致：

1. `system_constraints`
2. `chapter_context`
3. `output_constraints`
4. `fact_card_context`
5. `node_writing_plan`
6. `chapter_task`

可选 block 在没有对应文本时仍保留空摘要，以维持 trace schema 稳定。`node_writing_plan` 只有在实际注入时才带 `source_context: ["additional_requirements"]`。

## 7. 示例形态

```text
[system]
{role}

【最高优先级输出强约束】
...

[user]
## 当前章节边界及招标/评分要求
### 招标需求参考 / 项目背景参考 / 评分要求（按可用材料出现）
...
### 当前章节边界
...

## 输出硬约束提醒
...

## 事实卡片参考
...

## 节点撰写计划
...

## 章节任务卡
...
- 最终执行说明：直接输出当前章节投标正文。
```

## 8. 维护要点

- 新增 prompt 区块时，必须同步更新 `tests/test_prompt_contract.py`、本文和 trace block 合同。
- 需要采购需求全文直接进入模型时使用 `full_context`；`auto` 只通过 H2 项目背景使用采购需求证据。
- 节点撰写计划是当前节点的最终阶段写作指令，不是跨章节继承规则，也不是批量编辑入口。
