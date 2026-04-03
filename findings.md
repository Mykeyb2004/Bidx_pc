# Findings

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
- `ChapterContext.local_outline` 当前只用于 debug dump 和 trace 侧上下文记录，没有被 `AIWriter.build_prompt_result()` 直接拼进 user prompt。
- `prompt_contract.md` 中若把 `local_outline` 视为 prompt 输入、或把 `BID_WRITER_PRUNING_*` 视为“当前不参与章节提炼”，都会与现状不符。
- 当前 `BID_WRITER_EMBEDDING_*` 在 `vector_enabled=true` 时已经会参与章节检索；`BID_WRITER_PRUNING_*` 在 `llm_verify_enabled=true` 或 `rerank_enabled=true` 时已经会参与候选校验。
- `AIWriter._build_prompt_contract_blocks()` 的 `chapter_scope.source_context` 原先把 `pruned_context.local_outline` 记成了 prompt 来源；现已改成真实来源 `HeadingNode.parent/title/siblings`，避免 trace 解释偏差。
