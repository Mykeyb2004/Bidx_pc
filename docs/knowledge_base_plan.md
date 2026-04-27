# 知识库与事实卡片方案

> 状态：已归档。当前章节生成已废弃 `knowledge_context` prompt 注入；投标方事实只通过事实卡片机制进入 prompt。本文仅保留旧方案背景，不能作为现行生成链路说明。

## 当前定位

知识库机制曾负责读取用户手写资料，并把这些资料作为 `knowledge_context` 注入 prompt。该运行时注入链路已经下线，配置中的知识库字段仅为旧项目兼容保留。

一致性约束统一交给事实卡片机制：

- 全局事实卡片用于项目级稳定事实，例如投标主体、团队承诺、服务边界
- 局部事实卡片用于某个章节需要复用的关键事实
- 强制卡片作为硬约束，参考卡片作为可引用信息
- 生成前会检测强制卡片之间的冲突，冲突时阻断模型调用

## 运行时输入

`KnowledgeAssembler` 仍可作为独立兼容模块读取旧知识文档，但当前章节生成主链路不再调用它，也不会把读取结果写入 prompt。

旧字段包括：

- `project.inputs.knowledge_files`
- `project.inputs.knowledge_directory`
- `processing.knowledge.enabled`
- `processing.knowledge.max_chars`

它不再读取旧的章节关系 sidecar 文件，也不再从章节 facts 缓存自动拼装跨章节事实。

## 已下线内容

以下旧方案已退出运行时：

- 章节关系配置
- 章节摘要缓存
- 章节摘要预提炼
- 基于章节关系的 facts 自动注入
- 章节树上的关系标记与悬浮提示
- `knowledge_context` prompt 注入
- 无事实卡片时回退知识库上下文

旧项目目录中若还存在 `.bid_writer/chapter_dependencies.json` 或 `.bid_writer/chapter_summaries.json`，当前程序会忽略它们。
