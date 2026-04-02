# 自动标书撰写系统

## What This Is

这是一个基于 Python + Tkinter 的桌面版标书撰写工具。系统读取 Markdown 大纲、招标需求和评分标准，为用户选中的章节生成可直接进入标书正文的内容，并将结果保存到本地文件。当前工作的重点不是重做产品形态，而是在现有生成链路上系统优化提示词、上下文裁剪和质量验证闭环。

## Core Value

在不增加操作负担的前提下，让每个章节都能稳定生成贴合招标要求、结构规范、可直接交付的正文。

## Requirements

### Validated

- ✓ 用户可以在桌面 GUI 中按大纲树选择叶子章节并批量生成章节正文。 — existing
- ✓ 系统可以从 YAML 与本地文件加载大纲、招标需求、评分标准和模型配置。 — existing
- ✓ 系统已经具备 prompt 配置项、章节级上下文裁剪、生成 trace 与基础后处理能力。 — existing
- ✓ 系统可以将单章节结果保存到本地，并按大纲顺序整合为完整标书草稿。 — existing

### Active

- [ ] 建立清晰、可维护、可追踪的提示词装配契约，降低后续调 prompt 成本。
- [ ] 提高章节上下文选择精度，减少无关需求、错配评分项和章节越界内容。
- [ ] 建立基于 trace 和样本章节的 prompt 调优闭环，能比较改动前后效果。
- [ ] 强化输出格式守卫，降低无序号、标题违规、主体称谓漂移和总结段违规等问题。

### Out of Scope

- Web 化或服务端重构。 — 当前用户目标是优化现有桌面生成链路，不是更换产品形态。
- 大规模 GUI 改版。 — 本轮工作的核心是 prompt 与生成质量，不是界面重设计。
- 更换主模型供应商或重做模型接入层。 — 除非 prompt 优化明确受阻，否则不扩散到基础设施替换。

## Context

- 当前代码库是 brownfield 项目，已经完成 `.planning/codebase/*` 映射，但尚未建立项目级 `PROJECT / REQUIREMENTS / ROADMAP / STATE` 文档。
- 生成核心位于 `bid_writer/ai_writer.py`，当前已经支持 task card、结构硬要求、章节级上下文裁剪、trace 落盘和基础格式问题检测。
- `bid_writer/config.py` 已暴露较多 prompt 相关配置，包括 `hard_constraints`、`extra_rules`、`summary_title`、`bidder_name`、`max_tables_per_section` 和 `context_pruning.*`。
- `docs/generation_trace.md` 已说明 trace 工具主要用于调 prompt 和检查上下文质量，说明项目已经具备可观测性的基础，只缺少体系化调优流程。
- 当前没有自动化测试目录，后续与 prompt 优化相关的验证手段需要从样本章节、trace 对比和最小回归检查开始建立。

## Constraints

- **Tech stack**: 保持 Python + Tkinter + OpenAI Python SDK 现有桌面架构。 — 用户目标是优化生成效果，而不是迁移技术栈。
- **Workflow**: 运行、测试与调试统一通过 `uv run`。 — 仓库约定已明确要求使用 `uv`。
- **Document standard**: 输出必须符合中文政府采购/标书正文风格。 — 这是产品的核心质量标准，不能在调优中弱化。
- **Compatibility**: 现有配置文件需要继续可用。 — brownfield 优化不能要求用户重写所有 YAML。
- **Observability**: 调优结果必须可通过 trace 或样本对比回看。 — 仅凭主观感觉改 prompt 会导致回归不可控。

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 以 brownfield prompt 优化作为本次项目初始化范围 | 现有产品功能已成型，用户当前目标明确指向“优化提示词” | — Pending |
| 优先改造生成链路中的 prompt contract、上下文选择和验证闭环 | 这些环节直接决定输出质量，且比大范围 UI/架构调整更贴近目标 | — Pending |
| 将可观测性与评估能力纳入 v1 范围 | prompt 优化如果没有回看与对比机制，后续无法稳定迭代 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-02 after initialization*
