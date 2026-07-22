# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered bid writing system (标书智写) that generates professional bid content based on Markdown outlines. The system uses Gemini models to expand headings into comprehensive bid sections with Chinese government document standards.

## Development Commands

### Setup and Run
```bash
# Install dependencies using uv
uv sync

# Run the application directly
uv run python run.py

# Or use the installed command
uv run bid-writer

# Run with custom config
uv run python -m bid_writer.main -c custom_config.yaml
```
- 使用uv run 的形式运行和测试代码

### Package Management
```bash
# Add new dependencies
uv add package_name

# Update dependencies
uv lock
uv sync
```

## Important Implementation Details

### Document Standards
- Output follows Chinese government document formatting (not Markdown)
- Uses numbered hierarchy: 一、 (level 1), （一） (level 2), 1. (level 3), （1） (level 4)
- Content must be professional, technical, and compliance-focused

### 投标大纲层级约定
- 投标大纲是系统的章节任务树，不是最终正文；系统按 Markdown 标题解析项目、章节、分节和具体写作单元。
- `#` / H1：项目总标题，通常对应整份投标文件或项目名称，只作为全局根节点与上下文，不作为常规正文扩写单元。
- `##` / H2：标书一级章，通常对应投标文件的大章节，如“项目理解与工作基础”“总体服务方案”等。
- `###` / H3：章内二级节，通常用于承接 H2 下的核心板块，帮助定位评分点、采购需求和写作范围。
- `####` / H4：具体写作单元，通常是当前项目的主要扩写对象；当大纲继续细分时，应优先选择最深层叶子节点生成正文。
- `#####` / H5：更细的写作子单元，仅在大纲确有必要进一步拆解时使用；若存在 H5，H5 作为更优先的叶子写作单元，H4 主要承担父级上下文作用。
- Markdown 标题层级只用于输入大纲结构解析；生成的标书正文默认不得输出 Markdown 标题，应按正式层级序号组织正文。
- 解析和生成时应保留完整章节路径，例如 `H1 > H2 > H3 > H4`，用于判断当前章节的祖先、同级标题、评分响应范围和输出文件命名。

### File Management
- Output directory: `./output/` (configurable)
- Filename sanitization removes invalid characters
- Duplicate detection based on content title
- Automatic numbered suffix for conflicts
- 测试脚本文件在 /tests 中
- 功能说明性文档在 /docs 中，开发过程中分析性、说明性文档保存在此处，并在功能变动时维护这些文档。有相关功能的变动也先参考一下对应文档
- 配置结构相关变更时，需同步维护 `/docs/config_schema.md`、`/config.example.yaml`、相关 `config_*.yaml` 与对应测试夹具
- 调试日志放到 /log 中

### Error Handling
- Graceful handling of missing files (config, outline)
- API failure recovery with user feedback
- Keyboard interrupt handling for clean exits

## Testing Notes

No automated test suite currently exists. When testing:
- Use sample outline files with representative structure
- Verify API connectivity and credentials
- Test pagination with large outlines (>10 items per level)
- Verify output file naming and conflict resolution
- Check history recording and statistics calculation

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Bidx_pc** (5280 symbols, 10479 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Bidx_pc/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Bidx_pc/clusters` | All functional areas |
| `gitnexus://repo/Bidx_pc/processes` | All execution flows |
| `gitnexus://repo/Bidx_pc/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
