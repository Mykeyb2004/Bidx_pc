# Findings

## CS 模式改造讨论基线发现
- `Config._load_local_env()` 当前会按配置文件目录读取 `.env` / `.env.local`，随后大量模型连接参数只从环境变量读取；这是 CS 化时最直接的替换点，可以改为 `ServerConfigProvider` 从服务端获取账号有效配置。
- `Config.api_base_url` / `api_key` / `model` / `temperature` / `max_tokens` / `timeout` / `retries` 目前分别暴露给正文生成、大纲生成、章节写作计划、辅助校验、embedding 等模块；若要避免客户端持有真实模型 key，应统一抽象模型网关客户端。
- `AIWriter.__init__()` 当前直接创建 OpenAI 客户端，`prepare_generation()` 在本地组装 messages，`expand_raw()` 直接调用 `chat.completions.create()`；这是“本地组 prompt，服务端代理调用”的核心切入点。
- `OutlineGenerator`、`ChapterWritingPlanGenerator`、`LLMVerifier`、`H2ProjectBackgroundGenerator._compute_summary()`、`FactCardExtractor`、`ChapterFactExtractor`、`EmbeddingStore` 都存在模型或 embedding 调用，不能只改 `AIWriter`。
- `roles/system_gate_rules.md` 当前固定从配置文件目录下读取，且 `AIWriter.build_system_prompt()` 会把它与角色 prompt 拼成 system prompt；迁到数据库后，需要保证服务端规则版本可审计，且客户端本地缓存缺失时 fail fast。
- `GenerationTraceSession` 当前会把 system prompt、user prompt、request options、生成输出写到本地 trace；CS 模式下建议继续本地保存完整 trace，服务端只保存脱敏摘要、账号、模型、token、规则版本和错误信息。
- 当前生成后处理 `_finalize_generated_content()` 只做投标主体称谓规范化和轻量问题检测，不依赖服务端，适合留在本地。
- `FileSaver`、输出合并、事实卡片库、本地正文读取都围绕本地文件系统构建；符合“生成文本尽量本地处理”的原则，不建议首版迁移。

## 知识库方案阶段一规划相关发现
- `docs/knowledge_base_plan.md` 现已统一 `chapter_facts` 缓存为单文件 `.{bid_writer}/chapter_facts.json`，并补充了避免落地分叉的实现约束。
- 当前真正进入模型的 user prompt 是由 `AIWriter.build_prompt_result()` 中的 `_append_prompt_section(...)` 组装的；仅修改 `_PROMPT_CONTRACT_BLOCKS` 不会自动把 `knowledge_context` 注入到真实 prompt。
- `AIWriter._build_prompt_contract_blocks()` 还维护了一套独立的 `block_specs` 映射，因此 `knowledge_context` 需要同时补 section 注入和 block spec，trace 才能与真实 prompt 对齐。
- `AIWriter.build_prompt_result()` 目前有 `pruned_context is None` 和 `pruned_context is not None` 两条主路径；知识注入必须覆盖两条路径，且插入位置要与文档约定一致，放在 `project_background` 之后、`requirement_context` 之前。
- `Config` 已经具备可复用的路径与列表读取基础能力：`_get_string_list()`、`_resolve_path()`、`_resolve_project_path()`，适合直接承接 `knowledge_files` / `knowledge_directory` 的阶段一实现。
- 仓库约定要求：只要配置结构相关字段发生变化，就要同步维护 `docs/config_schema.md`、`config.example.yaml`、相关 `config_*.yaml` 与测试夹具，不能只改代码。
- 项目根目录已经长期使用 `task_plan.md`、`findings.md`、`progress.md` 作为持久 planning 文件，本轮应在现有文件上续接，而不是覆盖为通用模板。
- 当前阶段一目标只涉及“用户手写知识 -> prompt”的新链路，不应把既有“章节依赖摘要”或未来“章节事实提炼”混入本轮最小实现范围。

## Resources
- 方案文档：`docs/knowledge_base_plan.md`
- Prompt 接入点：`bid_writer/ai_writer.py`
- 配置接入点：`bid_writer/config.py`
- 运行时服务组装：`bid_writer/main.py`
- 后续 GUI 触发相关参考：`bid_writer/gui.py`

---

## config 项目文件结构评估补充发现
- README 已明确推荐把输入资源写在 `inputs` 下，但 `Config` 仍同时兼容根级 `outline_file` / `bid_requirements` / `scoring_criteria`，形成双轨写法。
- 当前公共服务满意度项目配置仍使用根级旧写法，而且 `bid_requirements` / `scoring_criteria` / `outline_file` 采用“多行文本字段里只放一个路径”的兼容形态，可读性较差。
- `Config._resolve_path()` 统一按“配置文件所在目录”解析相对路径；由于仓库内配置要引用仓库外项目资料，真实项目配置被迫写成长绝对路径。
- 四份公共服务满意度配置本质上是同一项目的不同运行剖面；对 69 个叶子配置项做扁平比较后，`full_context` 版只比基准版少改 2 项，`hybrid_extract` 版只改 4 项，`hybrid_extract_full` 版只改 7 项，重复度很高。
- `context_pruning.requirements_brief.fallback` 当前仍未接入主流程；用户可配置，但运行时不会按它决定回退行为。
- 旧局部大纲视图配置已废弃并从当前配置链路移除。
- `context_pruning.retrieval.rerank_enabled` 与 `context_pruning.extraction.llm_verify_enabled` 会共同决定是否进入同一条候选校验链路，概念上容易让人误以为是两个独立能力。
- `Config` 通过大量逐字段 property + 默认回退支撑兼容层，非法枚举和值大多会静默回退到默认值，缺少“显式 schema 校验 + 未知字段告警”。
- README、YAML 内联注释和代码默认值共同承担“配置说明”职责，已经出现“文档说明”和“实际默认行为”分散的问题。

## 新 schema 设计决议
- canonical schema 采用 `project / writing / processing / models / runtime` 五层，而不是继续把配置结构贴着实现模块命名。
- `processing` 已与用户确认收敛为 3 条业务路径：
  - `full_context`：采购需求和评分标准都不做章节级处理
  - `legacy_rule`：两者都走现有规则链路
  - `hybrid_extract`：两者都走检索摘录链路
- 新 schema 中不再推荐、也不再显式暴露“评分标准走一条链路、采购需求走另一条链路”的项目级混搭配置。
- 旧 schema 的 mixed-mode 兼容仍需要保留一层内部兜底，否则存在潜在回归风险；但 canonical schema 不把它作为正式能力继续推广。
- `processing` 顶层应先表达“当前项目跑哪条链路”，再在链路内部挂各自参数，而不是继续平铺一堆开关组合。
- `context_pruning.retrieval.rerank_enabled` 与 `context_pruning.extraction.llm_verify_enabled` 在新 schema 中更适合收敛为单一的 `verify_enabled` 概念。
- `role` 在旧 schema 中承担了领域背景、写作规范和风格约束的混合职责；本轮实现先迁移到 `writing.role` / `writing.role_file`，不强行再拆得更细。
- `project.root_dir` 是必要补充：只有引入项目根目录，项目输入资源和输出目录才不必继续写成长绝对路径。

## 本轮实现后补充发现
- 新 schema 下，`project.inputs.*` 与 `project.output_dir` 现在相对 `project.root_dir` 解析，已经能显著缩短真实项目配置里的长绝对路径。
- `runtime.trace.directory` 与 `models.embedding.cache_dir` 最终保留为“相对配置文件目录”解析，更符合仓库内 `/log` 与工具运行缓存的使用边界。
- `Config.processing_path` 已成为新的主链路入口；新 schema 下业务代码默认要求评分标准与采购需求跟随同一条处理路径。
- 对旧 schema 的 mixed-mode，`Config.processing_path` 会返回 `mixed`，`ChapterContextPruner` 则回退到旧的分开路由逻辑，避免回归。
- 现有业务代码主体基本不需要大改；只要 `Config` 兼容输出旧 accessor，GUI、AIWriter、trace、embedding、verifier 都能平滑承接新 schema。
- 将公共服务满意度角色设定抽出为 `docs/roles/公共服务满意度_role.md` 后，4 份项目配置已经不再重复粘贴整段角色 prompt。
- `docs/config_schema.md` 现在已补充“维护约定”和“变更检查清单”，可以作为后续配置变更的单一说明入口。
- 仓库约定也已补充到 `AGENTS.md`：配置结构相关变更时，需要同步维护 `docs/config_schema.md`、`config.example.yaml`、相关 `config_*.yaml` 和测试夹具。

## 当前实现
- `bid_writer/file_saver.py` 中 `sanitize_filename()` 采用替换式清洗，不是可逆编码。
- `bid_writer/gui.py` 预览时直接按清洗后的标题拼文件路径。
- `bid_writer/gui_adapter.py` 扫描输出目录时从文件名反推标题，再做一次清洗比对。

## 转义方案的关键事实
- 如果采用可逆转义，文件名本身可以承载原始标题语义。
- 但必须统一保存、预览、状态刷新三处的编码/解码规则。
- 只转义 `/` 不够，Windows 还需要处理保留名、尾部空格/点、控制字符等。

## GUI 配置与树状态相关发现
- `run_gui()` 当前在 `config_path is None` 时直接调用 `choose_config_file()`，因此启动时会先阻塞在配置选择框。
- `load_outline()` 每次都会调用 `_render_outline_tree()` 全量重绘树，当前没有保存和恢复展开状态。
- 切换配置 `select_and_switch_config()` 会直接替换 `BidWriter` 和 `GUIAdapter`，然后重绘树，因此如果不显式恢复状态，视图一定会被重置。
- 当前已有 “展开至一级/二级/三级/全部收缩” 操作，但没有“默认展开全部”入口，也没有“上次展开层级”的状态字段。
- 最小实现路径是新增一个 GUI 状态存储文件记录 `last_config_path`，并在运行时维护树的 `expanded_mode`/`expanded_paths`，避免污染业务配置文件。

## GUI 优化实施后的确认
- 启动配置来源现在变为：命令行 `-c` 优先，其次 `.bid_writer_gui_state.json` 中的 `last_config_path`，最后回退到 `config.yaml`。
- 配置文件选择仅保留在主窗口内弹窗，不再作为默认启动前置步骤。
- 树视图新增了运行时 `TreeViewState`，支持 `all / level_1 / level_2 / level_3 / collapsed / custom` 六种状态。
- 自定义展开状态通过 `HeadingNode.full_path` 恢复，不依赖 Tk 节点 ID，因此重绘后仍可恢复。

## 提示词需求文件注入相关发现
- `AIWriter.expand()` 把 `self.config.role` 放进 `system` 消息，把 `build_prompt()` 结果放进 `user` 消息。
- `AIWriter.build_prompt()` 确实会把 `self.config.bid_requirements` 和 `self.config.scoring_criteria` 拼到 user prompt 中。
- 当前问题不在 prompt 拼接位置，而在 `Config._get_text_or_file()` 对 inline 值的识别规则。
- 现有兼容逻辑只会把“单行短字符串”当作路径去读文件；对于 YAML `|` 多行块中的 `# 注释 + 引号路径`，会直接原样返回。
- 运行时验证表明，prompt 中目前出现的是 `"/Users/zhangqijin/PycharmProjects/BidX_simple/项目要求/项目采购需求.md"` 这类路径文本，而不是目标 Markdown 文件正文。
- 修复方向应当是：从 inline 多行文本里提取唯一有效路径行，成功读取文件后优先返回文件内容；否则仍保留原始 inline 文本。

## 提示词需求文件注入修复后的确认
- 新增了 inline 路径候选提取逻辑：忽略空行和 `#` 注释行，去掉成对引号，仅当剩余为唯一候选且确实指向现有文件时才按路径读取。
- 当前 `config.yaml` 中的 `bid_requirements: |` 和 `scoring_criteria: |` 写法已按预期生效，不需要强制改成 `*_file` 字段。
- 运行时 `Config('config.yaml')` 现在返回的是两个 Markdown 文件正文，`AIWriter.build_prompt()` 中对应段落也已经注入正文内容。

## 提示词完整大纲上下文相关发现
- 当前 prompt 已包含 `当前标题：{heading.title}` 和 `标题层级：{heading.full_path}`，因此“当前扩写章节标题”和“当前章节在大纲中的父级路径位置”是有的。
- 当前 prompt 未包含 `config.get_outline_content()` 的结果，因此模型拿不到完整总大纲原文。
- `BidWriter.load_outline()` 会读取并解析大纲文件，但解析结果只用于 GUI/树结构，未传入 `AIWriter.build_prompt()`。
- 如果要满足“既不超出本章节边界，又具备整体视野”，最直接的实现是在 prompt 中追加“完整总大纲参考”段落，并显式约束模型只撰写当前章节负责范围。

## 提示词完整大纲上下文修复后的确认
- `AIWriter.build_prompt()` 现在会先读取 `config.get_outline_content()`，并在 prompt 中追加“完整总大纲参考”段落。
- 完整大纲以 fenced code block 的形式注入 prompt，能保留原始 Markdown 结构，减少与其他提示段落混淆。
- 扩写要求中新增了两条边界约束：只写当前标题负责范围；结合完整总大纲避免重复、遗漏和越级展开。
- 运行时验证已确认 prompt 同时包含当前标题、标题层级路径、完整总大纲原文三项信息。

## Review 修复相关发现
- `find_existing_filepath()` 当前先查标准文件、再查首个匹配的 ID/legacy 文件，因此在存在 `__id_1`、`__id_2` 等版本文件时会稳定返回旧版本。
- `save()` 在 `overwrite_existing=False` 时确实会持续生成新文件，说明问题出在“读取侧不认识最新版本”，不是保存覆盖失败。
- `Config.output_directory` 与 `outline_file`、`bid_requirements_file` 使用了不同的路径规则；前者保留原始相对字符串，后者按配置文件目录解析。
- `GenerationWindow.wait_completion()` 直接循环调用 `self.window.update()`；如果用户先把窗口销毁，后续任意一次 `update()` 或 `destroy()` 都可能抛 `TclError`。
- 生成进度窗当前没有注册 `WM_DELETE_WINDOW` 行为，也没有“窗口已关闭但任务仍在运行”的状态字段。

## Review 修复后的确认
- `file_saver.py` 新增了基于修改时间和版本后缀的候选文件选择逻辑，读取侧现在会返回最近一次生成的章节文件。
- `find_existing_filepath()` 不再对标准文件名做早返回，而是把标准文件、带稳定 ID 的版本文件、legacy 文件统一纳入候选后再选最新版本。
- `Config.output_directory` 现在与输入文件路径保持一致，统一通过 `_resolve_path()` 相对于配置文件目录解析。
- `GenerationWindow` 把队列轮询挂到父窗口上，而不是进度窗自身；即使进度窗已被用户关闭，后台任务状态仍会继续被消费。
- `GenerationWindow.close()` 现在是幂等的，重复关闭或关闭已销毁窗口都不会再触发 Tk 异常。

## 章节级上下文裁剪规划相关发现
- 当前 GUI 默认启动顺序来自 `get_startup_config_candidates()`：显式配置优先，其次上次成功配置，再次是 `config.yaml`，最后才是其他 `config*.yaml`；没有“固定调试基准配置”的概念。
- 当前代码只有一套模型配置入口，即 `Config.api_*` 和 `AIWriter` 单客户端；不存在辅助摘要模型的第二套配置通道。
- `[config_公共服务满意度.yaml](/Users/zhangqijin/PycharmProjects/BidX_simple/config_公共服务满意度.yaml)` 仍是旧风格 prompt：`output_format: "Markdown格式"`、`first_line_template: "#### {title}"`，并把强约束写在 `role` 中，尚未迁移到 `prompt.bidder_name` / `prompt.hard_constraints`。
- 对“章节级上下文裁剪”，最稳妥的首版是混合策略：局部大纲和评分项命中用规则提取，采购需求再按章节生成结构化 brief。
- 用户确认辅助模型的敏感项 `base_url`、`api_key` 必须放 `.env.local`，不进入 YAML。
- 基于现有环境变量命名规则，辅助模型宜采用独立前缀，如 `BID_WRITER_PRUNING_API_BASE_URL`、`BID_WRITER_PRUNING_API_KEY`，与主生成模型分离。
- 为避免隐式耦合，若辅助模型 env 缺失，不应自动偷用主模型密钥；应直接回退到 `rule_only`。
- `planning-with-files` 技能说明中的默认 catchup 脚本路径在当前环境不存在，因此本轮规划是基于项目内已有 planning 文件恢复上下文。

## 章节级上下文裁剪配置接口实现后的确认
- `Config` 已新增 `context_pruning` 相关属性，覆盖开关、调试输出、局部大纲、评分路由、需求摘要和辅助模型参数读取。
- 辅助模型的 `base_url` 与 `api_key` 已按要求改为仅从环境变量 `BID_WRITER_PRUNING_API_BASE_URL` / `BID_WRITER_PRUNING_API_KEY` 读取，不再依赖 YAML。
- 辅助模型的非敏感参数如 `model`、`temperature`、`max_tokens`、`timeout_seconds`、`max_retries` 支持 YAML 默认值，并允许被 `BID_WRITER_PRUNING_*` 环境变量覆盖。
- `Config.pruning_api_is_configured` 已提供后续运行时判断条件，用于决定是否启用需求摘要模型。
- `[config_公共服务满意度.yaml](/Users/zhangqijin/PycharmProjects/BidX_simple/config_公共服务满意度.yaml)` 已迁移到新 prompt 字段：`output_format: 纯正文`、`first_line_template: ""`、`allow_markdown_headings: false`、`bidder_name`、`hard_constraints`、`context_pruning`。
- `.env.example` 和 `README.md` 已补充 `BID_WRITER_PRUNING_*` 的使用说明，明确敏感配置应进入 `.env.local`。

## 章节级上下文裁剪链路实现后的确认
- 新增 `bid_writer/context_pruner.py`，负责局部大纲构建、评分表 Markdown 解析、评分项路由、采购需求 seed 提取，以及可选的需求 brief 生成。
- 评分项路由优先吃大纲祖先节点中的 `（响应：xxx）` / `（对应评分标准：xxx）` 标签，再结合标题链和最长公共子串匹配，对同一子项下的多行评分标准做二次排序。
- 采购需求 seed 不再简单返回整份需求全文；当前实现会按段落打分，并将“短标题块 + 下一段正文”合并，避免只抽到 `1.2调查方法` 这类无信息量的短标题。
- `AIWriter.build_prompt()` 在启用裁剪时不再注入 `## 完整总大纲参考`、`## 招标需求参考`、`## 评分标准参考`，而是切换为 `## 局部大纲参考`、`## 命中评分项参考`、`## 命中需求片段` / `## 需求提炼 Brief`。
- 对公共服务满意度项目的 `2.9.2 数据资料保密管理制度`，评分路由已能把“保密工作制度”“数据真实性保障措施”等评分行排到前面。
- 在未配置或调用失败的辅助模型场景下，`requirement_brief` 会返回空串，主 prompt 自动回退到规则提取的 `requirement_seed`，不会抛异常或阻塞生成。
- `context_pruning.debug_dump=true` 时，`AIWriter.build_prompt()` 会把当前章节的局部大纲、命中评分项、需求 seed、需求 brief 和 prompt 长度统计写入输出目录下的 `_context_pruning_debug/*.md` sidecar 文件。
- 为了提升需求 seed 的可解释性，关键词匹配已增加标题/评分语句的变体提取和 generic suffix 剥离，例如可从“数据资料保密管理制度”派生出“数据资料保密”等更短关键词。

## Hybrid Extract 规划相关发现
- 当前 `context_pruner.py` 中评分标准路由仍强依赖 Markdown 表格解析；如果 `scoring_criteria` 是 Markdown 文字段落，现有 `评分关注` 基本不会命中。
- 当前采购需求和评分标准虽然都在做“原文摘录”方向的尝试，但前置召回仍然是规则分块 + 关键词打分，因此核心瓶颈在召回而不是摘录动作本身。
- 对“准确匹配 + 原文摘抄”场景，更稳的工程路线是 `结构化切分 -> lexical/vector 检索 -> 候选重排 -> 程序回填原文`，而不是“让 LLM 读整份文档做自由提炼”。
- 如果让模型直接输出摘录文本，即使再做字符串校验，也不如“模型只返回片段 ID，程序按 ID 回填原文”稳。
- 评分标准应统一建模成 `SourceUnit`，覆盖表格行、标题+正文块、列表项和文字评分段；否则表格评分和文字评分会形成两套后处理链路。
- prompt 输出层最好继续只认 `scoring_items`、`requirement_brief`、`requirement_seed` 这几个字段，避免新检索模式把 prompt 合同搅乱。
- 当前 `Config` 已会按配置文件目录顺序加载 `.env` 和 `.env.local`，因此 embedding 连接参数进入 `.env.local` 不需要重做环境加载机制。
- embedding 的 `model` 不属于敏感信息，更适合保留在 `config_xxx.yaml`；连接参数 `API_BASE_URL`、`API_KEY` 才应放 `.env.local`。
- `hybrid_extract` 的第一版可以先不接 embedding、不接 LLM，仅靠结构化分段 + lexical retrieval 就能先验证收益，并降低实现复杂度。
- 成本视角下，embedding 一次性成本通常远低于逐章 rerank/verify；后续真正需要精控的是“哪些章节才值得做辅助模型校验”。

## Hybrid Extract 规划默认假设
- 默认把 `hybrid_extract` 视为新增模式，而不是替换现有模式。
- 默认第一轮实现只交付到 lexical-only，不把 embedding 和 rerank 作为首批阻塞项。
- 默认不新增检索依赖包，优先使用现有规则链路里的关键词、最长公共子串、标题链信号扩展出 lexical retrieval。
- 默认最终 prompt 仍然只暴露 `评分关注` 和 `需求要点`，不把 `SourceUnit`、候选分数等内部概念直接暴露给模型。
- 默认人工验收需要一组代表性章节样例，否则很难客观比较 `legacy_rule` 和 `hybrid_extract` 的得失。

## Hybrid Extract 已确认结论
- 第一轮实现范围已经锁定为 Phase 1-3，不把 embedding 与 rerank/verify 作为首批交付阻塞项。
- `config_公共服务满意度.yaml` 中新模式先保持关闭，等基准章节验证通过后再人工开启。
- lexical retrieval 第一版明确不新增第三方依赖。
- 基准验收章节已定为：
  - `2.1.4 验收要求与成果应用理解`
  - `2.4.2 1.2万至1.5万个有效样本配置方案`
  - `2.9.2 数据资料保密管理制度`
  - `2.10.4 全流程真实性追溯机制`
  - `3.3.4 合同履约至2026年12月底保障计划`
- 用户提供了待验证的 embedding 服务连接信息，但该信息不应进入 planning 文件、yaml 配置或普通命令日志。
- 对 OpenAI 兼容客户端而言，embedding `base_url` 更可能是服务根路径，真正的 `/embeddings` 路径由客户端追加；若直接把 `/v1/embeddings` 当作 `base_url`，有较高概率会拼接错误。

## Hybrid Extract Phase 1-3 实现后的确认
- `Config` 已新增 `context_pruning.mode`、`scoring.mode`、`requirements.mode`、`retrieval.*`、`embedding.*` 访问器，以及 `validate_context_pruning_runtime()`。
- `bid_writer/source_unit_parser.py` 已落地，采购需求、评分表格行、评分文字段已统一解析成 `SourceUnit`。
- `bid_writer/hybrid_retriever.py` 已落地，当前实现为 lexical-only 的 `hybrid_extract v1`。
- `bid_writer/context_pruner.py` 已支持评分标准和采购需求分别按 `legacy_rule` / `hybrid_extract` 路由，并会把 `retrieval_mode`、`fallback_reason`、selected ids 写进 `ChapterContext`。
- `hybrid_extract v1` 当前不会调用 embedding，也不会调用辅助模型；若配置提前打开 `vector_enabled` 或 `rerank_enabled`，会按策略回退或报错。
- 对公共服务满意度项目的 5 个基准章节，`hybrid_extract` 均已成功生成非空 `selected_scoring_unit_ids` 和 `selected_requirement_unit_ids`。
- 对纯 Markdown 文字评分样例，`SourceUnitParser.parse_scoring(parse_mode='auto')` 已能解析出带分值和标题+正文的评分项。

## Hybrid Extract Phase 4-5 实现后的确认
- `bid_writer/embedding_store.py` 已落地，支持：
  - embedding base URL 归一化
  - 文档向量缓存
  - query embedding
  - cosine similarity 检索
- `bid_writer/llm_verifier.py` 已落地，支持在少量候选上调用辅助模型，只返回 `selected_ids`，不直接输出摘录文本。
- `bid_writer/hybrid_retriever.py` 现在支持 lexical + vector 两路召回，并通过 rank-based 融合排序。
- `bid_writer/context_pruner.py` 已把 vector retrieval 与 verifier 接入到 scoring / requirements 两条 `hybrid_extract` 路径。
- embedding 实测可用：最小请求返回 `1536` 维向量。
- embedding `base_url` 即使被配置成 `.../v1/embeddings`，代码也会自动归一化到服务根路径后再请求。
- 在 verifier 打开的情况下，最终进入 prompt 的仍然是源文原文，因为 verifier 只允许返回候选 `unit_id`。

## 收尾核对补充发现
- 旧局部大纲字段已废弃并从 debug dump / trace 侧上下文记录中移除。
- `prompt_contract.md` 中若把旧局部大纲字段视为 prompt 输入、或把 `BID_WRITER_PRUNING_*` 视为“当前不参与章节提炼”，都会与现状不符。
- 当前 `BID_WRITER_EMBEDDING_*` 在 `vector_enabled=true` 时已经会参与章节检索；`BID_WRITER_PRUNING_*` 在 `llm_verify_enabled=true` 或 `rerank_enabled=true` 时已经会参与候选校验。
- `AIWriter._build_prompt_contract_blocks()` 的 `chapter_scope.source_context` 原先把旧局部大纲字段记成了 prompt 来源；现已改成真实来源 `HeadingNode.parent/title/siblings`，避免 trace 解释偏差。

## 配置编辑器设计相关发现
- 当前 GUI 只有“切换配置文件”，还没有“编辑配置内容”的入口；现有配置对话框更适合保留为快速切换器，而不是继续扩展成复杂表单。
- 当前 GUI 的交互风格以工具栏按钮 + `Toplevel` 模态窗口为主，新增配置编辑器时应延续这一风格，避免引入完全不同的导航模型。
- 当前 canonical schema 的 5 个一级分组已经足够稳定，适合直接成为配置编辑器的一级导航：`project / writing / processing / models / runtime`。
- `processing.path` 是最重要的业务开关，配置编辑器应先让用户选 `full_context / legacy_rule / hybrid_extract`，再展示链路参数；否则参数很多但缺乏主线。
- `project.inputs.*` 在真实项目里更适合作为“文件路径”来维护，不适合在配置器里直接编辑长篇采购需求或评分标准正文。
- `writing.role` 需要保留“文件路径”和“内嵌文本”两种能力，但界面应推荐 `role_file`，以减少大段 prompt 重复粘贴。
- `Config` 已提供足够多的 canonical accessor 和 `validate_context_pruning_runtime()`，说明配置编辑器后端不必从头设计字段解释层，主要缺的是 editor view model 和保存逻辑。
- `.env.local` 已经承载 generation / pruning / embedding 的敏感连接信息；配置编辑器更适合展示“是否已配置”的状态，而不是把 secrets 拉回到 YAML 表单里。
- 由于当前保存链路基于 PyYAML，若后续直接写回 YAML，默认不会保留原注释和字段顺序；这意味着配置编辑器首版应明确“保存即标准化”的产品语义。

## 配置编辑器实现后的补充发现
- 采用“canonical 可视化编辑 + preserved extras 回填”的保存策略后，可以在标准化输出的同时保留 `models.generation.base_url`、`api_key` 这类当前界面未直接编辑的连接字段，降低首版数据丢失风险。
- mixed-mode 旧配置无法直接映射到新的三路径模型，首版编辑器通过 `processing.path=mixed` 的过渡态显式报错，要求用户先做业务决策，再允许保存。
- `project.inputs.bid_requirements` / `scoring_criteria` 和 `writing.role` 的旧式 inline 文本仍可通过“文件 / 内嵌文本”双模式编辑，不会因为标准化 UI 被直接抹掉。
- 把配置编辑器拆成 `config_editor.py` 与 `config_editor_dialog.py` 两层后，YAML 导出与校验逻辑可以独立测试，不需要依赖 Tk 界面才能验证核心行为。
- 当前首版列表型字段采用“每行一条”的文本编辑方式，复杂度明显低于自定义列表控件，同时已足够覆盖 `hard_constraints` 和 `extra_rules` 的主要维护场景。
- 对“用户可能不懂参数”的问题，最直接有效的改法不是再挪分组，而是给字段本身补悬停解释；这样用户在编辑现场就能获得解释，不需要来回翻文档。
- 将 tip 文案单独抽到 `config_editor_tooltips.py` 后，后续可以独立维护字段说明，而不必反复改动 Tk 布局代码。
- `ScrollableSection` 若直接对每个分区使用 `bind_all("<MouseWheel>")`，在窗口关闭后容易残留全局滚轮回调；这类问题必须在回调里兜底 `TclError`，并在销毁时主动解绑。

## 章节依存关系评估的初步发现
- `docs/chapter_expansion_mechanism.md` 和 `docs/prompt_contract.md` 都表明，当前 user prompt 只注入“当前章节任务 + 裁剪后的招标需求/评分标准 + 当前章节边界信息”，没有“已写章节结论摘要”区块。
- 现有 `context_pruning` 主要负责“源文材料到当前章节”的路由，不负责“已生成章节到当前章节”的跨章节一致性传递。
- 旧局部大纲字段已废弃；当前章节边界仍由 `scope_reference` 和章节路径信息表达，不会把兄弟章节已写结果回灌到 prompt。
- 当前 full-context 分支虽然能注入完整需求和评分标准，但这只能缓解“对原始要求理解不一致”，不能解决“前文已做出的具体承诺/口径在后文不一致”。
- 文档中已有 `chapter_writing_plan` 能在 full-context 模式下先生成“章节写作计划”，说明现有架构允许在正文扩写前插入额外的前置推理/摘要步骤。
- 从机制上看，“章节依存关系”更适合落在 `AIWriter.build_prompt_result()` 之前或之中，作为与 `scoring_focus` / `requirement_brief` 同级的新 prompt 区块，而不是混进 system prompt。

## 章节依存关系评估的代码级发现
- `AIWriter.build_prompt_result()` 当前只在 pruned 分支追加 `scope_reference`、`project_background`、`scoring_focus`、`requirement_brief/points`，在 full-context 分支则追加完整 `bid_requirements`、`scoring_criteria`，没有任何“chapter dependency / prior section context”注入口。
- `AIWriter._build_prompt_contract_blocks()` 已把 prompt 拆成 `system_constraints / chapter_task / structure_rules / chapter_scope / project_background / requirement_context / scoring_context` 七类区块，这为未来新增 `dependency_context` 提供了清晰扩展点。
- `ChapterWritingPlanGenerator` 已经实现了“在正文前先生成一个短文本、并按 `heading.full_path + prompt 输入` 做缓存”的模式；如果要新增“依存摘要生成器”，这套缓存与请求组织方式基本可以复用。
- `FileSaver.find_existing_filepath()` 已能基于 `heading_id` 或兼容旧命名规则稳定找到某章节“最近一次生成”的正文文件；`load_section_body()` 还能去掉 front matter 和重复标题，适合作为依存摘要的输入源。
- 当前 GUI 侧 `_show_heading_preview_in_workspace()` 和 `BidWriter.merge_generated_sections()` 都已经在读回已生成章节正文，但这些读取结果只用于预览和整合，没有进入 `AIWriter`。
- `context_pruner._build_requirement_brief()` 当前不是调用 LLM 摘要，而是从命中的需求块中抽取短摘录，这说明项目现有偏好是“证据型压缩”而不是“自由总结”；章节依存摘要如果照此风格设计，风险会更低。
- `Config` 已有 `processing.full_context.chapter_writing_plan.*` 这类前置辅助能力配置入口，新增 `chapter_dependencies.*` 时可以复用同样的 schema 风格，而不必把配置散落到根级字段。

## 章节依存关系评估的建模结论
- 这个需求本质上不是“扩大原始输入上下文”，而是新增一条“生成结果到后续生成结果”的中间记忆链路。
- 依存关系至少可分为三类：
  - 前文承诺继承：后续章节必须沿用前文已确定的目标、口径、组织模式、角色分工、时间节点等
  - 横向边界避让：当前章节应知道相邻兄弟章节已承担了什么，避免重复
  - 后文预埋约束：当前章节在写作时应兼顾后续章节将展开的内容边界，避免抢写
- 真正适合注入 prompt 的，主要是“前文承诺继承”和“横向边界避让”；“后文预埋约束”更适合作为依存选择规则的一部分，而不是直接注入未来未知内容。
- 依存摘要来源建议分层：
  - 第一层：直接摘取已写章节中的结构化句子/要点，风险最低
  - 第二层：对已写章节做受限摘要，只抽“本章已确定事实/承诺/口径”
  - 第三层：跨多个依存章节再做汇总，适合作为后续增强，不适合首版
- 配置挂载位置最自然的是 `processing.full_context.chapter_dependencies.*`，因为当前最明显的一致性问题集中在 full-context 直写链路；后续如有需要，再决定是否对 `legacy_rule` / `hybrid_extract` 共享该能力。
- `config.example.yaml` 与 `docs/config_schema.md` 已有 `processing.full_context.chapter_writing_plan.*` 先例，因此“章节依存摘要”作为同类前置辅助能力加入 schema，不会破坏当前 canonical 设计。

## 章节依存关系评估的最终落点
- 最核心的改动入口是 `AIWriter.build_prompt_result()`：这里当前负责决定哪些 prompt section 被注入，因此新增 `dependency_context` 区块最顺手。
- 与之配套的提示词合同扩展点是 `AIWriter._build_prompt_contract_blocks()`；如果实现该能力，需要同步把 `dependency_context` 写入 trace/contract，否则后续难以审计实际注入了哪些依存摘要。
- 最适合复用的实现模式不是 `context_pruner`，而是 `ChapterWritingPlanGenerator` 这种“按当前章节 + 输入上下文生成短文本并落缓存”的辅助生成器。
- 读取依存章节正文时，应优先通过 `FileSaver.find_existing_filepath()` + `load_section_body()` 走稳定 ID 路径，而不是直接猜文件名。
- 若首版坚持“证据型压缩”，也可以先不走 LLM，只复用 `requirement_brief` 类似的摘录逻辑，对已写章节正文抽取 3-5 条短句作为依存摘要。
