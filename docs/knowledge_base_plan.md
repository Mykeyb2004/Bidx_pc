# 知识库与事实卡片方案

## 当前定位

知识库机制只负责读取用户手写资料，并把这些资料作为 `knowledge_context` 注入 prompt。章节间一致性不再通过章节关系、章节摘要或自动读取其他章节 facts 实现。

一致性约束统一交给事实卡片机制：

- 全局事实卡片用于项目级稳定事实，例如投标主体、团队承诺、服务边界
- 局部事实卡片用于某个章节需要复用的关键事实
- 强制卡片作为硬约束，参考卡片作为可引用信息
- 生成前会检测强制卡片之间的冲突，冲突时阻断模型调用

## 运行时输入

`KnowledgeAssembler` 的运行时输入只有两类：

- `processing.knowledge.enabled` 开启后读取的手写知识文档
- `processing.knowledge.max_chars` 控制后的知识文档内容

它不再读取旧的章节关系 sidecar 文件，也不再从章节 facts 缓存自动拼装跨章节事实。

## 已下线内容

以下旧方案已退出运行时：

- 章节关系配置
- 章节摘要缓存
- 章节摘要预提炼
- 基于章节关系的 facts 自动注入
- 章节树上的关系标记与悬浮提示

旧项目目录中若还存在 `.bid_writer/chapter_dependencies.json` 或 `.bid_writer/chapter_summaries.json`，当前程序会忽略它们。
