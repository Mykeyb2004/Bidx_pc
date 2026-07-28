from pathlib import Path

import pytest

from bid_writer.path_purposes import (
    PathPurpose,
    file_dialog_options,
    require_supported_suffix,
)


def test_file_dialog_options_never_include_all_files() -> None:
    for purpose in PathPurpose:
        options = file_dialog_options(purpose)
        assert ("全部文件", "*.*") not in options.filetypes


def test_dialog_filters_match_business_purposes() -> None:
    assert file_dialog_options(PathPurpose.TENDER).filetypes == (
        ("招标文件", "*.pdf *.docx *.doc *.xlsx *.xls"),
        ("PDF", "*.pdf"),
        ("Word", "*.docx *.doc"),
        ("Excel", "*.xlsx *.xls"),
    )
    assert file_dialog_options(PathPurpose.MARKDOWN).filetypes == (("Markdown", "*.md"),)
    assert file_dialog_options(PathPurpose.JSON).filetypes == (("JSON", "*.json"),)
    assert file_dialog_options(PathPurpose.YAML).filetypes == (("YAML", "*.yaml *.yml"),)


@pytest.mark.parametrize(
    ("purpose", "path"),
    [
        (PathPurpose.TENDER, Path("招标文件.pdf")),
        (PathPurpose.TENDER, Path("招标文件.docx")),
        (PathPurpose.TENDER, Path("招标文件.doc")),
        (PathPurpose.TENDER, Path("招标文件.xlsx")),
        (PathPurpose.TENDER, Path("招标文件.xls")),
        (PathPurpose.MARKDOWN, Path("采购需求.md")),
        (PathPurpose.JSON, Path("撰写计划.json")),
        (PathPurpose.YAML, Path("config.yaml")),
        (PathPurpose.YAML, Path("config.yml")),
    ],
)
def test_require_supported_suffix_accepts_supported_extensions(
    purpose: PathPurpose,
    path: Path,
) -> None:
    require_supported_suffix(path, purpose, label="测试文件")


def test_require_supported_suffix_rejects_wrong_extension() -> None:
    with pytest.raises(ValueError, match="节点撰写计划文件必须是 .json 文件"):
        require_supported_suffix(Path("撰写计划.txt"), PathPurpose.JSON, label="节点撰写计划文件")
