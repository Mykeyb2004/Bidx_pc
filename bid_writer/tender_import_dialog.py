"""招标文件导入确认 UI 辅助。"""

from __future__ import annotations

from tkinter import messagebox

from .tender_import_models import (
    ManualTenderConfirmationResult,
    ManualTenderSectionSelection,
    TenderExtractionResult,
    TenderSectionExtraction,
)


def build_low_confidence_preview(extraction: TenderSectionExtraction, *, max_chars: int = 420) -> str:
    parts: list[str] = ["抽取结果置信度偏低，请确认是否写入项目资料文件。"]
    for label, result in (
        ("项目采购需求", extraction.requirements),
        ("评分标准", extraction.scoring),
    ):
        if result is None:
            parts.append(f"\n{label}：未抽取到")
            continue
        parts.append(_format_result(label, result, max_chars=max_chars))
    return "\n".join(parts)


def confirm_low_confidence(parent, extraction: TenderSectionExtraction) -> bool:
    return messagebox.askyesno(
        "确认导入",
        build_low_confidence_preview(extraction),
        parent=parent,
    )


def confirm_extracted_sections_preview(
    parent,
    *,
    extraction: TenderSectionExtraction,
    **_kwargs,
) -> ManualTenderConfirmationResult:
    if not extraction.is_complete:
        return ManualTenderConfirmationResult(cancelled=True)
    if not confirm_low_confidence(parent, extraction):
        return ManualTenderConfirmationResult(cancelled=True)
    return ManualTenderConfirmationResult(
        requirements=ManualTenderSectionSelection(
            section_key="bid_requirements",
            markdown=extraction.requirements.markdown,
            start_block_id=extraction.requirements.start_block_id,
            end_block_id=extraction.requirements.end_block_id,
            manually_adjusted=False,
        ),
        scoring=ManualTenderSectionSelection(
            section_key="scoring_criteria",
            markdown=extraction.scoring.markdown,
            start_block_id=extraction.scoring.start_block_id,
            end_block_id=extraction.scoring.end_block_id,
            manually_adjusted=False,
        ),
        cancelled=False,
    )


def _format_result(label: str, result: TenderExtractionResult, *, max_chars: int) -> str:
    excerpt = result.markdown.strip().replace("\n\n", "\n")
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + "\n..."
    warnings = "；".join(result.warnings) if result.warnings else "无"
    return "\n".join(
        [
            f"\n{label}：{result.confidence:.0%}",
            f"标题：{result.title}",
            f"提示：{warnings}",
            "预览：",
            excerpt,
        ]
    )
