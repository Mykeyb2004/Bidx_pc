from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PathPurpose(str, Enum):
    TENDER = "tender"
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"


@dataclass(frozen=True)
class FileDialogOptions:
    filetypes: tuple[tuple[str, str], ...]
    defaultextension: str | None = None


_SUFFIXES: dict[PathPurpose, tuple[str, ...]] = {
    PathPurpose.TENDER: (".pdf", ".docx", ".doc", ".xlsx", ".xls"),
    PathPurpose.MARKDOWN: (".md",),
    PathPurpose.JSON: (".json",),
    PathPurpose.YAML: (".yaml", ".yml"),
}

_DIALOG_OPTIONS: dict[PathPurpose, FileDialogOptions] = {
    PathPurpose.TENDER: FileDialogOptions(
        filetypes=(
            ("招标文件", "*.pdf *.docx *.doc *.xlsx *.xls"),
            ("PDF", "*.pdf"),
            ("Word", "*.docx *.doc"),
            ("Excel", "*.xlsx *.xls"),
        )
    ),
    PathPurpose.MARKDOWN: FileDialogOptions(
        filetypes=(("Markdown", "*.md"),),
        defaultextension=".md",
    ),
    PathPurpose.JSON: FileDialogOptions(
        filetypes=(("JSON", "*.json"),),
        defaultextension=".json",
    ),
    PathPurpose.YAML: FileDialogOptions(
        filetypes=(("YAML", "*.yaml *.yml"),),
        defaultextension=".yaml",
    ),
}


def supported_suffixes(purpose: PathPurpose) -> tuple[str, ...]:
    return _SUFFIXES[purpose]


def file_dialog_options(purpose: PathPurpose) -> FileDialogOptions:
    return _DIALOG_OPTIONS[purpose]


def require_supported_suffix(path: str | Path, purpose: PathPurpose, *, label: str) -> None:
    suffixes = supported_suffixes(purpose)
    actual = Path(path).suffix.lower()
    if actual not in suffixes:
        if len(suffixes) == 1:
            expected = f"{suffixes[0]} 文件"
        else:
            expected = " / ".join(suffixes) + " 文件"
        raise ValueError(f"{label}必须是 {expected}：{path}")
