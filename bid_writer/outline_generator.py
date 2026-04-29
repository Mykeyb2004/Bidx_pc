"""
标书大纲生成服务。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI

from .config import Config
from .config_editor import ValidationMessage
from .outline_parser import parse_outline


@dataclass(frozen=True)
class OutlineGenerationResult:
    outline_text: str
    warnings: list[str] = field(default_factory=list)


class OutlineGenerationError(RuntimeError):
    """大纲生成无法继续。"""


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE_RE = re.compile(r"^\s*```")


def clean_outline_response(raw_text: str) -> OutlineGenerationResult:
    lines: list[str] = []
    downgraded = 0

    for raw_line in raw_text.splitlines():
        if _FENCE_RE.match(raw_line):
            continue
        match = _HEADING_RE.match(raw_line.strip())
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        if not title:
            continue
        if level > 4:
            level = 4
            downgraded += 1
        lines.append(f"{'#' * level} {title}")

    warnings: list[str] = []
    if downgraded:
        warnings.append(f"已将 {downgraded} 个 H5/H6 标题降级为 H4。")
    outline_text = "\n".join(lines).strip()
    return OutlineGenerationResult(
        outline_text=(outline_text + "\n") if outline_text else "",
        warnings=warnings,
    )


def validate_outline_text(outline_text: str) -> list[ValidationMessage]:
    messages: list[ValidationMessage] = []
    raw_heading_levels: list[int] = []

    for line_number, raw_line in enumerate(outline_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = _HEADING_RE.match(stripped)
        if not match:
            messages.append(ValidationMessage("warning", f"第 {line_number} 行不是 Markdown 标题，将不会进入大纲树。"))
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        raw_heading_levels.append(level)
        if not title:
            messages.append(ValidationMessage("error", f"第 {line_number} 行标题为空。"))
        if level > 4:
            messages.append(ValidationMessage("error", f"第 {line_number} 行为 H{level}，大纲固定到 H4，不允许 H5/H6。"))

    parser = parse_outline(outline_text)
    headings = parser.get_all_headings()
    if not headings:
        messages.append(ValidationMessage("error", "大纲至少需要 1 个 Markdown 标题。"))
        return messages
    if not any(heading.level == 1 for heading in headings):
        messages.append(ValidationMessage("error", "大纲至少需要 1 个 H1 项目总标题。"))
    if not any(heading.level == 4 for heading in headings):
        messages.append(ValidationMessage("error", "大纲至少包含 1 个 H4 具体写作单元。"))
    for heading in headings:
        if not heading.children and heading.level != 4:
            messages.append(ValidationMessage("error", f"叶子节点必须是 H4：{heading.full_path}"))
    if raw_heading_levels and max(raw_heading_levels) <= 4 and not any(item.level == "error" for item in messages):
        messages.append(ValidationMessage("info", f"已识别 {len(headings)} 个标题节点。"))
    return messages


class OutlineGenerator:
    def __init__(
        self,
        config: Config,
        *,
        client_factory: Optional[Callable[..., OpenAI]] = None,
    ):
        self.config = config
        self.client_factory = client_factory or OpenAI

    def generate(self) -> OutlineGenerationResult:
        role = self._load_role()
        bid_requirements = self.config.bid_requirements.strip()
        scoring_criteria = self.config.scoring_criteria.strip()
        if not bid_requirements and not scoring_criteria:
            raise OutlineGenerationError("采购需求和评分标准均为空，无法生成大纲。")

        client = self.client_factory(
            base_url=self.config.outline_api_base_url,
            api_key=self.config.outline_api_key,
            timeout=self.config.outline_timeout_seconds,
            max_retries=self.config.outline_max_retries,
        )
        options = {
            "model": self.config.outline_model,
            "temperature": self.config.outline_temperature,
            "max_tokens": self.config.outline_max_tokens,
            "stream": False,
            "messages": [
                {"role": "system", "content": role},
                {"role": "user", "content": self.build_user_prompt()},
            ],
        }
        if self.config.outline_top_p is not None:
            options["top_p"] = self.config.outline_top_p
        if self.config.outline_seed is not None:
            options["seed"] = self.config.outline_seed

        try:
            response = client.chat.completions.create(**options)
        except Exception as exc:
            raise OutlineGenerationError(f"大纲生成请求失败：{type(exc).__name__}: {exc}") from exc

        raw_text = self._extract_response_text(response)
        if not raw_text.strip():
            raise OutlineGenerationError("大纲生成返回为空。")
        result = clean_outline_response(raw_text)
        if not result.outline_text.strip():
            raise OutlineGenerationError("大纲生成结果中未识别到 Markdown 标题。")
        return result

    def _load_role(self) -> str:
        role_path = Path(self.config.outline_generation_role_file)
        if not role_path.exists():
            raise OutlineGenerationError(f"大纲生成角色文件不存在：{role_path}")
        return role_path.read_text(encoding="utf-8").strip()

    def build_user_prompt(self) -> str:
        bidder_name = self.config.prompt_bidder_name or "当前投标主体"
        project_title = self._infer_project_title()
        bid_requirements = self.config.bid_requirements.strip() or "（未提供采购需求）"
        scoring_criteria = self.config.scoring_criteria.strip() or "（未提供评分标准）"
        return "\n\n".join(
            [
                "## 当前任务",
                f"请为{bidder_name}的“{project_title}”生成投标文件目录大纲。",
                "## 采购需求",
                bid_requirements,
                "## 评分标准",
                scoring_criteria,
                "## 输出契约",
                "\n".join(
                    [
                        "你只输出 Markdown 标题大纲，不输出正文、说明、前言、代码块或补充解释。",
                        "标题层级必须固定到 H4：",
                        "# 项目或标书总标题",
                        "## 一级章，优先对应评分大项或标书一级章",
                        "### 二级节，承接一级章下的核心板块",
                        "#### 具体写作单元，作为后续章节扩写的叶子节点",
                        "每个 ### 下至少包含 1 个 ####。",
                        "不得输出 ##### 或更深层级标题。",
                        "标题应保留评分标准中的关键词原词，目录顺序原则上遵循评分标准顺序。",
                        "如果评分标准缺失，则依据采购需求提炼目录逻辑。",
                    ]
                ),
            ]
        )

    def _infer_project_title(self) -> str:
        try:
            outline_text = self.config.get_outline_content()
        except Exception:
            return "投标文件"
        parser = parse_outline(outline_text)
        for heading in parser.get_all_headings():
            if heading.level == 1 and heading.title.strip():
                return heading.title.strip()
        return "投标文件"

    @staticmethod
    def _extract_response_text(response) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        if message is None:
            return ""
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text", "")
                else:
                    text = getattr(item, "text", "")
                if text:
                    parts.append(str(text))
            return "\n".join(parts)
        return str(content or "")
