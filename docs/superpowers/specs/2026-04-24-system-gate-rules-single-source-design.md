# System Gate Rules Single-Source Design

## 1. 背景

当前 `system prompt` 的“最高优先级输出强约束”来自三处拼装：

1. `AIWriter` 内建规则文案
2. 配置中的 `writing.hard_constraints`
3. 配置开关推导出的规则（如禁 Markdown 标题、禁不必要英文）

这会带来三个问题：

- 审核提示词时，很难一眼看到最终门禁全文
- 不同来源容易语义重复，但代码只做同文案去重，不能做语义去重
- 某些规则（例如投标主体名称）虽然值来自配置，但规则文案模板仍散落在代码里

本次改动目标是把 `system prompt` 的门禁文案收敛为单一规则清单，并保持实现简单。

## 2. 目标

- 将 `system prompt` 的门禁文案集中到一个固定文档文件中维护
- `system prompt` 继续保留统一外壳：
  - `【最高优先级输出强约束】`
  - `以下规则优先级高于其他风格建议、默认模板和惯常表达；如有冲突，必须以本节规则为准。`
- 投标主体名称不在代码中硬编码，继续从配置的 `project.bidder_name` 读取
- 角色正文与门禁清单分离存放，二者都放在仓库根目录下的 `roles/`
- 门禁文件缺失时直接报错，不做静默回退
- 不为了这次重构引入复杂模板系统、复杂配置链路或多层 fallback

## 3. 非目标

- 不改 user prompt 的 A+ 拆分方案
- 不把 postprocess/输出巡检逻辑一起改造成“文档驱动”
- 不新增 `writing.system_gate_rules_file` 一类配置字段
- 不在这次改动里重做配置编辑器 UI 的交互形式

## 4. 选定方案

采用“全局固定门禁文件”方案。

### 4.1 文件布局

- 角色文件目录从 `docs/roles/` 挪到仓库根目录同级的 `roles/`
- 角色正文文件示例：`roles/通用投标角色.md`
- 全局固定门禁文件：`roles/system_gate_rules.md`

### 4.2 配置约定

- `writing.role_file` 继续保留，但路径改为类似 `roles/通用投标角色.md`
- 不新增新的门禁文件配置项
- `system prompt` 的门禁文案始终从固定路径 `roles/system_gate_rules.md` 读取

### 4.3 System Prompt 组装方式

`system prompt` 只保留两段内容：

1. `Config.role` 读出的角色正文
2. 固定门禁外壳 + `roles/system_gate_rules.md` 的原始正文

也就是说，门禁文件中的规则内容不再由代码逐条拼装，而是按文件原文读取后直接插入。

最终结构保持为：

```text
{role}

【最高优先级输出强约束】
以下规则优先级高于其他风格建议、默认模板和惯常表达；如有冲突，必须以本节规则为准。
{gate_rules_file_content}
```

## 5. 门禁文件格式

为保持实现简单，本次不引入 YAML、JSON 或复杂 DSL。

`roles/system_gate_rules.md` 直接存放“最终想进入 prompt 的规则正文”，推荐使用项目符号列表，例如：

```text
- 投标主体统一使用“{bidder_name}”表述；除非用户明确要求，不要替换为其他公司名称、简称或第一人称主体。
- 严禁使用Markdown标题符号（#）。
- 除专有名词或用户明确要求外，禁止输出不必要的英文、英文缩写或中英对照。
- 默认使用正式层级序号组织正文；除非用户明确要求只写单段摘要，否则至少出现一个正式层级序号“一、”。
```

关键约定：

- 文件内容按原样读取，不做逐条解析、不做去重、不做语义合并
- 规则是否重复，由维护门禁文件的人自行保证
- 代码只负责读取、轻量替换、拼接

这样可以让审计者直接打开一个文件就看到完整门禁内容。

## 6. 占位符策略

为了满足“投标主体名称不在代码中硬编码”的要求，同时避免复杂模板引擎，本次只支持一个轻量占位符：

- `{bidder_name}`

替换规则：

- 如果门禁文件中出现 `{bidder_name}`，则用 `project.bidder_name` 的值做直接字符串替换
- 不引入通用 `.format()` 模板系统
- 不支持任意占位符表达式

失败策略：

- 如果门禁文件中出现 `{bidder_name}`，但配置里没有有效的 `bidder_name`，直接报错

这样既满足配置驱动，也把运行时复杂度控制在最低。

## 7. 失败策略

以下情况直接报错，不做回退：

- `roles/system_gate_rules.md` 不存在
- `roles/system_gate_rules.md` 为空或只包含空白
- 门禁文件使用了 `{bidder_name}`，但配置未提供有效投标主体名称

不再保留“缺文件时退回代码内建规则”的兜底逻辑。

## 8. 配置字段影响范围

本次改动后，以下字段不再参与 `system prompt` 门禁文案生成：

- `writing.hard_constraints`
- `prompt.hard_constraints`
- `writing.allow_markdown_headings`
- `prompt.allow_markdown_headings`
- `writing.allow_english_terms`
- `prompt.allow_english_terms`

说明：

- 它们可以在本次改动里继续保留解析与配置兼容，避免引发过大连锁改动
- 但 `build_system_prompt()` 不再依赖这些字段去自动生成门禁文本
- 门禁文案的唯一文本来源变为 `roles/system_gate_rules.md`

## 9. 与现有输出巡检逻辑的边界

当前代码中仍有部分输出巡检逻辑依赖配置字段，例如 Markdown 标题检测。

本次设计不把这些巡检逻辑也改造成文档驱动，原因是：

- 用户当前诉求是“门禁提示词单一规则清单”
- 巡检逻辑属于另一个层面的行为约束，不必在这次一起重构
- 一次性同时改 prompt 来源与输出巡检来源，会显著扩大改动面

因此本次边界明确为：

- **system prompt 门禁文案**：改为单一文档来源
- **postprocess/巡检逻辑**：本次尽量不动，只做必要兼容

## 10. 需要同步更新的内容

实现时需要同步更新以下内容，避免文档和配置漂移：

- `config_统计台账.yaml`
  - `writing.role_file` 路径改到 `roles/通用投标角色.md`
  - 删除或清空当前示例中的 `writing.hard_constraints`
- `config.example.yaml`
  - 同步体现新的角色文件路径与门禁维护方式
- `docs/config_schema.md`
  - 更新 `writing.role_file` 的推荐位置说明
  - 说明 `roles/system_gate_rules.md` 是全局固定门禁文件
  - 标明 `hard_constraints` / `allow_markdown_headings` / `allow_english_terms` 不再作为 system prompt 门禁文本来源
- `docs/prompt_contract.md`
  - 更新 `System Prompt` 来源描述
  - 删除 `_build_hard_constraints()` 逐条生成门禁的旧说法

## 11. 预期代码改动边界

本次实现应尽量收敛在以下职责内：

- `bid_writer/config.py`
  - 保持 `role_file` 读取逻辑可用
  - 增加“固定全局门禁文件路径”的读取辅助能力，或在 `AIWriter` 中直接读取固定文件
- `bid_writer/ai_writer.py`
  - 精简 `build_system_prompt()` 的门禁来源
  - 删除或停用 `_build_hard_constraints()` 这类拼装式门禁文案生成逻辑
  - 改为读取 `roles/system_gate_rules.md` 原文并做 `{bidder_name}` 轻量替换
- 角色/门禁文件
  - 新建 `roles/system_gate_rules.md`
  - 将 `docs/roles/通用投标角色.md` 移到 `roles/通用投标角色.md`

## 12. 验证重点

至少需要覆盖以下验证点：

1. `build_system_prompt()` 能成功读取 `roles/system_gate_rules.md`
2. `system prompt` 中的门禁正文与门禁文件原文一致
3. `{bidder_name}` 能正确替换
4. 缺少门禁文件时直接报错
5. `writing.hard_constraints` 不再进入 `system prompt`
6. `allow_markdown_headings` / `allow_english_terms` 不再影响 `system prompt` 门禁文案
7. 现有 user prompt A+ 拆分不受影响

## 13. 设计结论

本次采用“固定全局门禁文件 + 轻量占位符替换 + fail fast”的极简方案。

这样可以同时满足四个核心目标：

- 审核时只看一个门禁文件
- 角色正文与门禁规则职责分离
- 投标主体名称仍由配置驱动
- 不引入新的复杂配置项或模板引擎
