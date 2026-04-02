# 章节生成 Trace 日志系统

## 目标

`generation_trace` 用于记录单次章节扩写时的上下文拼接过程、最终 prompt 和模型输出结果，便于人工检查：

- 当前章节拿到了哪些局部大纲
- 命中了哪些评分项
- 采购需求哪些片段被选入上下文
- 最终发给模型的 `system prompt` / `user prompt` 是什么
- 模型最终输出了什么内容

该日志系统面向“调 prompt”和“看上下文质量”的场景，不替代正常输出文件。

## 配置方式

```yaml
generation_trace:
  enabled: true
  mode: "full"
  write_prompt: true
  write_output: true
  write_context: true
  write_summary: true
  redact_sensitive: true
```

字段说明：

- `enabled`
  是否启用章节生成 trace。
- `mode`
  `basic` 或 `full`。`full` 会记录完整上下文拼接信息；`basic` 更适合只看 prompt 和最终输出。
- `write_prompt`
  是否写出最终的 `system prompt` 和 `user prompt`。
- `write_output`
  是否写出模型最终返回的正文。
- `write_context`
  是否写出上下文拼接详情。`full` 模式下建议保持开启。
- `write_summary`
  是否写出人工快速浏览用的摘要文件。
- `redact_sensitive`
  是否脱敏敏感字段。开启后不会记录完整 `api_base_url`，只保留 host；不会记录任何密钥。

如果未显式指定 `generation_trace.directory`，日志目录默认为：

```text
<output.directory>/_generation_traces/
```

## 目录结构

单次章节生成会创建一个独立目录：

```text
output/
  _generation_traces/
    20260401_181530__数据资料保密管理制度__a1b2c3d4e5f6/
      manifest.json
      01_heading.json
      02_context_assembly.json
      03_prompt_system.md
      04_prompt_user.md
      05_request_options.json
      06_generation_output.md
      07_summary.md
```

目录命名规则：

- 前缀时间戳：便于按生成顺序浏览
- 中间是章节标题的清洗结果：便于人工识别
- 尾部是 `trace_id`：避免重名覆盖

## 文件说明

### `manifest.json`

总索引文件，记录：

- `trace_id`
- `status`
- `created_at` / `completed_at`
- 当前章节标题与完整路径
- 当前生成模式：`pruned` 或 `full`
- prompt 长度统计
- 后处理动作摘要
- 请求参数摘要
- 各 trace 文件名

### `01_heading.json`

记录本次生成的原始输入：

- `title`
- `full_path`
- `level`
- `line_number`
- `additional_requirements`
- `min_words`
- `stream`

### `02_context_assembly.json`

这是最核心的中间日志，用来还原“prompt 是怎么拼出来的”。

公共字段：

- `context_mode`
- `context_pruning_enabled`
- `prompt_contract`
- `prompt_sections`
- `prompt_lengths`

其中 `prompt_contract` 是 Phase 1 新增的维护者视角摘要层，包含：

- `block_order`
- `blocks`

每个 `blocks[]` 条目都会记录：

- `id`
- `label`
- `prompt_kind`
- `section_names`
- `source_context`
- `chars`

推荐先看 `prompt_contract`，再下钻到 `prompt_sections`。前者回答“本次 prompt 按哪几个业务块组织”，后者回答“每个业务块底下具体落到了哪些低层 section”。

当 `context_mode = "pruned"` 时，还会记录 `pruned_context`，主要包括：

- `local_outline`
- `response_labels`
- `match_keywords`
- `scoring_items`
- `scoring_candidates`
- `requirement_seed`
- `requirement_blocks`
- `requirement_brief`
- `requirement_brief_status`
- `requirement_brief_error`

当 `context_mode = "full"` 时，会记录 `full_context`：

- `outline_chars`
- `bid_requirements_chars`
- `scoring_criteria_chars`

### `03_prompt_system.md`

最终发给模型的 `system prompt` 原文。

### `04_prompt_user.md`

最终发给模型的 `user prompt` 原文。  
这是判断“上下文合不合适”时最值得直接打开的文件。

### `05_request_options.json`

记录实际请求参数，但不包含密钥：

- `model`
- `temperature`
- `max_tokens`
- `stream`
- `top_p`
- `seed`
- `api_base_url_host` 或 `api_base_url`

### `06_generation_output.md`

记录模型最终输出正文，以及本次生成的状态：

- `completed`
- `failed`
- `interrupted`

如果流式输出过程中被中断，这里会保留已收到的部分内容。

当启用了后处理时，还会记录：

- 是否触发主体称谓归一化
- 实际归一化替换次数
- 是否触发格式修复
- 触发修复的问题类型

### `07_summary.md`

给人看的快速摘要，适合先扫一眼：

- 本章标题
- 上下文模式
- business-block 顺序（`prompt_contract_blocks`）
- prompt 长度
- 命中评分项数量
- 需求 seed / brief 长度
- brief 状态
- 后处理动作摘要
- trace 文件清单

## 记录时机

trace 会在三个阶段落盘：

1. 构造完上下文与 prompt 后
2. 发起模型请求前
3. 模型返回完成后，补齐最终输出和状态

因此即使生成失败，也会保留：

- 当时的 prompt
- 请求参数
- 已完成的上下文裁剪结果

## 推荐查看顺序

你在人工判断上下文是否合适时，建议按这个顺序看：

1. `07_summary.md`
2. `02_context_assembly.json` 中的 `prompt_contract`
3. `02_context_assembly.json` 中的 `prompt_sections`
4. `04_prompt_user.md`
4. `06_generation_output.md`

如果只是判断“是不是塞了太多无关内容”，通常看到第 3 步就够了。

## 与 `context_pruning.debug_dump` 的关系

两者可以同时开启：

- `context_pruning.debug_dump`
  轻量 sidecar，适合快速看裁剪结果。
- `generation_trace`
  完整 trace，适合系统性排查 prompt 拼接和最终输出。

建议在需要人工调试上下文时优先看 `generation_trace`。
