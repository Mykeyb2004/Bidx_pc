# 转义文件名方案评估

## 目标
- 评估“对非法文件名字符做可逆转义，并直接把转义结果作为输出文件名”的可行性、改动范围、风险与收益。

## 阶段
- [x] 梳理当前保存、预览、状态判断链路
- [x] 识别转义方案的核心约束与边界条件
- [x] 形成改动评估与建议

## 关键决策
- 当前代码不是“文件名直接报错”，而是“文件名被清洗后失去可逆性”。
- 评估对象聚焦在“转义方案”而不是“稳定 id 方案”的实现成本和收益。

## 风险
- 如果只靠文件名反向解析，任何不满足可逆编码规则的旧文件都需要兼容。
- Windows 的保留名、尾部空格/点、路径长度不能只靠 `/` 转义解决。

---

# GUI 配置与树状态优化方案

## 目标
- 启动时默认载入上次使用的配置文件，不再强制先弹启动选择框。
- 配置切换保留在主窗口内，以弹窗形式处理。
- 大纲树首次进入时默认展开所有层级。
- 生成正文、刷新状态、重新加载大纲后，保留用户上次的展开层级，而不是重置视图。

## 阶段
- [x] 梳理当前启动、配置切换与树重绘逻辑
- [x] 确定最小改动的状态持久化方案
- [x] 输出实施方案待确认
- [x] 代码实现与验证

## 关键决策
- “上次配置文件”采用独立 UI 状态文件持久化，不写回业务配置 YAML。
- 启动流程改为：优先读取上次配置；若不存在或失效，再回退 `config.yaml`，仍失败时才弹配置选择框。
- 树展开状态不按节点 ID 记录，而是用运行时的“展开层级”和“手动展开节点路径”恢复，降低配置切换和重载时的脆弱性。

## 风险
- 如果大纲内容变化较大，按“节点路径”恢复部分展开状态时可能有少量节点无法精确匹配。
- 目前切换配置会重建 `BidWriter` 与树数据，恢复视图状态需要放在重绘之后统一执行，不能继续散落在多个入口里。

## 验证结果
- 使用 `config_chatgpt.yaml` 初始化主窗口时，全部父节点默认展开。
- 切换到“展开至一级”后重新加载大纲，展开层级保持为一级。
- 手动收起根节点后再次加载大纲，自定义展开状态能够按路径恢复。

---

# 提示词需求文件注入修复

## 目标
- 让 `config.yaml` 中 `bid_requirements` 和 `scoring_criteria` 当前这种多行块写法，也能被识别为文件路径并读取对应 `.md` 正文。
- 生成正文时，把项目需求和评分标准的实际文本拼进 prompt，而不是把路径字符串发给 LLM。

## 阶段
- [x] 复核当前 `AIWriter.build_prompt()` 与 `Config._get_text_or_file()` 行为
- [x] 修改配置解析，兼容多行块中的路径写法
- [x] 运行时验证 prompt 中已注入文件正文

## 关键决策
- 不要求用户立刻改配置格式，优先兼容当前 `|` 多行块 + 注释 + 引号路径的写法。
- 保持现有 `*_file` 配置能力不变，只增强 inline 文本字段的路径识别能力。

## 风险
- 如果 inline 文本里既有普通说明文字又有一行看起来像路径的内容，需要避免误判成“只读文件”模式。
- 路径识别应以“唯一有效路径行”为前提，不能破坏用户直接内联正文内容的用法。

## 验证结果
- `Config('config.yaml').bid_requirements` 已返回 `项目采购需求.md` 的正文，首行为 `# 项目采购需求`。
- `Config('config.yaml').scoring_criteria` 已返回 `评分标准.md` 的正文，首行为 `# 评分标准`。
- `AIWriter.build_prompt()` 生成的 prompt 中仍保留“招标需求参考”和“评分标准参考”两段，但已不再包含原始路径字符串。

---

# 提示词完整大纲注入修复

## 目标
- 在扩写章节正文时，把当前章节标题、当前章节在整体大纲中的位置、以及完整总大纲内容一并提供给大模型。
- 让模型在扩写时兼顾当前章节边界与全局结构，减少跨章节重复、越界扩写和内容遗漏。

## 阶段
- [x] 复核当前 prompt 中已有的章节标题与路径信息
- [x] 修改 prompt，补充完整总大纲和边界约束
- [x] 运行时验证 prompt 已包含标题、位置、完整大纲三项信息

## 关键决策
- 完整大纲直接使用 `config.get_outline_content()` 读取原始 Markdown 内容，确保与实际大纲文件一致。
- 完整大纲放在单独段落中，并增加“仅用于把握边界与整体结构”的说明，避免模型把整份大纲机械复述到正文里。

## 风险
- 大纲较长时会增加 prompt token 开销。
- 如果大纲文件被外部修改但未重新加载，生成时读取到的是文件当前版本，而不是界面树上已解析的旧版本。

## 验证结果
- 运行时构造 prompt 后，已确认同时包含 `当前标题：...`、`标题层级：...` 和 `## 完整总大纲参考` 三部分。
- `config.get_outline_content()` 读取到的完整 Markdown 大纲原文已经完整出现在 prompt 中。
- 扩写要求中已新增“只撰写当前标题负责的内容边界”“结合完整总大纲把握全局结构，避免与其他章节重复”等约束语句。

---

# Review Findings 修复

## 目标
- 修复 review 中确认的 3 个行为问题：
- `overwrite_existing: false` 时读取逻辑应优先返回最新版本章节，而不是最早版本。
- 相对输出目录应与输入文件路径一样，相对于配置文件目录解析。
- 关闭生成进度窗口不应把仍在运行的生成任务误判为失败，也不应触发 `TclError`。

## 阶段
- [x] 更新 planning 文件并固化修复范围
- [x] 修复 `file_saver` 的版本文件查找与选择规则
- [x] 修复 `config` / `main` 的输出目录路径解析
- [x] 修复 `gui` 中生成窗口的关闭与等待逻辑
- [x] 运行脚本验证 3 个问题已关闭

## 关键决策
- 对同一 `heading_id` 的多版本文件，读取侧按“最新版本优先”选择，而不是按字典序首个文件。
- 输出目录仍保留字符串配置接口，但在配置层统一返回“相对于配置文件目录解析后的绝对路径”，减少调用方分散处理。
- 关闭生成窗口时不取消后台生成；窗口只进入“已隐藏/已关闭 UI”状态，主流程继续等待结果并避免再触碰已销毁的 Tk 控件。

## 风险
- 旧文件名兼容逻辑要同时覆盖标准文件、带 `_N` 后缀的历史文件和 metadata 文件，不能只修一种命名。
- Tk 窗口生命周期修复需要避免引入新的 busy-loop 或无响应问题。

## 验证结果
- 使用 `uv run python` 复现 `overwrite_existing=False` 场景后，`find_existing_filepath()` 现在返回最新生成的 `__id_1` 文件，正文为最新内容。
- 使用临时配置文件验证 `output.directory: ./out` 时，`Config.output_directory` 现在解析到配置文件所在目录下的 `out`。
- 使用最小 Tk 脚本验证：生成开始后立即关闭进度窗口，后台生成仍正常完成，`wait_completion()` 返回结果且不再抛 `TclError`。
- `uv run python -m compileall bid_writer run.py` 通过。

---

# 章节级上下文裁剪与辅助模型配置

## 目标
- 将章节扩写从“完整大纲 + 完整招标需求 + 完整评分标准”的全量注入，优化为“局部大纲 + 命中评分项 + 章节需求 brief”的裁剪注入。
- 保留主生成模型用于正文写作，并为可选的“需求摘要”阶段预留独立辅助模型配置。
- 约束辅助模型的敏感配置仅存放于 `.env.local`，不写入 YAML。
- 将 `[config_公共服务满意度.yaml](/Users/zhangqijin/PycharmProjects/BidX_simple/config_公共服务满意度.yaml)` 作为调试基准配置，通过显式 `--config` 方式验证，不改 GUI 默认启动顺序。

## 阶段
- [x] 复核当前默认配置选择、`config_公共服务满意度.yaml` 现状与单模型配置入口
- [x] 确定章节裁剪采用“规则提取 + 可选轻量模型摘要”的混合策略
- [x] 确定辅助模型敏感信息仅通过 `.env.local` 的 `BID_WRITER_PRUNING_*` 环境变量提供
- [x] 实现 `context_pruning` 配置读取与辅助模型 env 覆写逻辑
- [x] 实现章节级局部大纲、评分项路由、需求 seed/brief 生成链路
- [x] 将 `config_公共服务满意度.yaml` 迁移到新 prompt 字段与裁剪配置结构
- [x] 运行回退、长度和约束命中验证

## 关键决策
- GUI 启动顺序保持现状：显式 `--config` 优先，其次上次成功配置，再回退 `config.yaml`；公共服务满意度配置只作为调试基准，不挤占默认启动位。
- 辅助模型只负责“章节需求 brief”压缩；局部大纲和评分项命中继续走规则逻辑，减少额外模型的不确定性。
- 辅助模型配置采用独立环境变量前缀，如 `BID_WRITER_PRUNING_API_BASE_URL`、`BID_WRITER_PRUNING_API_KEY`，避免与主生成模型共享密钥或地址。
- 若辅助模型缺少必要环境变量、调用失败或返回无效结果，正文生成直接回退到 `rule_only`，不再回退到“全量需求全文”模式。

## 风险
- 评分项路由若只依赖标题关键词，可能在无“对应评分标准”标记的大纲中命中不准，需要设计保底匹配顺序。
- `[config_公共服务满意度.yaml](/Users/zhangqijin/PycharmProjects/BidX_simple/config_公共服务满意度.yaml)` 目前仍保留旧 prompt 字段，迁移时要避免与已实现的 `hard_constraints` 机制冲突。
- 辅助模型与主模型完全分离后，文风和术语口径可能出现偏差，摘要 prompt 需要尽量结构化和去风格化。

## 错误记录
| Error | Attempt | Resolution |
|-------|---------|------------|
| `session-catchup.py` 默认路径不存在 | 1 | 直接读取项目现有 `task_plan.md`、`findings.md`、`progress.md` 接续本轮规划，并记录该路径问题。 |

## 验证结果
- `Config('config_公共服务满意度.yaml')` 已能读取 `context_pruning.enabled`、`requirements_brief.enabled`、`prompt.bidder_name`、`prompt.hard_constraints` 等新字段。
- 未设置 `BID_WRITER_PRUNING_API_BASE_URL` / `BID_WRITER_PRUNING_API_KEY` 时，`pruning_api_is_configured` 为 `False`，可作为后续 `rule_only` 回退条件。
- 设置 `BID_WRITER_PRUNING_*` 环境变量后，`pruning_api_base_url`、`pruning_api_key`、`pruning_model`、`pruning_temperature`、`pruning_max_tokens` 均按预期被环境变量覆盖。
- `uv run python -m compileall bid_writer run.py` 通过。
- `AIWriter.build_prompt()` 在 `context_pruning.enabled=true` 时，已切换为注入局部大纲、命中评分项和需求 seed/brief，而不是完整大纲、完整需求和完整评分表。
- 对 `2.9.2 数据资料保密管理制度` 的 prompt 进行对比：裁剪版长度 `2778`，关闭裁剪后的旧版长度 `9317`，减少 `6539` 个字符。
- 将辅助模型指向不可用地址时，`requirement_brief` 会安静回退为空字符串，主 prompt 继续使用 `命中需求片段`，不影响章节生成流程。

---

# Hybrid Extract 检索摘录模式规划

## 目标
- 在保留现有 `legacy_rule` 规则裁剪链路的前提下，新增 `hybrid_extract` 检索摘录模式，通过配置开关切换。
- 让采购需求与评分标准都支持“准确匹配 + 原文摘录”，避免自由摘要改写。
- 覆盖“评分标准不是 Markdown 表格，而是 Markdown 文字”的场景。
- 保持 prompt 输出面基本不变，继续向模型提供 `评分关注` 与 `需求要点`，为后续提示词优化提供稳定输入合同。
- 将 embedding 连接敏感信息限制在 `.env.local`，不写入 `config_xxx.yaml`。

## 阶段
- [x] 确认业务目标从“需求/评分提炼摘要”转为“基于证据的检索摘录”
- [x] 评估纯规则分块、全文 LLM 提炼、hybrid retrieval 三类方案的复杂度与收益
- [x] 确定配置边界：`.env.local` 仅承载 embedding 连接参数，`config_xxx.yaml` 保留 `embedding.model` 与检索业务参数
- [x] 确定新旧模式并存：`legacy_rule` 保留，`hybrid_extract` 通过配置开关启用
- [x] 确定新模式第一版优先顺序：结构化分段 -> lexical retrieval -> 向量召回 -> rerank/verify
- [x] 在 `Config` 中补齐 `context_pruning.mode`、`scoring.mode`、`requirements.mode`、`retrieval.*`、`embedding.*` 访问器与运行时校验
- [x] 在 `context_pruner.py` 中加入模式分发：`legacy_rule` / `hybrid_extract`
- [x] 新增 `SourceUnit` 统一分段模型，覆盖采购需求、评分表格行、评分文字段落
- [x] 实现非表格评分标准解析，输出统一 `SourceUnit`
- [x] 实现 lexical-only 的 `hybrid_extract v1`，先不依赖 embedding 和 LLM
- [x] 接入 embedding 缓存和向量召回
- [x] 接入可选 rerank/verify，并限定为“返回片段 ID，由程序回填原文”
- [x] 扩展 trace/debug_dump，记录新模式命中与回退信息

## 关键决策
- 不移除现有规则链路；`legacy_rule` 继续可用，降低回归风险。
- `hybrid_extract` 不让模型自由总结采购需求或评分标准，而是以“结构化切分 + 检索 + 原文回填”为核心。
- 评分标准不再假设一定是 Markdown 表格；表格和文字都统一切成 `SourceUnit`。
- 新模式下模型若参与，只负责选 `unit_id` 或做候选校验，不直接生成摘录文本。
- 最终进入 prompt 的内容必须来自源文原文，不允许模型改写后再注入。
- `.env.local` 仅承载 `BID_WRITER_EMBEDDING_API_BASE_URL`、`BID_WRITER_EMBEDDING_API_KEY`；`embedding.model` 留在 `config_xxx.yaml`。
- 第一版实现顺序先偏稳妥：先做 lexical-only，新模式可在不依赖 embedding/LLM 的情况下落地验证。
- prompt 拼接层尽量不改，避免把“检索方式切换”耦合进 prompt 合同。

## 风险
- 非表格评分标准的文本解析如果切分过粗，会影响后续召回精度；切分过细又可能丢失上下文。
- `SourceUnit` 建模若未统一表格/文字/列表的路径信息，后续原文回填和 trace 会变得脆弱。
- 启用向量召回后会引入本地缓存、重建策略和一致性问题，需要明确定义“源文变化后何时失效”。
- rerank/verify 若直接返回文本而不是 ID，会破坏“原文摘录”这一核心约束。
- 新旧模式并存后，调试面需要清晰区分“命中不足”“配置缺失”“主动回退”三种情况。

## 复杂度与收益评估
- 纯规则增强版：中低复杂度，高收益，重点价值在于补齐“非表格评分标准”缺口。
- lexical-only `hybrid_extract`：中等复杂度，中高收益，可先验证结构化分段是否明显优于当前空行切块。
- 加入 embedding 的 vector retrieval：中等复杂度，中高收益，主要提升同义表达和跨段落召回。
- 加入 rerank/verify：中高复杂度，最高收益，但应放到候选集合较小、输出受控的后置阶段。
- 单章时延判断：规则/检索阶段通常可控制在亚秒级；若再加一次辅助模型筛选，通常会额外增加秒级等待。
- token 成本判断：embedding 的一次性成本通常远低于逐章 LLM 校验成本，因此后续成本控制重点在“哪些章节真的需要 rerank/verify”。

## 错误记录
| Error | Attempt | Resolution |
|-------|---------|------------|
| `planning-with-files` 提示的 catchup 脚本默认路径在当前环境不存在 | 2 | 继续沿用项目根目录已有 `task_plan.md`、`findings.md`、`progress.md` 作为持久上下文，并把本轮规划直接写回这些文件。 |

## 当前产出
- 已形成 `hybrid_extract` 的配置边界、数据结构方向、模式切换方式和实施顺序。
- 已明确第一版实现不依赖全文 LLM 提炼，而是优先补强结构化分段与 lexical retrieval。
- 已明确 embedding 敏感连接参数进入 `.env.local`，不进入 `config_xxx.yaml`。
- 已完成 `Phase 1-3` 的代码落地：`Config` 访问器、`SourceUnit`/解析器、`hybrid_extract v1`、文档和示例配置已同步更新。

## 完整实施方案

### 范围
- 本次方案只覆盖“评分标准提炼”“采购需求提炼”“提示词拼接前的章节上下文构建”。
- 不改变章节正文生成的 system/user messages 总体结构。
- 不改变 GUI 主流程，只补充配置和调试可见性。

### 非目标
- 不在本轮把采购需求或评分标准改造成自由摘要工作流。
- 不在本轮引入新的外部存储服务；默认优先使用本地缓存和本地索引。
- 不在本轮重构全文生成流程或输出后处理。

### 目标架构
1. `Config` 提供新旧模式、retrieval、embedding、extraction 的统一配置入口。
2. `ChapterContextPruner` 只做模式编排，不承载全部解析与检索细节。
3. `SourceUnitParser` 负责把采购需求与评分标准切成统一 `SourceUnit`。
4. `HybridRetriever` 负责 lexical / vector / fused retrieval。
5. 可选 `Verifier/Reranker` 只在候选集上工作，输出 `unit_id`，不输出改写后的文本。
6. `AIWriter` 继续消费 `ChapterContext`，保持 prompt 合同稳定。

### 文件改动蓝图
- `bid_writer/config.py`
  - 新增 `context_pruning.mode`、`context_pruning.unavailable_policy`
  - 新增 `scoring.mode`、`scoring.parse_mode`
  - 新增 `requirements.mode`、`requirements.max_quotes`、`requirements.max_quote_chars`
  - 新增 `retrieval.*`、`retrieval.embedding.*`
  - 新增 `.env.local` 中 embedding 连接参数访问器与运行时校验
- `bid_writer/context_pruner.py`
  - 加入 `legacy_rule` / `hybrid_extract` 分发
  - 保持 `ChapterContext` 对 prompt 层兼容
  - 加入新模式命中信息和回退原因
- `bid_writer/source_unit_parser.py`（新增）
  - 统一解析采购需求、评分表格、评分文字段
- `bid_writer/retrieval_models.py`（新增）
  - 定义 `SourceUnit`、`RetrievedUnit`、`ExtractedQuote`
- `bid_writer/hybrid_retriever.py`（新增）
  - 实现 lexical、vector、fuse、select
- `bid_writer/embedding_store.py`（新增，可后置）
  - 管理 embedding 缓存、重建和查询
- `bid_writer/generation_trace.py`
  - 扩展记录 `mode`、候选数、selected ids、fallback reason
- `docs/prompt_contract.md`
  - 第二阶段后更新：明确 `legacy_rule` / `hybrid_extract` 两套上下文构建路径
- `config_公共服务满意度.yaml`
  - 增加新模式配置示例和中文注释

### 分阶段执行

#### Phase 1：配置与模式骨架
- 目标
  - 配置层支持 `legacy_rule` / `hybrid_extract`
  - 缺失 embedding 连接参数时能按策略回退或报错
- 交付
  - `Config` 新访问器
  - `context_pruner.build_context()` 分发骨架
  - `debug_dump/trace` 最小模式字段
- 验收
  - 关闭新模式时行为与当前完全一致
  - 打开新模式但未实现检索时，能稳定回退 `legacy_rule`

#### Phase 2：统一分段模型
- 目标
  - 采购需求和评分标准都产出统一 `SourceUnit`
  - 评分标准支持表格和非表格 Markdown 文字
- 交付
  - `SourceUnit` 数据结构
  - `SourceUnitParser.parse_requirements()`
  - `SourceUnitParser.parse_scoring()` / `parse_scoring_text_units()`
- 验收
  - 对同一输入文档可以稳定输出可追踪的 `unit_id`
  - 非表格评分标准不再“整体失明”

#### Phase 3：lexical-only hybrid_extract v1
- 目标
  - 在不接 embedding、不接 LLM 的情况下跑通新模式
- 交付
  - lexical retrieval
  - fused selection 的占位实现
  - requirements/scoring 原文回填
- 验收
  - `hybrid_extract` 能输出 `评分关注` 与 `需求要点`
  - 样例章节下，命中质量不低于当前 `legacy_rule`

#### Phase 4：embedding + vector retrieval
- 目标
  - 在 lexical 基础上补强同义表达和跨段落召回
- 交付
  - `.env.local` 读取 embedding 连接参数
  - embedding 缓存
  - vector retrieval
  - lexical + vector 融合
- 验收
  - 文档未变化时命中缓存
  - 文档变化时能自动重建或显式重建

#### Phase 5：rerank / verify
- 目标
  - 仅在候选集上做精排或校验，提高最终摘录精度
- 交付
  - 可选 verifier/reranker
  - 输出仅允许 `unit_id`
  - 程序按 `unit_id` 回填 `source_text_exact`
- 验收
  - 无改写文本直接进入 prompt
  - 候选不足或模型失败时可稳定回退上一层

#### Phase 6：验证、文档、样例基线
- 目标
  - 固化手工验证样例、trace 输出和文档合同
- 交付
  - 更新 `docs/prompt_contract.md`
  - 更新示例配置
  - 样例章节前后对比说明
- 验收
  - 可清楚解释任一章节为何命中某些评分项和需求摘录

### 验收口径
- 功能验收
  - `legacy_rule` 行为保持兼容
  - `hybrid_extract` 可单独通过配置启用
  - 非表格评分标准可被解析并命中
  - 最终 prompt 中的摘录必须可回溯到源文
- 质量验收
  - 同一章节重复执行结果基本稳定
  - trace/debug_dump 能解释召回、筛选、回退原因
- 成本验收
  - lexical-only 模式不引入额外模型成本
  - vector 模式仅引入 embedding 成本
  - rerank/verify 为可选开关，默认不强制启用

### 建议默认实施顺序
1. 先完成 Phase 1-3，交付一个可工作的 `hybrid_extract v1`
2. 再进入 Phase 4，补上 embedding
3. 最后做 Phase 5，按效果决定是否默认启用 rerank/verify

## Phase 1-3 验证结果
- `uv run python -m compileall bid_writer run.py` 通过。
- `config_公共服务满意度.yaml` 经 YAML 解析校验通过。
- 在 `config_公共服务满意度.yaml` 下，对 5 个基准章节开启 `hybrid_extract` 后，均成功返回：
  - `retrieval_mode=scoring=hybrid_extract;requirements=hybrid_extract`
  - `scoring_items=4`
  - 非空 `selected_scoring_unit_ids`
  - 非空 `selected_requirement_unit_ids`
- 构造文本型评分标准样例后，`SourceUnitParser.parse_scoring(parse_mode='auto')` 已能正确解析：
  - 带分值的文字评分项
  - 不带分值但有标题+正文的评分段
- 在强行配置 `vector_enabled=true` 的情况下，`hybrid_extract v1` 会按 `fallback_legacy` 自动回退，并给出明确 `fallback_reason`。

## Phase 4-5 验证结果
- 已将 `.env.local` 中的现有主 API 连接参数同步补齐为 `BID_WRITER_EMBEDDING_API_BASE_URL` / `BID_WRITER_EMBEDDING_API_KEY`，未把敏感值写入仓库文件。
- 使用 `text-embedding-3-small` 对真实服务做最小 embedding 请求，返回维度 `1536`，说明 embedding 接口联通。
- 在 `vector_enabled=true`、`rerank=false` 的情况下，`hybrid_extract` 可正常工作，`retrieval_mode` 会显示 `vector=on`，且无回退。
- embedding 缓存目录 `output/_embedding_cache` 已生成缓存文件，说明本地缓存链路正常。
- 在 `BID_WRITER_EMBEDDING_API_BASE_URL` 临时写成 `.../v1/embeddings` 的情况下，代码仍能成功请求，说明 base URL 归一化兼容逻辑生效。
- 在 `rerank_enabled=true`、`llm_verify_enabled=true` 的情况下，候选 verifier 能正常返回已选 `unit_id`，并仍由程序回填原文。

## 项目状态
- `legacy_rule` 已保留并兼容。
- `hybrid_extract` 已完整落地：
  - 统一分段
  - lexical retrieval
  - vector retrieval
  - 可选 rerank/verify
  - trace/debug_dump 可观测性
- 当前剩余工作只属于后续效果调优，不再属于“功能未完成”。
- 收尾核对已完成：
  - verifier 联通性验证完成
  - `__pycache__` 噪音已清理
  - `docs/prompt_contract.md` 与 `config_公共服务满意度.yaml` 已按最终实现校正

## 待确认需求
- [x] `hybrid_extract` 第一轮落地范围只做到 Phase 1-3，先不上 embedding 和 rerank/verify
- [x] `hybrid_extract` 在 `config_公共服务满意度.yaml` 中先默认关闭，待验证通过后再手动开启
- [x] lexical retrieval 第一版接受“不新增第三方依赖”，优先复用现有关键词/相似度逻辑实现
- [x] 后续人工验收以 `config_公共服务满意度.yaml` 下 3-5 个代表章节作为基准样例；章节由当前方案直接指定

## 推荐确认答案
- `hybrid_extract` 第一轮范围：建议只做到 Phase 1-3
- `config_公共服务满意度.yaml` 默认值：建议先保留 `legacy_rule`
- lexical retrieval 依赖策略：建议先不新增依赖
- 验收样例：建议由你指定 3-5 个章节，我据此做对比基线

## 已确认答案
- 第一轮交付范围锁定为 Phase 1-3：只做配置与模式骨架、统一分段模型、lexical-only `hybrid_extract v1`。
- `config_公共服务满意度.yaml` 中的新模式先默认关闭，待样例验证通过后再手动开启。
- lexical retrieval 首版不新增第三方依赖，优先复用现有关键词、标题链、最长公共子串等逻辑。
- 验收样例由当前方案指定，不再等待用户补充章节。

## 基准验收章节
- `2.1.4 验收要求与成果应用理解`
- `2.4.2 1.2万至1.5万个有效样本配置方案`
- `2.9.2 数据资料保密管理制度`
- `2.10.4 全流程真实性追溯机制`
- `3.3.4 合同履约至2026年12月底保障计划`

## Embedding 接入说明
- 用户已提供一组待验证的 embedding 服务连接信息，但出于敏感信息保护，不写入 planning 文件和仓库文件。
- 运行时应从 `.env.local` 读取 `BID_WRITER_EMBEDDING_API_BASE_URL`、`BID_WRITER_EMBEDDING_API_KEY`。
- 若按 OpenAI 兼容客户端接入，`base_url` 更可能应为服务根路径，例如 `/v1`，而不是直接写到 `/v1/embeddings`；真正请求路径由客户端追加 `/embeddings`。
- 若后续联通性测试失败，应优先尝试区分“客户端 base_url”和“HTTP 直连 endpoint”两种写法，再决定是否需要额外适配。
