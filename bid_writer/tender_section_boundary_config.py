"""招标文件章节边界规则加载。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Literal

import yaml


DEFAULT_BOUNDARY_CONFIG_PATH = Path(__file__).resolve().parents[1] / "roles" / "tender_section_boundaries.yaml"


@dataclass(frozen=True)
class TenderSectionBoundaryRule:
    name: str
    kind: Literal["major", "fallback"]
    priority: int
    pattern: str
    regex: re.Pattern[str]


@dataclass(frozen=True)
class TenderSectionBoundaryMatch:
    block_id: str
    block_index: int
    kind: Literal["major", "fallback"]
    rule_name: str
    priority: int
    marker_text: str
    ordinal: str
    title: str
    normalized_text: str


@dataclass(frozen=True)
class TenderSectionBoundaryConfig:
    normalization: dict[str, bool] = field(default_factory=dict)
    major_markers: tuple[TenderSectionBoundaryRule, ...] = ()
    fallback_markers: tuple[TenderSectionBoundaryRule, ...] = ()
    warnings: tuple[str, ...] = ()


def normalize_boundary_text(
    text: str,
    *,
    strip_invisible: bool = True,
    collapse_space: bool = True,
) -> str:
    text = text.replace("\ufeff", "")
    if strip_invisible:
        text = re.sub(r"[\u200b-\u200f\u2060]", "", text)
    text = text.replace("\u3000", " ")
    if collapse_space:
        text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_boundary_config(path: str | Path | None = None) -> TenderSectionBoundaryConfig:
    boundary_path = Path(path or DEFAULT_BOUNDARY_CONFIG_PATH).expanduser()
    if not boundary_path.exists():
        return TenderSectionBoundaryConfig(warnings=(f"章节边界配置不存在：{boundary_path}",))

    payload = yaml.safe_load(boundary_path.read_text(encoding="utf-8")) or {}
    warnings: list[str] = []
    major_markers = _load_rules(payload.get("major_markers", []), kind="major", warnings=warnings)
    fallback_markers = _load_rules(payload.get("fallback_markers", []), kind="fallback", warnings=warnings)
    normalization = dict(payload.get("normalization", {}) or {})
    return TenderSectionBoundaryConfig(
        normalization=normalization,
        major_markers=tuple(major_markers),
        fallback_markers=tuple(fallback_markers),
        warnings=tuple(warnings),
    )


def _load_rules(
    items: list[dict[str, object]],
    *,
    kind: Literal["major", "fallback"],
    warnings: list[str],
) -> list[TenderSectionBoundaryRule]:
    rules: list[TenderSectionBoundaryRule] = []
    for item in items:
        name = str(item.get("name", "")).strip()
        pattern = str(item.get("pattern", "")).strip()
        priority = int(item.get("priority", 0) or 0)
        if not name or not pattern:
            warnings.append(f"章节边界规则缺少 name 或 pattern：{item!r}")
            continue
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            warnings.append(f"章节边界规则 {name} 编译失败：{exc}")
            continue
        rules.append(
            TenderSectionBoundaryRule(
                name=name,
                kind=kind,
                priority=priority,
                pattern=pattern,
                regex=regex,
            )
        )
    return rules
