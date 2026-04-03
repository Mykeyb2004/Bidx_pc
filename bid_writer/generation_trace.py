"""
章节生成 trace 日志系统
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .config import Config
from .context_pruner import ChapterContext
from .outline_parser import HeadingNode


def _sanitize_path_component(text: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", text)
    sanitized = re.sub(r"[\s_]+", "_", sanitized).strip("._ ")
    return sanitized or "untitled"


def _utc_now_string() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class GenerationTraceSession:
    """单次章节生成的 trace 会话。"""

    def __init__(
        self,
        config: Config,
        heading: HeadingNode,
        additional_requirements: str,
        min_words: int,
        stream: bool,
        system_prompt: str,
        user_prompt: str,
        prompt_sections: list[dict[str, Any]],
        prompt_contract_blocks: list[dict[str, Any]],
        context_mode: str,
        pruned_context: Optional[ChapterContext],
        full_context_stats: dict[str, Any],
        request_options: dict[str, Any],
    ):
        self.config = config
        self.heading = heading
        self.additional_requirements = additional_requirements
        self.min_words = min_words
        self.stream = stream
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.prompt_sections = prompt_sections
        self.prompt_contract_blocks = prompt_contract_blocks
        self.context_mode = context_mode
        self.pruned_context = pruned_context
        self.full_context_stats = full_context_stats
        self.request_options = request_options
        self.trace_id = self._build_trace_id()
        self.created_at = _utc_now_string()
        self.completed_at: Optional[str] = None
        self.status = "running"
        self.postprocess: dict[str, Any] = {}
        self._finished = False

        self.trace_dir = self._build_trace_dir()
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_paths = {
            "manifest": self.trace_dir / "manifest.json",
            "heading": self.trace_dir / "01_heading.json",
            "context_assembly": self.trace_dir / "02_context_assembly.json",
            "prompt_system": self.trace_dir / "03_prompt_system.md",
            "prompt_user": self.trace_dir / "04_prompt_user.md",
            "request_options": self.trace_dir / "05_request_options.json",
            "generation_output": self.trace_dir / "06_generation_output.md",
            "summary": self.trace_dir / "07_summary.md",
        }
        self._write_initial_artifacts()

    @property
    def finished(self) -> bool:
        return self._finished

    def _build_trace_id(self) -> str:
        seed = "|".join(
            [
                self.heading.full_path,
                self.heading.title,
                str(self.min_words),
                self.additional_requirements.strip(),
                str(self.stream),
                _utc_now_string(),
            ]
        )
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    def _build_trace_dir(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title_slug = _sanitize_path_component(self.heading.title)[:32]
        root = Path(self.config.generation_trace_directory)
        return root / f"{timestamp}__{title_slug}__{self.trace_id}"

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_text(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def _sanitize_request_options(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.request_options.get("model", ""),
            "temperature": self.request_options.get("temperature"),
            "max_tokens": self.request_options.get("max_tokens"),
            "stream": self.request_options.get("stream"),
        }
        if "top_p" in self.request_options:
            payload["top_p"] = self.request_options.get("top_p")
        if "seed" in self.request_options:
            payload["seed"] = self.request_options.get("seed")

        if not self.config.generation_trace_redact_sensitive:
            payload["api_base_url"] = self.config.api_base_url
        else:
            parsed = urlparse(self.config.api_base_url)
            payload["api_base_url_host"] = parsed.hostname or parsed.netloc or ""
        return payload

    def _build_heading_payload(self) -> dict[str, Any]:
        return {
            "title": self.heading.title,
            "full_path": self.heading.full_path,
            "level": self.heading.level,
            "line_number": self.heading.line_number,
            "additional_requirements": self.additional_requirements,
            "min_words": self.min_words,
            "stream": self.stream,
        }

    def _build_context_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "context_mode": self.context_mode,
            "context_pruning_enabled": self.config.context_pruning_enabled,
            "prompt_contract": {
                "block_order": [block.get("id", "") for block in self.prompt_contract_blocks],
                "blocks": [
                    {
                        "id": block.get("id", ""),
                        "label": block.get("label", ""),
                        "prompt_kind": block.get("prompt_kind", ""),
                        "section_names": list(block.get("section_names", [])),
                        "source_context": list(block.get("source_context", [])),
                        "chars": int(block.get("chars", 0)),
                    }
                    for block in self.prompt_contract_blocks
                ],
            },
            "prompt_sections": [
                {
                    "name": section.get("name", ""),
                    "chars": len(section.get("content", "")),
                }
                for section in self.prompt_sections
            ],
            "prompt_lengths": {
                "system_prompt_chars": len(self.system_prompt),
                "user_prompt_chars": len(self.user_prompt),
            },
        }

        if self.pruned_context is not None:
            payload["pruned_context"] = asdict(self.pruned_context)
        else:
            payload["full_context"] = self.full_context_stats
        return payload

    def _build_manifest(self, output_chars: int = 0, error: str = "") -> dict[str, Any]:
        artifacts = {
            name: path.name
            for name, path in self.artifact_paths.items()
            if path.exists() or name in {"manifest", "heading", "request_options"}
        }
        return {
            "trace_id": self.trace_id,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "config_path": str(self.config.config_path.resolve()),
            "heading_title": self.heading.title,
            "heading_full_path": self.heading.full_path,
            "heading_level": self.heading.level,
            "context_mode": self.context_mode,
            "context_pruning_enabled": self.config.context_pruning_enabled,
            "generation_trace_mode": self.config.generation_trace_mode,
            "request": self._sanitize_request_options(),
            "prompt_lengths": {
                "system_prompt_chars": len(self.system_prompt),
                "user_prompt_chars": len(self.user_prompt),
            },
            "postprocess": self.postprocess,
            "output_chars": output_chars,
            "error": error,
            "artifacts": artifacts,
        }

    def _write_initial_artifacts(self) -> None:
        self._write_json(self.artifact_paths["manifest"], self._build_manifest())
        self._write_json(self.artifact_paths["heading"], self._build_heading_payload())
        self._write_json(self.artifact_paths["request_options"], self._sanitize_request_options())

        if self.config.generation_trace_write_context:
            self._write_json(self.artifact_paths["context_assembly"], self._build_context_payload())

        if self.config.generation_trace_write_prompt:
            self._write_text(self.artifact_paths["prompt_system"], self.system_prompt)
            self._write_text(self.artifact_paths["prompt_user"], self.user_prompt)

    def _build_output_document(self, output_text: str, error: str = "") -> str:
        lines = [
            f"# 章节生成结果 - {self.heading.title}",
            "",
            f"- trace_id: {self.trace_id}",
            f"- status: {self.status}",
            f"- created_at: {self.created_at}",
            f"- completed_at: {self.completed_at or '（未完成）'}",
            f"- output_chars: {len(output_text)}",
        ]
        if error:
            lines.append(f"- error: {error}")
        if self.postprocess:
            issues = self.postprocess.get("format_repair_issues") or []
            lines.extend(
                [
                    f"- bidder_reference_normalized: {self.postprocess.get('bidder_reference_normalized', False)}",
                    f"- bidder_reference_replacements: {self.postprocess.get('bidder_reference_replacements', 0)}",
                    f"- format_repair_applied: {self.postprocess.get('format_repair_applied', False)}",
                    f"- format_repair_issues: {', '.join(issues) if issues else '（无）'}",
                ]
            )
        lines.extend(
            [
                "",
                "## 正文输出",
                output_text or "（无输出）",
            ]
        )
        return "\n".join(lines)

    def _build_summary(self, output_text: str, error: str = "") -> str:
        lines = [
            "# 章节生成 Trace 摘要",
            "",
            f"- trace_id: {self.trace_id}",
            f"- 标题: {self.heading.title}",
            f"- full_path: {self.heading.full_path}",
            f"- status: {self.status}",
            f"- context_mode: {self.context_mode}",
            f"- system_prompt_chars: {len(self.system_prompt)}",
            f"- user_prompt_chars: {len(self.user_prompt)}",
            f"- output_chars: {len(output_text)}",
        ]
        if self.prompt_contract_blocks:
            lines.append(
                "- prompt_contract_blocks: "
                + ", ".join(block.get("id", "") for block in self.prompt_contract_blocks if block.get("id"))
            )
        if self.postprocess:
            issues = self.postprocess.get("format_repair_issues") or []
            lines.extend(
                [
                    f"- bidder_reference_normalized: {self.postprocess.get('bidder_reference_normalized', False)}",
                    f"- bidder_reference_replacements: {self.postprocess.get('bidder_reference_replacements', 0)}",
                    f"- format_repair_applied: {self.postprocess.get('format_repair_applied', False)}",
                    f"- format_repair_issues: {', '.join(issues) if issues else '（无）'}",
                ]
            )

        if self.pruned_context is not None:
            lines.extend(
                [
                    f"- retrieval_mode: {self.pruned_context.retrieval_mode or '（无）'}",
                    f"- fallback_reason: {self.pruned_context.fallback_reason or '（无）'}",
                    f"- response_labels: {', '.join(self.pruned_context.response_labels) if self.pruned_context.response_labels else '（无）'}",
                    f"- scoring_items: {len(self.pruned_context.scoring_items)}",
                    f"- requirement_blocks: {len(self.pruned_context.requirement_blocks)}",
                    f"- requirement_seed_chars: {len(self.pruned_context.requirement_seed)}",
                    f"- requirement_brief_chars: {len(self.pruned_context.requirement_brief)}",
                    f"- requirement_brief_status: {self.pruned_context.requirement_brief_status or '（无）'}",
                ]
            )
        else:
            lines.extend(
                [
                    f"- outline_chars: {self.full_context_stats.get('outline_chars', 0)}",
                    f"- bid_requirements_chars: {self.full_context_stats.get('bid_requirements_chars', 0)}",
                    f"- scoring_criteria_chars: {self.full_context_stats.get('scoring_criteria_chars', 0)}",
                ]
            )

        if error:
            lines.extend(["", "## 异常", error])

        lines.extend(
            [
                "",
                "## Prompt Contract",
                *[
                    "- "
                    + block.get("id", "")
                    + ": "
                    + (
                        ", ".join(block.get("section_names", []))
                        if block.get("section_names")
                        else "system-only"
                    )
                    + " | source_context="
                    + ", ".join(block.get("source_context", []))
                    for block in self.prompt_contract_blocks
                ],
                "",
                "## 产物文件",
                "\n".join(
                    f"- {name}: {path.name}"
                    for name, path in self.artifact_paths.items()
                    if path.exists() or name in {"manifest", "heading", "request_options"}
                ),
            ]
        )
        return "\n".join(lines)

    def finalize(
        self,
        output_text: str,
        status: str = "completed",
        error: str = "",
        postprocess: Optional[dict[str, Any]] = None,
    ) -> None:
        if self._finished:
            return

        self._finished = True
        self.status = status
        self.completed_at = _utc_now_string()
        if postprocess:
            self.postprocess = postprocess

        if self.config.generation_trace_write_output:
            self._write_text(
                self.artifact_paths["generation_output"],
                self._build_output_document(output_text, error),
            )

        if self.config.generation_trace_write_summary:
            self._write_text(
                self.artifact_paths["summary"],
                self._build_summary(output_text, error),
            )

        self._write_json(
            self.artifact_paths["manifest"],
            self._build_manifest(output_chars=len(output_text), error=error),
        )


class GenerationTraceLogger:
    """负责创建章节生成 trace 会话。"""

    def __init__(self, config: Config):
        self.config = config

    def start_session(
        self,
        heading: HeadingNode,
        additional_requirements: str,
        min_words: int,
        stream: bool,
        system_prompt: str,
        user_prompt: str,
        prompt_sections: list[dict[str, Any]],
        prompt_contract_blocks: list[dict[str, Any]],
        context_mode: str,
        pruned_context: Optional[ChapterContext],
        full_context_stats: dict[str, Any],
        request_options: dict[str, Any],
    ) -> Optional[GenerationTraceSession]:
        if not self.config.generation_trace_enabled:
            return None

        return GenerationTraceSession(
            config=self.config,
            heading=heading,
            additional_requirements=additional_requirements,
            min_words=min_words,
            stream=stream,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            prompt_sections=prompt_sections,
            prompt_contract_blocks=prompt_contract_blocks,
            context_mode=context_mode,
            pruned_context=pruned_context,
            full_context_stats=full_context_stats,
            request_options=request_options,
        )
