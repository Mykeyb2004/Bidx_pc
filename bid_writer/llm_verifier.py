"""
可选的候选精排 / 校验器。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI

from .config import Config
from .retrieval_models import RetrievedUnit


@dataclass
class VerificationResult:
    selected_ids: list[str]
    raw_text: str = ""
    error: str = ""


class LLMVerifier:
    """在少量候选上做可选精排，只返回候选 ID。"""

    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(
            base_url=config.pruning_api_base_url,
            api_key=config.pruning_api_key,
            timeout=config.pruning_timeout_seconds,
            max_retries=config.pruning_max_retries,
        )

    def verify(
        self,
        *,
        heading_path: str,
        heading_title: str,
        response_labels: list[str],
        focus_terms: list[str],
        candidates: list[RetrievedUnit],
        limit: int,
    ) -> VerificationResult:
        if not candidates:
            return VerificationResult(selected_ids=[])

        truncated = candidates[:limit]
        prompt = self._build_prompt(
            heading_path=heading_path,
            heading_title=heading_title,
            response_labels=response_labels,
            focus_terms=focus_terms,
            candidates=truncated,
        )
        try:
            response = self.client.chat.completions.create(
                model=self.config.pruning_model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": "你是检索候选校验器。只允许从候选中选择最相关的原文片段 ID，不要改写原文，不要输出解释。",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            selected_ids = self._parse_selected_ids(text, {item.unit.unit_id for item in truncated})
            return VerificationResult(selected_ids=selected_ids, raw_text=text)
        except Exception as exc:
            return VerificationResult(selected_ids=[], error=str(exc))

    def _build_prompt(
        self,
        *,
        heading_path: str,
        heading_title: str,
        response_labels: list[str],
        focus_terms: list[str],
        candidates: list[RetrievedUnit],
    ) -> str:
        lines = [
            "请从以下候选片段中，选出最适合当前章节写作依据的候选 ID。",
            "必须只返回 JSON，对象格式为：{\"selected_ids\": [\"id1\", \"id2\"]}",
            "不要返回任何额外说明。",
            "",
            f"章节标题：{heading_title}",
            f"章节路径：{heading_path}",
            f"响应标签：{'；'.join(response_labels) if response_labels else '（无）'}",
            f"焦点词：{'；'.join(focus_terms) if focus_terms else '（无）'}",
            "",
            "候选如下：",
        ]
        for item in candidates:
            unit = item.unit
            lines.extend(
                [
                    f"- id: {unit.unit_id}",
                    f"  section_path: {unit.section_path or '（无）'}",
                    f"  title: {unit.title or '（无）'}",
                    f"  weight: {unit.weight_text or '（无）'}",
                    f"  score: {item.fused_score:.4f}",
                    f"  text: {unit.source_text_exact or unit.source_text}",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _parse_selected_ids(text: str, valid_ids: set[str]) -> list[str]:
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end < start:
                return []
            try:
                payload = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return []

        values = payload.get("selected_ids", [])
        selected: list[str] = []
        seen: set[str] = set()
        if not isinstance(values, list):
            return []
        for value in values:
            normalized = str(value).strip()
            if normalized in valid_ids and normalized not in seen:
                seen.add(normalized)
                selected.append(normalized)
        return selected
