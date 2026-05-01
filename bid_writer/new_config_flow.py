from __future__ import annotations

import copy
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from bid_writer.config_editor import ConfigEditorDocument, create_new_config_editor_document


@dataclass
class NewConfigWizardState:
    source_path: Path | None
    project_root: Path
    config_path: Path
    import_dir: Path | None
    should_copy_source: bool
    source_copy_path: Path | None
    copied_source_path: Path | None
    requirements_path: Path | None
    scoring_path: Path | None
    outline_path: Path
    output_dir: Path
    bidder_name: str
    created_paths: list[Path] = field(default_factory=list)
    manual_inputs: bool = False


_TENDER_SUFFIXES = (
    "公开招标文件",
    "竞争性磋商文件",
    "竞争性谈判文件",
    "招标文件",
    "采购文件",
    "询价文件",
    "比选文件",
    "采购需求",
    "采购公告",
    "招标公告",
    "投标文件",
)
DEFAULT_REQUIREMENTS_RELATIVE = "./项目要求/项目采购需求.md"
DEFAULT_SCORING_RELATIVE = "./项目要求/评分标准.md"


def build_initial_state_from_source(
    source_path: str | Path, *, current_config_path: str | Path
) -> NewConfigWizardState:
    source = Path(source_path)
    current_config = Path(current_config_path)
    config_dir = current_config.parent
    project_name = derive_project_name(source.name)
    project_root = infer_project_root(source, config_dir, project_name)
    copy_source = should_copy_source_file(source, project_root)
    source_copy_path = project_root / "招标文件" / source.name if copy_source else None

    return NewConfigWizardState(
        source_path=source,
        project_root=project_root,
        config_path=config_dir / f"config_{project_name}.yaml",
        import_dir=project_root / ".bid_writer" / "imports" / "pending",
        should_copy_source=copy_source,
        source_copy_path=source_copy_path,
        copied_source_path=None,
        requirements_path=project_root / "项目要求" / "项目采购需求.md",
        scoring_path=project_root / "项目要求" / "评分标准.md",
        outline_path=project_root / "投标大纲.md",
        output_dir=project_root / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=False,
    )


def build_manual_state(*, project_root: str | Path, config_path: str | Path) -> NewConfigWizardState:
    root = Path(project_root)
    return NewConfigWizardState(
        source_path=None,
        project_root=root,
        config_path=Path(config_path),
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=root / "项目要求" / "项目采购需求.md",
        scoring_path=root / "项目要求" / "评分标准.md",
        outline_path=root / "投标大纲.md",
        output_dir=root / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=True,
    )


def build_editor_document_from_state(state: NewConfigWizardState) -> ConfigEditorDocument:
    document = create_new_config_editor_document(state.config_path)
    model = copy.deepcopy(document.model)
    model["project"]["root_dir"] = format_relative_path(state.project_root, state.config_path.parent)
    model["project"]["bidder_name"] = state.bidder_name.strip()
    model["project"]["outline_locked"] = False
    model["project"]["outline_file"] = format_relative_path(state.outline_path, state.project_root)
    model["project"]["bid_requirements_mode"] = "file"
    model["project"]["bid_requirements_file"] = (
        format_relative_path(state.requirements_path, state.project_root)
        if state.requirements_path is not None
        else DEFAULT_REQUIREMENTS_RELATIVE
    )
    model["project"]["scoring_criteria_mode"] = "file"
    model["project"]["scoring_criteria_file"] = (
        format_relative_path(state.scoring_path, state.project_root)
        if state.scoring_path is not None
        else DEFAULT_SCORING_RELATIVE
    )
    model["project"]["output_dir"] = format_relative_path(state.output_dir, state.project_root)
    document.model = model
    document.require_project_identity = True
    return document


def infer_project_root(source_path: str | Path, config_dir: str | Path, project_name: str) -> Path:
    source = Path(source_path)
    return source.parent


def derive_project_name(filename: str | Path) -> str:
    name = Path(filename).stem.strip()
    for suffix in sorted(_TENDER_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    return name or "新项目"


def should_copy_source_file(source_path: str | Path, project_root: str | Path) -> bool:
    return not _is_relative_to_normalized(Path(source_path), Path(project_root))


def format_relative_path(path: str | Path, base_dir: str | Path) -> str:
    target = Path(path)
    base = Path(base_dir)
    normalized_target = _normalize_path(target)
    normalized_base = _normalize_path(base)
    if _is_relative_to(normalized_target, normalized_base):
        return f"./{normalized_target.relative_to(normalized_base).as_posix()}"
    return str(target)


def register_created_path(state: NewConfigWizardState, path: str | Path) -> None:
    created = Path(path)
    if created not in state.created_paths:
        state.created_paths.append(created)


def cleanup_created_paths(state: NewConfigWizardState) -> list[tuple[Path, str]]:
    failures: list[tuple[Path, str]] = []
    for path in reversed(state.created_paths):
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        except OSError as exc:
            failures.append((path, str(exc)))
    return failures


def copy_source_file_if_needed(state: NewConfigWizardState) -> Path | None:
    if not state.should_copy_source or state.source_path is None or state.source_copy_path is None:
        return None

    parent_dir = state.source_copy_path.parent
    created_parent_dir = not parent_dir.exists()
    parent_dir.mkdir(parents=True, exist_ok=True)
    target_path = _unique_copy_target(state.source_copy_path)
    state.source_copy_path = target_path
    copied = Path(shutil.copy2(state.source_path, target_path))
    state.copied_source_path = copied
    if created_parent_dir:
        register_created_path(state, parent_dir)
    register_created_path(state, copied)
    return copied


def _unique_copy_target(path: Path) -> Path:
    if not path.exists():
        return path

    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _is_relative_to_normalized(path: Path, base: Path) -> bool:
    return _is_relative_to(_normalize_path(path), _normalize_path(base))


def _normalize_path(path: Path) -> Path:
    return path.resolve(strict=False)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
