from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from .config import Config
from .fact_cards import FactCardDraft, normalize_fact_card_enforcement, normalize_fact_card_scope
from .file_saver import FileSaver
from .outline_parser import HeadingNode


@dataclass(frozen=True)
class FactCardExtractionResult:
    drafts: list[FactCardDraft]
    message: str = ""
    detail: str = ""
    raw_response_excerpt: str = ""

    def user_message(self) -> str:
        lines = [self.message or "当前未能提炼出可保存的事实卡片草稿。"]
        if self.detail:
            lines.extend(["", "详细信息：", self.detail])
        if self.raw_response_excerpt:
            lines.extend(["", "模型原始返回（截断）：", self.raw_response_excerpt])
        return "\n".join(lines)


class FactCardExtractor:
    """从已保存章节正文中提炼事实卡片草稿。"""

    def __init__(self, config: Config, file_saver: FileSaver):
        self.config = config
        self.file_saver = file_saver

    def extract_from_output(self, heading: HeadingNode, instruction: str = "") -> list[FactCardDraft]:
        return self.extract_from_output_with_diagnostics(heading, instruction).drafts

    def extract_from_output_with_diagnostics(
        self,
        heading: HeadingNode,
        instruction: str = "",
    ) -> FactCardExtractionResult:
        filepath = self.file_saver.find_existing_filepath(heading)
        if filepath is None or not filepath.exists():
            return FactCardExtractionResult(
                drafts=[],
                message="未找到该章节的已生成正文文件。",
                detail=f"章节：{heading.full_path or heading.title}\n请先生成该章节正文后再提炼事实卡片。",
            )

        content = self.file_saver.load_section_body(filepath, heading.title).strip()
        if not content:
            return FactCardExtractionResult(
                drafts=[],
                message="已找到正文文件，但未读取到该章节正文。",
                detail=(
                    f"文件：{filepath}\n"
                    f"章节标题：{heading.title}\n"
                    "可能原因：输出文件中章节标题不匹配，或该章节正文为空。"
                ),
            )

        client, model = self._get_client_and_model()
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": "你是标书事实卡片提炼助手，只返回 JSON 数组。"},
                    {
                        "role": "user",
                        "content": self.build_prompt(
                            heading=heading,
                            chapter_content=content,
                            instruction=instruction,
                        ),
                    },
                ],
            )
        except Exception as exc:
            return FactCardExtractionResult(
                drafts=[],
                message="调用模型提炼事实卡片失败。",
                detail=f"{exc.__class__.__name__}: {exc}",
            )

        content_text = self._extract_response_content(response)
        if not content_text:
            return FactCardExtractionResult(
                drafts=[],
                message="模型响应为空，无法提炼事实卡片。",
                detail="接口已返回响应，但未包含 choices[0].message.content 内容。",
            )
        return self.parse_draft_response_with_diagnostics(content_text)

    @staticmethod
    def build_prompt(*, heading: HeadingNode, chapter_content: str, instruction: str = "") -> str:
        return "\n\n".join(
            [
                "请从以下已保存章节正文中提炼 1 张事实卡片草稿。",
                "输出要求：",
                "1. 仅输出 JSON 数组，不要输出额外说明。",
                "2. 只输出 1 张事实卡片；如果没有明确核心事实，则输出空数组 []。",
                "3. 每项字段必须包含：name、content、scope、enforcement，可选 category。",
                "4. scope 只能是 global 或 local：主体信息、资质能力、统一承诺、全项目通用要求用 global；只适用于当前章节主题、局部措施、局部流程的内容用 local。",
                "5. enforcement 只能是 strong 或 reference：必须全文一致、不能被改写成相反含义的信息用 strong；仅供借鉴、可按章节选择性吸收的信息用 reference。",
                "6. 选择最能代表本章节核心内容、最适合后续章节复用或引用的一条事实。",
                "7. 内容必须具体、可验证、信息密度高，避免泛泛总结、修饰性评价和重复表述。",
                f"章节标题：{heading.title}",
                f"章节路径：{heading.full_path}",
                f"用户要求：{instruction.strip() or '提炼最能代表当前章节核心内容的一张事实卡片。'}",
                "章节正文：",
                chapter_content,
            ]
        )

    @classmethod
    def parse_draft_response(cls, content: str) -> list[FactCardDraft]:
        return cls.parse_draft_response_with_diagnostics(content).drafts

    @classmethod
    def parse_draft_response_with_diagnostics(cls, content: str) -> FactCardExtractionResult:
        payload, json_error, normalized = cls._load_json_payload_with_diagnostics(content)
        if json_error:
            return FactCardExtractionResult(
                drafts=[],
                message="模型返回不是合法 JSON，无法解析事实卡片。",
                detail=json_error,
                raw_response_excerpt=cls._excerpt(normalized),
            )
        if isinstance(payload, dict):
            for key in ("items", "cards", "data"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
            else:
                return FactCardExtractionResult(
                    drafts=[],
                    message="模型返回了 JSON 对象，但没有可识别的卡片列表。",
                    detail="期望字段：items、cards 或 data，且字段值应为数组。",
                    raw_response_excerpt=cls._excerpt(normalized),
                )
        if not isinstance(payload, list):
            return FactCardExtractionResult(
                drafts=[],
                message="模型返回的 JSON 不是数组，无法提炼事实卡片。",
                detail=f"实际 JSON 类型：{type(payload).__name__}。",
                raw_response_excerpt=cls._excerpt(normalized),
            )

        if not payload:
            return FactCardExtractionResult(
                drafts=[],
                message="模型返回空数组，表示未识别到明确核心事实。",
                detail="可尝试在提炼要求中指定要提取的资质、人员、工期、服务承诺、业绩等具体事实。",
                raw_response_excerpt=cls._excerpt(normalized),
            )

        drafts: list[FactCardDraft] = []
        invalid_reasons: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                invalid_reasons.append("存在非对象数组项。")
                continue
            draft = FactCardDraft.from_dict(item if isinstance(item, dict) else None)
            if draft is not None:
                drafts.append(draft)
                break
            missing_fields = []
            if not str(item.get("name", "") or "").strip():
                missing_fields.append("name")
            if not str(item.get("content", item.get("value", "")) or "").strip():
                missing_fields.append("content")
            if not str(item.get("scope", "") or "").strip():
                missing_fields.append("scope")
            if not str(item.get("enforcement", "") or "").strip():
                missing_fields.append("enforcement")
            if missing_fields:
                invalid_reasons.append(f"存在缺少 {'、'.join(missing_fields)} 字段的数组项。")
            scope_value = str(item.get("scope", "") or "").strip()
            enforcement_value = str(item.get("enforcement", "") or "").strip()
            if scope_value and not normalize_fact_card_scope(scope_value):
                invalid_reasons.append("存在 scope 取值不是 global/local 的数组项。")
            if enforcement_value and not normalize_fact_card_enforcement(enforcement_value):
                invalid_reasons.append("存在 enforcement 取值不是 strong/reference 的数组项。")
        if drafts:
            return FactCardExtractionResult(drafts=drafts)
        return FactCardExtractionResult(
            drafts=[],
            message="模型返回了数组，但没有包含可保存的事实卡片。",
            detail="；".join(dict.fromkeys(invalid_reasons)) or "每张卡片都必须同时包含非空 name 和 content。",
            raw_response_excerpt=cls._excerpt(normalized),
        )

    @staticmethod
    def _load_json_payload(content: str) -> Any:
        payload, _json_error, _normalized = FactCardExtractor._load_json_payload_with_diagnostics(content)
        return payload

    @staticmethod
    def _load_json_payload_with_diagnostics(content: str) -> tuple[Any, str, str]:
        normalized = str(content or "").strip()
        if not normalized:
            return [], "", normalized
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[0].strip().lower() == "json":
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            normalized = "\n".join(lines).strip()
        if normalized.lower().startswith("json\n"):
            normalized = normalized.split("\n", 1)[1].strip()
        try:
            return json.loads(normalized), "", normalized
        except json.JSONDecodeError as exc:
            return (
                [],
                f"解析错误：{exc.msg}（第 {exc.lineno} 行，第 {exc.colno} 列）。",
                normalized,
            )

    @staticmethod
    def _excerpt(text: str, limit: int = 800) -> str:
        normalized = str(text or "").strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit].rstrip() + "..."

    @staticmethod
    def _extract_response_content(response: Any) -> str:
        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            return ""

        message = getattr(choices[0], "message", None)
        if message is None:
            return ""

        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            segments: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text", "")
                else:
                    text = getattr(item, "text", "")
                text = str(text or "").strip()
                if text:
                    segments.append(text)
            return "\n".join(segments).strip()
        return str(content or "").strip()

    def _get_client_and_model(self) -> tuple[OpenAI, str]:
        client = OpenAI(
            base_url=self.config.api_base_url,
            api_key=self.config.api_key,
            timeout=self.config.api_timeout_seconds,
            max_retries=self.config.api_max_retries,
        )
        return client, self.config.model
