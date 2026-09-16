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

禁止自解释、自评论、自引用的条款集中在 system 门禁中：正文直接陈述业务内容，不解释当前输出的写作、排版、图表展示或编号安排，不评价其表达效果，不以“本文”“本章节”“下图”等引导阅读或说明表达作用。约束覆盖标题、图表前后说明、括号注释及结尾；图表标题使用业务名称，保留必要的 Mermaid 语法，正常业务流程说明、服务质量评价及采购政策依据引用不受影响。门禁要求生成模型输出前自行消除违规表述，但本要求仅通过提示词约束，不新增应用运行时检核、自动清理或修复调用，也不改变既有正文编号校验流程。

正文编号属于应用的最高优先级输出格式约束：每次独立扩写的首个正文标题从 `一、` 开始，最多使用 `一、 → （一） → 1. → （1）` 四层，同级连续编号，父级切换后下级从首号重新编号。不要求四层齐全。输入大纲路径不占正文层级；不得重复输入章节标题，也不得用单段摘要绕过编号要求。禁止的是 Markdown 标题标记，允许正式一级标题。角色、节点计划及参考材料不能覆盖这些格式约束，采购事实和评分要求不受改变。

门禁文件按配置目录优先、应用资源根目录兜底读取。user prompt 仅提醒遵守 system，不重复编号规则清单。

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

## 9. 输出校验与自动修复

`AIWriter.finalize_generation()` 在成功结束前调用 `body_numbering` 校验标题。除四级正式序号和 Markdown 标题外，也识别独立加粗短标题（`**标题**` / `__标题__`）、圈号短标题（`①`–`⑳`），以及加粗标题后的独立括号注释。支持行尾两个空格或反斜杠表示的 Markdown 换行，并保留这些原始字符。跳过围栏代码、Mermaid、管道表格、引用和长段落枚举；普通正文与标题边界不明确时不凭空创建标题。system 门禁明确禁止以无编号加粗或圈号替代四级序号。

先本地修复整棵标题树：整体提升层级、连续重编号、转换 Markdown 标题、删除与已知输入标题精确匹配的开头重复标题。混排或跳级无法确定时最多请求一次当前模型，只允许返回 `{"headings":[{"line":1,"level":1}]}` 形式的结构建议；全部候选标题必须按原行序覆盖，禁用 SDK 重试。程序从原文构造标题编辑，不接受模型返回替换正文。非标题内容保持原样，后续投标主体称谓归一化仍沿用原有行为。

加粗和圈号只确定候选标题边界，不能据此推断父子层级，统一进入一次模型结构判断，不自动压平成同级。开头重复章节标题比较时忽略 Markdown 标记、完整加粗包裹和换行装饰，章节编号和实际文字必须精确相同。即使正文首标题合规，后续未编号加粗标题或圈号标题也必须处理，不能直接放行。

修复后复核通过才返回成功结果。失败抛出携带原始正文的 `BodyNumberingError`，GUI 保留未保存草稿、不覆盖旧文件，批量任务记为失败后继续。没有可辨认标题时直接保留草稿；取消、超时及无效 JSON 不触发再次请求。流式原始文本可能短暂展示错误编号，最终结果会整段替换为通过复核的正文。
