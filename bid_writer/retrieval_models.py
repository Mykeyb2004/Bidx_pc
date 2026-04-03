"""
检索摘录链路的数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SourceUnit:
    """统一的源文片段。"""

    unit_id: str
    doc_type: str
    section_path: str
    block_type: str
    title: str = ""
    weight_text: str = ""
    source_text: str = ""
    source_text_exact: str = ""
    order_index: int = 0


@dataclass
class RetrievedUnit:
    """一次召回命中的候选片段。"""

    unit: SourceUnit
    lexical_score: float = 0.0
    vector_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class ExtractedQuote:
    """最终选中的原文摘录。"""

    unit_id: str
    doc_type: str
    section_path: str
    title: str = ""
    quote: str = ""
    score: float = 0.0
