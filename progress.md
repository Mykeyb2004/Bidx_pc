# Progress

## 2026-03-15
- 读取并分析了 `file_saver.py`、`gui.py`、`gui_adapter.py` 的文件名相关逻辑。
- 确认当前项目没有使用 `full_path` 作为输出文件主键。
- 开始输出“转义方案”的完整改动评估和推荐结论。
- 新增分析 GUI 启动配置选择、树展开状态、生成后视图重置问题。
- 确认了当前 `run_gui()`、`load_outline()`、`select_and_switch_config()` 都会触发或依赖树重绘，适合统一抽象“视图状态保存/恢复”。
- 已整理出一版最小改动优化方案，等待用户确认后再实现。
- 已新增 `bid_writer/gui_state.py`，持久化上次成功加载的配置文件。
- 已调整 GUI 启动逻辑，默认直接加载上次配置或 `config.yaml`，不再默认弹启动选择框。
- 已为大纲树加入默认全部展开与展开状态恢复逻辑，并通过脚本验证刷新后能够保留一级展开和自定义收起状态。
- 新任务：修复 `config.yaml` 中 `bid_requirements` / `scoring_criteria` 的多行块路径写法，使其真正读取 `.md` 文件正文并注入 prompt。
- 已复核 `AIWriter.build_prompt()`、`Config._get_text_or_file()` 与运行时 prompt，确认当前模型接收到的是路径字符串而不是文件内容。
- 已修改 `bid_writer/config.py`，兼容从多行块 inline 文本中提取唯一有效路径，并在文件存在时读取 Markdown 正文。
- 已用 `uv run python` 做运行时验证：`bid_requirements` 首行为 `# 项目采购需求`，`scoring_criteria` 首行为 `# 评分标准`，prompt 中不再出现原始路径字面量。
- 新任务：在章节扩写 prompt 中补充完整总大纲原文，并强化“仅写当前章节范围、避免与其他章节重复”的边界约束。
- 已确认当前实现只包含 `heading.title` 和 `heading.full_path`，尚未把完整大纲文本传给模型。
- 已修改 `bid_writer/ai_writer.py`，在 prompt 中新增“完整总大纲参考”段落，并加入边界控制与全局去重约束语句。
- 已用 `uv run python` 构造真实 prompt 验证：当前标题、标题层级路径、完整总大纲原文均已注入。
- 新任务：修复 review 中的 3 个行为问题，涉及 `file_saver.py`、`config.py/main.py`、`gui.py`。
- 已完成会话恢复检查并复读 `task_plan.md`、`findings.md`、`progress.md`，确认本轮工作在现有代码基础上继续，不回退用户改动。
- 已复现实例：`overwrite_existing=False` 时连续保存同一章节，读取侧仍返回第一份旧文件。
- 已复现实例：从其他目录的配置文件读取 `output.directory: ./out` 时，实际输出目录落在当前工作目录而不是配置文件目录。
- 已确认 `GenerationWindow` 当前未处理用户主动关闭窗口的生命周期。
- 已修改 `bid_writer/file_saver.py`，读取同一章节时改为从所有候选版本里选择最近生成的文件。
- 已修改 `bid_writer/config.py`，`output_directory` 现统一按配置文件目录解析。
- 已修改 `bid_writer/gui.py`，生成进度窗注册关闭处理，并把队列轮询改为挂在父窗口上，避免关闭子窗后丢失状态更新。
- 已完成 3 组验证：版本文件读取返回最新内容；相对输出目录解析到配置目录；关闭进度窗后后台生成仍能正常返回结果。
- 已重新运行 `uv run python -m compileall bid_writer run.py`，通过。

## 2026-04-01
- 用户继续讨论“章节级上下文裁剪”方案，并指定调试验证应以 `config_公共服务满意度.yaml` 为基准配置。
- 已检查当前启动逻辑，确认默认顺序仍是“显式参数 > 上次成功配置 > config.yaml > 其他配置文件”，因此公共服务满意度配置更适合作为显式 `--config` 调试基准，而不是替换 GUI 默认启动顺序。
- 已检查当前模型接入形态，确认项目仍只有单一 `AIWriter` 客户端和一套 `api.*` 配置，辅助摘要模型需要新增独立配置接口。
- 已检查 `config_公共服务满意度.yaml`，确认其 prompt 仍使用旧字段组合，尚未迁移到当前已实现的 `prompt.allow_markdown_headings`、`prompt.bidder_name`、`prompt.hard_constraints` 机制。
- 已与用户确认：辅助模型的 `base_url` 和 `api_key` 视为敏感信息，只能进入 `.env.local`，不能进入 YAML。
- 已确定后续规划方向：裁剪链路采用“规则提取局部大纲/评分项 + 可选轻量模型压缩需求 brief”的混合方案；辅助模型环境变量采用独立前缀 `BID_WRITER_PRUNING_*`。
- 执行 `planning-with-files` 的 catchup 脚本时发现默认路径不存在，已改为直接读取项目内现有 planning 文件续接上下文，并在 `task_plan.md` 记录该问题。
- 已修改 `bid_writer/config.py`，新增 `context_pruning` 配置读取与 `BID_WRITER_PRUNING_*` 环境变量覆写能力，并加入 `pruning_api_is_configured` 判定。
- 已更新 `config_公共服务满意度.yaml`，迁移到新 prompt 字段并加入 `context_pruning` 基准配置。
- 已更新 `.env.example` 与 `README.md`，补充章节裁剪辅助模型的 `.env.local` 用法说明。
- 已用 `uv run python` 分别验证默认读取和环境变量覆写场景；同时运行 `uv run python -m compileall bid_writer run.py` 通过。
- 已新增 `bid_writer/context_pruner.py`，实现章节级局部大纲、评分项路由、需求 seed 提取和可选需求 brief 生成。
- 已修改 `bid_writer/ai_writer.py`，在 `context_pruning.enabled=true` 时切换为裁剪 prompt 注入模式；关闭时仍保留旧的全量注入逻辑。
- 已对 `2.9.2 数据资料保密管理制度` 和 `3.3.4 合同履约至2026年12月底保障计划` 做运行时验证，确认评分路由和需求 seed 均能命中对应内容。
- 已验证辅助模型失败回退：将 `BID_WRITER_PRUNING_API_BASE_URL` 指向不可用地址时，`requirement_brief` 为空，主流程继续使用规则提取的需求片段。
- 已验证 prompt 长度缩减：同一章节在公共服务满意度配置下，裁剪版 prompt 长度为 `2778`，旧版为 `9317`。
- 已进一步补充 `context_pruning.debug_dump`：启用后会在输出目录生成 `_context_pruning_debug` sidecar 文件，记录章节裁剪结果和 prompt 长度统计。
- 已再次验证公共服务满意度基准配置下的两个章节样例，确认 prompt 构造仍然正常，且 `debug_dump` 文件可以成功落盘。
