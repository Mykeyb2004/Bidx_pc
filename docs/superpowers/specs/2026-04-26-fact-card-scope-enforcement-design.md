# 事实卡片作用域与约束属性设计

## 1. 背景

现有事实卡片已支持项目级卡片库、章节默认选择、章节正文提炼与扩写 prompt 注入。但当前设计把 `strong/reference` 放在“章节选择态”上，卡片本体只保存名称、内容、分类、来源等信息。

新的业务口径要求事实卡片自身携带两个互相独立的属性：

- `scope`：全局 / 局部
- `enforcement`：强制 / 参考

其中，全局卡片启用后应自动进入每个章节；强制卡片应要求大模型在扩写时必须保持一致，参考卡片只作为可引用素材。

## 2. 已确认约束

- 不考虑旧配置兼容，允许直接升级 `fact_cards` schema。
- 当 `fact_cards.enabled=true` 时，所有 `active=true` 且 `scope=global` 的卡片默认加入每个章节 prompt。
- `strong/reference` 以卡片本体的 `enforcement` 为准，不再由每个章节单独设置。
- `scope` 与 `enforcement` 是两组独立属性；每组内部互斥且必须二选一。

## 3. 设计目标

- 让卡片本体完整表达“适用范围”和“约束强度”。
- 减少章节选择弹窗中的重复配置，降低批量生成时遗漏全局事实的风险。
- 保留局部卡片的章节级显式选择与默认方案能力。
- 在提炼、编辑、保存、扩写、trace 与文档中统一使用新字段。
- 强制事实冲突继续在调用模型前阻断。

## 4. 非目标

- 不提供旧字段自动迁移。
- 不保留 `chapter_defaults[].usage` 的语义。
- 不新增复杂语义冲突检测，例如不同名称但语义相同的冲突。
- 不改变旧知识库 `knowledge_context` 与事实卡片模式互斥的总体规则。

## 5. 选定方案

采用“卡片本体携带作用域与约束属性”的方案。

每张事实卡片新增：

- `scope: global | local`
- `enforcement: strong | reference`

章节默认方案只负责说明“该章节选了哪些局部卡片”，不再保存用途强弱。

## 6. 数据模型

### 6.1 顶层结构

```yaml
fact_cards:
  enabled: true
  cards:
    - id: fact-card-1
      name: 企业资质
      content: 具备建筑工程施工总承包一级资质。
      category: 资质
      scope: global
      enforcement: strong
      active: true
      source:
        type: manual
        chapter_path: ""
        extraction_instruction: ""
      created_at: "2026-04-26T10:00:00+08:00"
      updated_at: "2026-04-26T10:00:00+08:00"
  chapter_defaults:
    "综合服务项目投标方案 > 项目实施方案 > 质量保障措施":
      - card_id: fact-card-2
```

### 6.2 字段说明

- `scope=global`：项目级全局事实，启用事实卡片模式时自动进入每个章节。
- `scope=local`：局部事实，只在当前章节显式选择或章节默认方案命中时进入 prompt。
- `enforcement=strong`：强制事实，章节正文必须与卡片内容保持一致。
- `enforcement=reference`：参考事实，模型可引用、转述或不使用。
- `chapter_defaults`：只保存局部卡片的默认 `card_id` 列表。

### 6.3 校验规则

- `scope` 只允许 `global` / `local`。
- `enforcement` 只允许 `strong` / `reference`。
- 保存卡片时缺少任一字段都视为无效草稿，应在 GUI 中提示用户补全。
- `chapter_defaults` 中引用不存在、未启用或 `scope=global` 的卡片时，应在保存或读取时剔除。

## 7. 生成解析规则

### 7.1 单章节生成

进入事实卡片模式后，当前章节最终注入卡片为：

1. 全部 `active=true` 且 `scope=global` 的卡片。
2. 本次手动选择的 `active=true` 且 `scope=local` 的卡片。
3. 若没有本次手动选择，则使用该章节 `chapter_defaults` 命中的 `active=true` 且 `scope=local` 的卡片。

同一 `card_id` 去重，全局卡片优先保留。

### 7.2 批量生成

批量生成不提供整批共享临时选择，最终注入卡片为：

1. 全部 `active=true` 且 `scope=global` 的卡片。
2. 当前章节 `chapter_defaults` 命中的 `active=true` 且 `scope=local` 的卡片。

### 7.3 冲突阻断

只检测进入本次 prompt 的 `enforcement=strong` 卡片。若同名强制卡片内容不一致，生成前阻断并提示冲突卡片。

## 8. Prompt 结构

事实卡片 prompt section 保持 `## 事实卡片参考`，内部按约束强度分组：

```text
## 事实卡片参考
以下事实卡片已进入当前章节扩写上下文；“强制事实”必须保持一致，“参考事实”可按章节需要择优吸收。

### 强制事实
- [全局] 企业资质：具备建筑工程施工总承包一级资质。
- [局部] 服务承诺：本章节承诺 2 小时内响应。

### 参考事实
- [全局] 同类案例：近三年完成 5 个同类项目。
```

Prompt 中显式标注 `[全局]` / `[局部]`，帮助模型理解适用范围，但最终强弱行为由分组决定。

## 9. 提炼工作台

章节正文提炼时，模型必须返回：

```json
[
  {
    "name": "企业资质",
    "content": "具备建筑工程施工总承包一级资质。",
    "category": "资质",
    "scope": "global",
    "enforcement": "strong"
  }
]
```

提炼提示词应说明判定口径：

- 主体信息、资质能力、统一承诺、全项目通用要求优先标记为 `global`。
- 只适用于当前章节主题、局部措施、局部流程的内容优先标记为 `local`。
- 必须全文一致、不能被改写成相反含义的信息标记为 `strong`。
- 仅供模型借鉴、可按章节选择性吸收的信息标记为 `reference`。

草稿编辑器必须允许用户修改 `scope` 与 `enforcement` 后再保存。

## 10. GUI 调整

### 10.1 卡片草稿编辑器

每张卡片新增两个下拉框：

- 作用域：全局 / 局部
- 约束：强制 / 参考

保存时校验两个字段必须有值。

### 10.2 事实卡片库

当前卡片列表新增两列：

- 作用域
- 约束

下方编辑区同步支持修改这两个字段。

### 10.3 生成参数弹窗

单章节生成时：

- 全局卡片不再出现在“可选局部卡片”中，改为显示只读摘要，例如“本次将自动加入 N 张全局卡片”。
- 局部卡片仍可勾选。
- 局部卡片不再提供 `strong/reference` 用途下拉框。

批量生成时：

- 提示文案改为“本次会自动加入全局卡片，并读取各章节已保存的局部默认卡片方案”。

## 11. 配置与文档影响

需要同步维护：

- `config.example.yaml`
- `docs/config_schema.md`
- `docs/prompt_contract.md`
- `docs/chapter_expansion_mechanism.md`
- 相关测试夹具中的 `fact_cards` 示例

这些文档应明确 `usage` 已从章节默认方案中移除，强制/参考由卡片本体 `enforcement` 决定。

## 12. 测试策略

需要覆盖以下行为：

- 读取卡片时 `scope` / `enforcement` 必填且取值合法。
- 保存手工卡片、提炼卡片、卡片库编辑时保留新字段。
- 全局卡片在单章节与批量生成中自动注入。
- 局部卡片只在手动选择或章节默认方案命中时注入。
- `chapter_defaults` 不保存 `usage`，且剔除全局卡片引用。
- prompt 按 `enforcement` 分组，并标注 `[全局]` / `[局部]`。
- 强制卡片冲突检测基于 `enforcement=strong`。
- 提炼解析能读取 `scope` / `enforcement`，缺字段时不保存该草稿。
- GUI 草稿编辑器与卡片库编辑器能读写两个新属性。

## 13. 实施顺序建议

1. 更新领域模型与纯函数测试。
2. 更新 YAML 存储与章节默认方案解析。
3. 更新 prompt 拼装与冲突检测。
4. 更新提炼 prompt、解析和诊断。
5. 更新 GUI 草稿编辑器、卡片库和生成参数弹窗。
6. 更新配置示例、文档和测试夹具。

