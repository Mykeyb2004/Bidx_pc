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
