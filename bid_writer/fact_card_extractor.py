from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from .config import Config
from .fact_cards import FactCardDraft
from .file_saver import FileSaver
from .outline_parser import HeadingNode


class FactCardExtractor:
    """从已保存章节正文中提炼事实卡片草稿。"""

    def __init__(self, config: Config, file_saver: FileSaver):
        self.config = config
        self.file_saver = file_saver

    def extract_from_output(self, heading: HeadingNode, instruction: str = "") -> list[FactCardDraft]:
        filepath = self.file_saver.find_existing_filepath(heading)
        if filepath is None or not filepath.exists():
            return []

        content = self.file_saver.load_section_body(filepath, heading.title).strip()
        if not content:
            return []

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
        except Exception:
            return []

        content_text = self._extract_response_content(response)
        if not content_text:
            return []
        return self.parse_draft_response(content_text)

    @staticmethod
    def build_prompt(*, heading: HeadingNode, chapter_content: str, instruction: str = "") -> str:
        return "\n\n".join(
            [
                "请从以下已保存章节正文中提炼 1 张事实卡片草稿。",
                "输出要求：",
                "1. 仅输出 JSON 数组，不要输出额外说明。",
                "2. 只输出 1 张事实卡片；如果没有明确核心事实，则输出空数组 []。",
                "3. 每项字段包含：name、content，可选 category。",
                "4. 选择最能代表本章节核心内容、最适合后续章节复用或引用的一条事实。",
                "5. 内容必须具体、可验证、信息密度高，避免泛泛总结、修饰性评价和重复表述。",
                f"章节标题：{heading.title}",
                f"章节路径：{heading.full_path}",
                f"用户要求：{instruction.strip() or '提炼最能代表当前章节核心内容的一张事实卡片。'}",
                "章节正文：",
                chapter_content,
            ]
        )

    @classmethod
    def parse_draft_response(cls, content: str) -> list[FactCardDraft]:
        payload = cls._load_json_payload(content)
        if isinstance(payload, dict):
            for key in ("items", "cards", "data"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        if not isinstance(payload, list):
            return []

        drafts: list[FactCardDraft] = []
        for item in payload:
            draft = FactCardDraft.from_dict(item if isinstance(item, dict) else None)
            if draft is not None:
                drafts.append(draft)
                break
        return drafts

    @staticmethod
    def _load_json_payload(content: str) -> Any:
        normalized = str(content or "").strip()
        if not normalized:
            return []
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
            return json.loads(normalized)
        except json.JSONDecodeError:
            return []

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
