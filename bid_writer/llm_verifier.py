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


@dataclass
class ScoringClassification:
    """评分项分类结果：必需响应 / 参考。"""

    must_respond_ids: list[str]
    reference_ids: list[str]
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

    def classify_scoring(
        self,
        *,
        heading_path: str,
        heading_title: str,
        response_labels: list[str],
        focus_terms: list[str],
        all_scoring_items: list[dict],
        sibling_titles: list[str] | None = None,
    ) -> ScoringClassification:
        """将评分项分为必需响应和参考两类。"""
        if not all_scoring_items:
            return ScoringClassification(must_respond_ids=[], reference_ids=[])

        all_ids = [item["id"] for item in all_scoring_items]
        prompt = self._build_classify_prompt(
            heading_path=heading_path,
            heading_title=heading_title,
            response_labels=response_labels,
            focus_terms=focus_terms,
            items=all_scoring_items,
            sibling_titles=sibling_titles or [],
        )
        try:
            response = self.client.chat.completions.create(
                model=self.config.pruning_model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": '你是评分标准分类器。将评分项分为与章节直接相关的"必须响应"和间接相关的"参考"两类。只返回 JSON。',
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            return self._parse_classification(text, set(all_ids))
        except Exception as exc:
            return ScoringClassification(
                must_respond_ids=list(all_ids),
                reference_ids=[],
                error=str(exc),
            )

    @staticmethod
    def _build_classify_prompt(
        *,
        heading_path: str,
        heading_title: str,
        response_labels: list[str],
        focus_terms: list[str],
        items: list[dict],
        sibling_titles: list[str],
    ) -> str:
        sibling_text = (
            "；".join(sibling_titles) if sibling_titles else "（无）"
        )
        lines = [
            "请将以下评分项分为两类：",
            '必须响应：评分项的考察重点与当前章节"' + heading_title + '"的核心内容直接对应，'
            "正文必须明确覆盖该评分项的要求。",
            "参考：评分项与当前章节间接相关，或其考察重点主要由同级其他章节负责覆盖，"
            "本章可适当体现但无需专门论述。",
            "",
            "判断标准：",
            "- 若一个评分项的考察内容在同级其他章节标题中有更直接的对应，归为参考。",
            "- 若一个评分项属于整体方案的通用要求（而非当前章节的专属职责），归为参考。",
            "- 仅当评分项的主要考察点就是当前章节的核心主题时，才归为必须响应。",
            "",
            '只返回 JSON：{"must_respond": ["id1", ...], "reference": ["id2", ...]}',
            "不要返回任何额外说明。",
            "",
            f"当前扩写章节：{heading_title}",
            f"章节完整路径：{heading_path}",
            f"响应标签：{'；'.join(response_labels) if response_labels else '（无）'}",
            f"焦点词：{'；'.join(focus_terms) if focus_terms else '（无）'}",
            f"同级章节（已由这些章节各自负责）：{sibling_text}",
            "",
            "评分项：",
        ]
        for item in items:
            lines.extend([
                f"- id: {item['id']}",
                f"  subitem: {item.get('subitem', '')}",
                f"  standard: {item.get('standard', '')}",
                f"  weight: {item.get('weight', '')}",
            ])
        return "\n".join(lines)

    @staticmethod
    def _parse_classification(text: str, valid_ids: set[str]) -> ScoringClassification:
        if not text:
            return ScoringClassification(
                must_respond_ids=list(valid_ids), reference_ids=[]
            )
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end < start:
                return ScoringClassification(
                    must_respond_ids=list(valid_ids), reference_ids=[], raw_text=text
                )
            try:
                payload = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return ScoringClassification(
                    must_respond_ids=list(valid_ids), reference_ids=[], raw_text=text
                )

        def extract_ids(key: str) -> list[str]:
            values = payload.get(key, [])
            if not isinstance(values, list):
                return []
            result: list[str] = []
            seen: set[str] = set()
            for v in values:
                normalized = str(v).strip()
                if normalized in valid_ids and normalized not in seen:
                    seen.add(normalized)
                    result.append(normalized)
            return result

        must = extract_ids("must_respond")
        ref = extract_ids("reference")
        if not must and not ref:
            return ScoringClassification(
                must_respond_ids=list(valid_ids), reference_ids=[], raw_text=text
            )
        return ScoringClassification(
            must_respond_ids=must, reference_ids=ref, raw_text=text
        )

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
