# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

### Package Management
```bash
# Add new dependencies
uv add package_name

# Update dependencies
uv lock
uv sync
```

## Architecture Overview

The system follows a modular architecture with clear separation of concerns:

### Core Modules (`bid_writer/`)

1. **main.py** - Application entry point and orchestration
   - `BidWriter` class coordinates all components
   - Manages the main workflow loop and user interactions
   - Handles batch expansion and preview workflow

2. **terminal_ui.py** - Interactive terminal interface using Rich and Questionary
   - Implements hierarchical navigation for outline selection
   - Provides real-time streaming content display
   - Handles pagination for large outline trees
   - Tracks generated files to prevent duplicates

3. **ai_writer.py** - AI content generation engine
   - Builds structured prompts from outline context
   - Integrates bid requirements and scoring criteria automatically
   - Stream responses for real-time display
   - Configurable model parameters (temperature, max_tokens)

4. **outline_parser.py** - Markdown outline parsing
   - Parses nested heading structure (1-3 levels)
   - Builds hierarchical tree of `HeadingNode` objects
   - Provides navigation methods for different heading levels
   - Identifies leaf nodes for expansion

5. **config.py** - Configuration management
   - Loads YAML configuration with environment variable overrides
   - Dynamically loads bid requirements and scoring criteria from files
   - Manages API credentials and model settings
   - Provides hot-reload capability

6. **file_saver.py** - Output file management
   - Sanitizes filenames for filesystem safety
   - Handles duplicate filename conflicts
   - Organizes output in structured directories

7. **history.py** - Tracking and statistics
   - Records all generation attempts with metadata
   - Provides statistics on success rates and word counts
   - Supports historical query and analysis

### Configuration System

The system uses a hierarchical configuration approach:
- **config.yaml**: Main configuration file
- **Environment variables**: Override config file (e.g., `BID_WRITER_API_KEY`)
- **Dynamic file loading**: Bid requirements and scoring criteria can be separate files
- **Outline structure**: Markdown file with nested headings defines bid structure

### Key Workflow

1. User selects headings through hierarchical navigation (Chapter → Section → Subsection)
2. System builds comprehensive prompts including:
   - Outline path context
   - Full bid requirements document
   - Scoring criteria for optimization
   - Additional user requirements
3. AI generates content with streaming display
4. User can preview, modify, or regenerate content
5. Approved content is saved with sanitized filenames
6. All operations logged to history for tracking

## Important Implementation Details

### Document Standards
- Output follows Chinese government document formatting (not Markdown)
- Uses numbered hierarchy: 一、 (level 1), （一） (level 2), 1. (level 3), （1） (level 4)
- Content must be professional, technical, and compliance-focused

### AI Prompt Engineering
- System role defines bid writing expert with 20 years of experience
- Three-part structure: Structure Compliance + Content Injection + Scoring Optimization
- Automatically incorporates scoring criteria keywords for higher scores

### File Management
- Output directory: `./output/` (configurable)
- Filename sanitization removes invalid characters
- Duplicate detection based on content title
- Automatic numbered suffix for conflicts

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
- 使用uv作为包管理器，使用uv run 的形式运行和测试代码