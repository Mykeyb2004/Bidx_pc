# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered bid writing system (自动标书撰写系统) that generates professional bid content based on Markdown outlines. The system uses Gemini models to expand headings into comprehensive bid sections with Chinese government document standards.

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

### File Management
- Output directory: `./output/` (configurable)
- Filename sanitization removes invalid characters
- Duplicate detection based on content title
- Automatic numbered suffix for conflicts
- 测试脚本文件在 /tests 中
- 功能说明性文档在 /docs 中，开发过程中分析性、说明性文档保存在此处，并在功能变动时维护这些文档。有相关功能的变动也先参考一下对应文档
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
