from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path


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


_MATERIALS_DIR_NAMES = {"招标文件", "采购文件", "招采文件", "投标资料", "项目资料", "资料"}
_TRANSIENT_DIR_NAMES = {
    "downloads",
    "download",
    "desktop",
    "桌面",
    "下载",
    "tmp",
    "temp",
    "temporaryitems",
}
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


def infer_project_root(source_path: str | Path, config_dir: str | Path, project_name: str) -> Path:
    source = Path(source_path)
    parent = source.parent
    if parent.name in _MATERIALS_DIR_NAMES:
        return parent.parent
    if is_transient_location(source):
        return Path(config_dir) / project_name
    return parent


def derive_project_name(filename: str | Path) -> str:
    name = Path(filename).stem.strip()
    for suffix in sorted(_TENDER_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    return name or "新项目"


def is_transient_location(path: str | Path) -> bool:
    path_obj = Path(path)
    return any(part.casefold() in _TRANSIENT_DIR_NAMES for part in path_obj.parts)


def should_copy_source_file(source_path: str | Path, project_root: str | Path) -> bool:
    return not _is_relative_to(Path(source_path), Path(project_root))


def format_relative_path(path: str | Path, base_dir: str | Path) -> str:
    target = Path(path)
    base = Path(base_dir)
    if _is_relative_to(target, base):
        return f"./{target.relative_to(base).as_posix()}"
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

    state.source_copy_path.parent.mkdir(parents=True, exist_ok=True)
    copied = Path(shutil.copy2(state.source_path, state.source_copy_path))
    state.copied_source_path = copied
    register_created_path(state, copied)
    return copied


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
