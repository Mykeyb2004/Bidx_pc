# 标书大纲生成与锁定设计

## 目标

为桌面 GUI 的“新建配置”流程增加大纲准备阶段，让用户既可以指定已有投标大纲，也可以根据评分标准和项目采购需求自动生成标书大纲。生成结果使用当前系统已经支持的 Markdown 多级标题结构，并允许用户在进入扩写前以纯文本形式手动编辑。

大纲一旦确认，系统进入章节扩写阶段。本次 GUI 流程内不再允许继续修改大纲，并通过配置字段 `project.outline_locked: true` 标记该配置已经完成大纲确认。

## 范围

包含：

- 新建配置保存并应用后，根据 `project.outline_locked` 判断是否进入“大纲准备”窗口
- 大纲准备窗口支持读取已有大纲、调用模型生成大纲、手动编辑文本、确认并进入扩写
- 大纲生成固定输出到 H4：`#` / `##` / `###` / `####`
- 大纲生成使用专用角色文件 `./roles/标书架构师.md`
- 大纲生成模型参数优先读取 `.env.local` 中的 `BID_WRITER_OUTLINE_*`，未配置时回退正文扩写 `BID_WRITER_*`
- 确认大纲后保存到 `project.inputs.outline_file`，并把 `project.outline_locked` 写回 `true`
- 主窗口在大纲锁定后加载大纲树并允许章节扩写
- 文档、示例配置和测试夹具同步维护

不包含：

- 大纲版本管理、差异对比或历史回滚
- 已生成章节与新大纲之间的迁移匹配
- 针对单个 H2/H3 的局部重生成
- CLI 大纲生成命令
- 对正文扩写角色文件的改造

## 用户流程

### 新建配置后的大纲准备

用户点击“新建配置...”后，仍使用现有配置编辑器填写项目根目录、投标主体、采购需求文件、评分标准文件、输出目录、正文扩写角色等基础信息。

保存并应用配置后：

1. GUI 加载新配置。
2. 如果 `project.outline_locked` 为 `false`，不直接进入章节扩写树，而是打开“大纲准备”窗口。
3. 用户可以点击“读取已有大纲”，把 `project.inputs.outline_file` 指向的文件内容载入文本框。
4. 用户可以点击“生成大纲”，系统读取当前配置中的采购需求和评分标准，调用大纲生成模型，把生成结果写入文本框。
5. 用户可以在文本框中直接编辑 Markdown 大纲。
6. 用户点击“确认大纲并进入扩写”后，系统保存文本框内容到 `outline_file`，写回 `project.outline_locked: true`，重载配置和大纲树。

### 锁定后的主窗口行为

当 `project.outline_locked` 为 `true` 时，主窗口按现有方式加载大纲树、展示叶子章节、允许生成所选章节和整合标书。

大纲锁定后不自动打开大纲准备窗口。主窗口可以提供“解锁/重新准备大纲...”入口，但必须先提示用户：修改大纲可能导致已生成章节文件、章节状态、事实卡片引用和输出整合顺序不再匹配当前目录。

第一版解锁行为只负责把 `project.outline_locked` 改回 `false` 并重新打开大纲准备窗口，不做章节迁移或缓存重写。

## 配置设计

新增字段位于 `project` 下：

```yaml
project:
  root_dir: "."
  bidder_name: "示例投标主体名称"
  outline_locked: false
  outline_generation:
    role_file: "./roles/标书架构师.md"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./项目要求/项目采购需求.md"
    scoring_criteria_file: "./项目要求/评分标准.md"
  output_dir: "./output"
```

字段语义：

- `project.outline_locked`
  - `false`：大纲仍处于准备阶段，GUI 应先让用户确认大纲。
  - `true`：大纲已固定，GUI 可进入章节扩写阶段。
- `project.outline_generation.role_file`
  - 大纲生成专用角色提示词文件。
  - 默认值为 `./roles/标书架构师.md`，相对配置文件目录解析。
  - 正文扩写仍使用 `writing.role_file`，两者互不替代。

兼容策略：

- 新建配置默认写入 `outline_locked: false`。
- 旧配置如果缺少 `project.outline_locked`，运行时按 `true` 处理，避免老项目被强制带入新建配置流程。
- 配置编辑器规范化保存时保留并展示这两个字段。

## 模型环境变量

新增大纲生成专用环境变量：

```dotenv
BID_WRITER_OUTLINE_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_OUTLINE_API_KEY=your-api-key
BID_WRITER_OUTLINE_MODEL=gpt-5.4
BID_WRITER_OUTLINE_TEMPERATURE=0.3
BID_WRITER_OUTLINE_MAX_TOKENS=6000
BID_WRITER_OUTLINE_TIMEOUT_SECONDS=120
BID_WRITER_OUTLINE_MAX_RETRIES=3
BID_WRITER_OUTLINE_TOP_P=
BID_WRITER_OUTLINE_SEED=
```

读取优先级：

1. `BID_WRITER_OUTLINE_*`
2. 对应正文扩写 `BID_WRITER_*`
3. 代码默认值

默认建议：

- temperature 默认 `0.3`，让目录生成稳定但保留一定组织能力。
- max tokens 默认 `6000`，覆盖中大型评分表的大纲输出。
- timeout 默认 `120` 秒，和正文扩写默认值保持一致。

## 大纲生成服务

新增 `bid_writer/outline_generator.py`，提供 `OutlineGenerator` 服务。

核心职责：

- 读取大纲生成角色文件
- 组装大纲生成 prompt
- 使用 OpenAI 兼容接口调用大纲模型
- 清理模型返回，保留 Markdown 标题行
- 校验标题层级固定到 H4
- 返回可编辑的大纲文本

推荐接口：

```python
@dataclass(frozen=True)
class OutlineGenerationResult:
    outline_text: str
    warnings: list[str]


class OutlineGenerator:
    def __init__(self, config: Config):
        ...

    def generate(self) -> OutlineGenerationResult:
        ...
```

`warnings` 用于提示模型输出被清理、缺少 H4、缺少评分关键词等非阻断问题。阻断性错误直接抛出明确异常，由 GUI 显示。

## Prompt 契约

system prompt：

- 使用 `project.outline_generation.role_file` 对应文件内容。
- 若文件不存在，阻断生成并提示用户检查角色文件路径。

user prompt 包含：

- 投标主体名称
- 项目/标书名称，优先从已有大纲 H1 或配置上下文推断；无法推断时使用“投标文件”
- 采购需求全文
- 评分标准全文
- 输出契约

输出契约：

```text
你只输出 Markdown 标题大纲，不输出正文、说明、前言、代码块或补充解释。
标题层级必须固定到 H4：
# 项目或标书总标题
## 一级章，优先对应评分大项或标书一级章
### 二级节，承接一级章下的核心板块
#### 具体写作单元，作为后续章节扩写的叶子节点
每个 ### 下至少包含 1 个 ####。
不得输出 ##### 或更深层级标题。
标题应保留评分标准中的关键词原词，目录顺序原则上遵循评分标准顺序。
如果评分标准缺失，则依据采购需求提炼目录逻辑。
```

生成后清理规则：

- 去除 Markdown 代码围栏。
- 去除非标题行。
- 保留 `#` 到 `####` 标题。
- 如出现 `#####` 或更深标题，将其降级为 `####`，并记录 warning。
- 如果没有任何 `####`，生成结果视为不可进入扩写，GUI 提示用户修改或重新生成。

## 大纲准备窗口

新增 `bid_writer/outline_prepare_dialog.py`。

窗口组成：

- 顶部状态区：显示当前配置文件、大纲文件路径、锁定状态。
- 操作按钮：
  - “读取已有大纲”
  - “生成大纲”
  - “确认大纲并进入扩写”
  - “取消”
- 主体文本框：可编辑 Markdown 大纲文本。
- 底部校验消息区：显示缺少 H1、缺少 H4、层级跳跃、生成 warning 等。

行为：

- 打开时如果 `outline_file` 存在，默认载入文件内容。
- “读取已有大纲”重新读取当前 `outline_file`。
- “生成大纲”在后台线程调用 `OutlineGenerator.generate()`，成功后替换文本框内容。
- 用户确认前运行大纲校验。
- 校验通过后写入大纲文件，并调用配置更新函数把 `project.outline_locked` 设为 `true`。

校验规则：

- 至少存在 1 个 H1。
- 至少存在 1 个 H4。
- 不允许出现 H5/H6。
- 不允许空标题。
- 每个可扩写叶子应为 H4；如果存在 H2/H3 叶子，提示用户继续细化到 H4。
- 解析后的大纲应至少有 1 个叶子节点。

## GUI 集成

### 新建配置流程

`MainWindow.open_new_config_editor()` 在配置保存并应用后改为：

1. 构造 `BidWriter` 加载新配置。
2. 如果 `config.outline_locked` 为 `False`，打开 `OutlinePrepareDialog`。
3. 用户确认后重载配置并加载大纲。
4. 如果用户取消，保留新配置文件，但不切换主窗口到未准备状态。

### 配置切换流程

`MainWindow._switch_to_config_path()` 增加大纲锁定判断：

- `outline_locked=True`：沿用当前加载大纲逻辑。
- `outline_locked=False`：打开大纲准备窗口；确认后再加载大纲；取消则保持当前配置不变。

这样用户切到一个尚未确认大纲的新配置时，也会先经过准备阶段。

### 解锁入口

在项目菜单中新增“解锁/重新准备大纲...”。入口状态：

- 生成中禁用。
- 当前配置未加载时禁用。
- `outline_locked=false` 时文案可显示为“继续准备大纲...”。

点击后：

1. 如果当前为 `outline_locked=true`，先弹出确认提示。
2. 用户确认后写回 `outline_locked=false`。
3. 打开大纲准备窗口。
4. 用户确认后再次锁定并重载大纲树。

## 错误处理

- 角色文件不存在：生成按钮报错，不清空当前文本框。
- 采购需求和评分标准都为空：阻断生成，提示用户先补充输入文件。
- API Key 缺失：显示大纲模型连接缺失，说明可配置 `BID_WRITER_OUTLINE_API_KEY` 或正文扩写 `BID_WRITER_API_KEY`。
- 模型返回空内容：保留当前文本框，提示重新生成。
- 生成结果缺少 H4：保留结果并提示用户手动细化，确认按钮继续阻断。
- 保存大纲失败：提示具体路径和异常，不修改 `outline_locked`。
- 写回配置失败：提示配置保存失败；已保存的大纲文件保留，但不进入扩写阶段。
- 用户取消准备：不写入锁定状态，不切换当前主窗口到该配置。

## 测试

新增或扩展测试：

- `tests/test_config_schema.py`
  - 新建默认配置包含 `project.outline_locked: false`
  - 新建默认配置包含 `project.outline_generation.role_file: ./roles/标书架构师.md`
  - 旧配置缺少 `outline_locked` 时运行时读取为 `true`
  - `.env.local` 中 `BID_WRITER_OUTLINE_*` 优先于 `BID_WRITER_*`

- `tests/test_outline_generator.py`
  - 生成 prompt 包含采购需求、评分标准和 H4 输出契约
  - 专用角色文件不存在时抛出明确错误
  - 模型返回代码块时可清理出 Markdown 标题
  - 出现 H5 时降级为 H4 并记录 warning
  - 缺少 H4 时校验失败

- `tests/test_outline_prepare_dialog.py`
  - 打开时自动读取已有大纲文件
  - 确认后写入大纲文件
  - 确认后写回 `outline_locked: true`
  - 缺少 H4 时阻断确认

- `tests/test_gui_new_config.py`
  - 新建配置应用后未锁定时打开大纲准备窗口
  - 大纲准备取消时不切换当前主窗口配置
  - 大纲准备确认后切换配置并加载大纲

推荐验证命令：

```bash
uv run pytest tests/test_config_schema.py tests/test_outline_generator.py tests/test_outline_prepare_dialog.py tests/test_gui_new_config.py -q
```

## 文档维护

实现时同步维护：

- `docs/config_schema.md`
- `config.example.yaml`
- `.env.example`
- `README.md` 中 GUI 新建配置说明
- 相关测试夹具中的配置样例

## 验收标准

- 新建配置默认处于大纲未锁定状态。
- 用户可以在大纲准备窗口读取已有大纲。
- 用户可以根据评分标准和采购需求生成 H4 Markdown 大纲。
- 用户可以在文本框中手动编辑生成的大纲。
- 确认后大纲保存到配置指定的 `outline_file`。
- 确认后配置写回 `project.outline_locked: true`。
- 锁定后主窗口加载章节树并允许扩写。
- 锁定后不会自动再打开大纲准备窗口。
- 大纲生成模型优先使用 `BID_WRITER_OUTLINE_*`，未配置时回退正文扩写模型参数。
- 相关配置文档、示例配置和测试通过。
