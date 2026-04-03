from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from bid_writer.ai_writer import AIWriter
from bid_writer.config import Config
from bid_writer.context_pruner import ChapterContext
from bid_writer.outline_parser import HeadingNode, parse_outline


DEFAULT_CONFIGS = [
    "config_公共服务满意度_hybrid_extract.yaml",
    "config_公共服务满意度_hybrid_extract_full.yaml",
]
OUTPUT_DIR = Path("output/h2check")
REQUIREMENT_SECTION_NAMES = {"requirement_brief", "requirement_points"}
SCORING_SECTION_NAME = "scoring_focus"


def _safe_stem(path: Path) -> str:
    return path.stem.replace("/", "_").replace("\\", "_")


def _find_section(prompt_sections: list[dict[str, str]], target_names: set[str] | str) -> str:
    names = {target_names} if isinstance(target_names, str) else set(target_names)
    for section in prompt_sections:
        if section.get("name") in names:
            return (section.get("content") or "").strip()
    return ""


def _format_scoring_items(context: ChapterContext) -> str:
    if not context.scoring_items:
        return "（无）"

    lines: list[str] = []
    for index, item in enumerate(context.scoring_items, start=1):
        title = item.subitem or "（无标题）"
        if item.weight:
            title = f"{title}（权重：{item.weight}）"
        lines.append(f"{index}. {title} [score={item.match_score}]")
        lines.append("")
        lines.append(item.standard.strip() or "（无正文）")
        lines.append("")
    return "\n".join(lines).strip()


def _format_selected_requirement_blocks(context: ChapterContext) -> str:
    selected = [match for match in context.requirement_blocks if match.selected and match.block.strip()]
    if not selected:
        return "（无）"

    lines: list[str] = []
    for index, match in enumerate(selected, start=1):
        lines.append(f"{index}. block_index={match.index} score={match.score} chars={match.chars}")
        lines.append("")
        lines.append(match.block.strip())
        lines.append("")
    return "\n".join(lines).strip()


def _render_h2_entry(
    heading: HeadingNode,
    requirement_text: str,
    scoring_text: str,
    context: ChapterContext | None,
) -> str:
    lines = [
        f"## {heading.title}",
        "",
        f"- full_path: {heading.full_path}",
        f"- level: H{heading.level}",
    ]

    if context is None:
        lines.extend(
            [
                "- context_status: pruned_context_failed_or_fallback_to_full",
                "",
                "### 采购需求提炼输出",
                requirement_text or "（无）",
                "",
                "### 评分标准提炼输出",
                scoring_text or "（无）",
                "",
            ]
        )
        return "\n".join(lines).strip()

    lines.extend(
        [
            f"- retrieval_mode: {context.retrieval_mode or '（无）'}",
            f"- fallback_reason: {context.fallback_reason or '（无）'}",
            f"- selected_requirement_unit_ids: {', '.join(context.selected_requirement_unit_ids) if context.selected_requirement_unit_ids else '（无）'}",
            f"- selected_scoring_unit_ids: {', '.join(context.selected_scoring_unit_ids) if context.selected_scoring_unit_ids else '（无）'}",
            "",
            "### 采购需求提炼输出",
            requirement_text or "（无）",
            "",
            "### 评分标准提炼输出",
            scoring_text or "（无）",
            "",
            "### 命中采购需求原文块",
            _format_selected_requirement_blocks(context),
            "",
            "### 命中评分标准原文块",
            _format_scoring_items(context),
            "",
        ]
    )
    return "\n".join(lines).strip()


def build_report(config_path: Path) -> str:
    config = Config(str(config_path))
    config._config.setdefault("context_pruning", {})["debug_dump"] = False
    config._config.setdefault("generation_trace", {})["enabled"] = False

    writer = AIWriter(config)
    parser = parse_outline(config.get_outline_content())
    h2_headings = [heading for heading in parser.get_all_headings() if heading.level == 2]

    lines = [
        f"# H2 摘录核查报告 - {config_path.name}",
        "",
        f"- generated_at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- config_path: {config_path.resolve()}",
        f"- h2_count: {len(h2_headings)}",
        f"- context_pruning_mode: {config.context_pruning_mode}",
        f"- scoring_mode: {config.context_pruning_scoring_mode}",
        f"- requirements_mode: {config.context_pruning_requirements_mode}",
        f"- vector_enabled: {config.context_pruning_retrieval_vector_enabled}",
        f"- rerank_or_verify_enabled: {config.context_pruning_rerank_or_verify_enabled}",
        "",
        "> 说明：以下“采购需求提炼输出”和“评分标准提炼输出”均为当前代码实际拼给模型的 section 文本，不是手工重写。",
        "",
    ]

    for heading in h2_headings:
        prompt_result = writer.build_prompt_result(heading)
        requirement_text = _find_section(prompt_result.prompt_sections, REQUIREMENT_SECTION_NAMES)
        scoring_text = _find_section(prompt_result.prompt_sections, SCORING_SECTION_NAME)
        lines.append(_render_h2_entry(heading, requirement_text, scoring_text, prompt_result.pruned_context))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_report(config_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{_safe_stem(config_path)}__h2_extract_report.md"
    report_path.write_text(build_report(config_path), encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 H2 节点的采购需求/评分标准提炼核查报告")
    parser.add_argument(
        "--config",
        dest="configs",
        action="append",
        default=[],
        help="配置文件路径；可重复传入。默认生成两份 hybrid_extract 测试配置的报告。",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="报告输出目录，默认 output/h2check",
    )
    args = parser.parse_args()

    config_paths = [Path(item) for item in (args.configs or DEFAULT_CONFIGS)]
    output_dir = Path(args.output_dir)

    generated: list[Path] = []
    for config_path in config_paths:
        generated.append(write_report(config_path, output_dir))

    index_lines = [
        "# H2 核查报告索引",
        "",
        f"- generated_at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- output_dir: {output_dir.resolve()}",
        "",
    ]
    for report_path in generated:
        index_lines.append(f"- {report_path.name}")

    (output_dir / "README.md").write_text("\n".join(index_lines).strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
