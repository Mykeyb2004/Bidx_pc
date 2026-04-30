from pathlib import Path

from bid_writer.new_config_flow import (
    NewConfigWizardState,
    build_initial_state_from_source,
    copy_source_file_if_needed,
    cleanup_created_paths,
    derive_project_name,
    format_relative_path,
    should_copy_source_file,
)


def test_regular_tender_directory_becomes_project_root(tmp_path: Path):
    source = tmp_path / "公共服务满意度招标文件.docx"
    source.write_text("fake", encoding="utf-8")
    current_config = tmp_path / "config.yaml"

    state = build_initial_state_from_source(source, current_config_path=current_config)

    assert state.project_root == tmp_path
    assert state.config_path == tmp_path / "config_公共服务满意度.yaml"
    assert state.requirements_path == tmp_path / "项目要求" / "项目采购需求.md"
    assert state.scoring_path == tmp_path / "项目要求" / "评分标准.md"
    assert state.outline_path == tmp_path / "投标大纲.md"
    assert state.output_dir == tmp_path / "output"
    assert state.should_copy_source is False


def test_materials_directory_uses_parent_as_project_root(tmp_path: Path):
    project = tmp_path / "公共服务项目"
    source_dir = project / "招标文件"
    source_dir.mkdir(parents=True)
    source = source_dir / "采购文件.pdf"
    source.write_text("fake", encoding="utf-8")

    state = build_initial_state_from_source(source, current_config_path=tmp_path / "config.yaml")

    assert state.project_root == project
    assert state.should_copy_source is False


def test_downloads_source_suggests_new_project_folder(tmp_path: Path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    source = downloads / "公共服务满意度项目招标文件.pdf"
    source.write_text("fake", encoding="utf-8")
    current_config = tmp_path / "workspace" / "config.yaml"
    current_config.parent.mkdir()

    state = build_initial_state_from_source(source, current_config_path=current_config)

    assert state.project_root == current_config.parent / "公共服务满意度项目"
    assert state.should_copy_source is True
    assert state.source_copy_path == state.project_root / "招标文件" / source.name


def test_project_name_strips_common_tender_suffixes():
    assert derive_project_name("公共服务满意度项目招标文件.pdf") == "公共服务满意度项目"
    assert derive_project_name("采购文件") == "新项目"


def test_format_relative_path_prefers_project_relative(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()
    target = project / "项目要求" / "评分标准.md"

    assert format_relative_path(target, project) == "./项目要求/评分标准.md"


def test_should_copy_source_file_only_for_project_external_sources(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()

    assert should_copy_source_file(project / "招标文件" / "a.pdf", project) is False
    assert should_copy_source_file(tmp_path / "Downloads" / "a.pdf", project) is True


def test_cleanup_created_paths_removes_only_recorded_files_and_empty_dirs(tmp_path: Path):
    keep = tmp_path / "用户已有.md"
    keep.write_text("keep", encoding="utf-8")
    created_dir = tmp_path / "项目要求"
    created_dir.mkdir()
    created_file = created_dir / "评分标准.md"
    created_file.write_text("score", encoding="utf-8")
    nested_keep = created_dir / "用户补充.md"
    nested_keep.write_text("user", encoding="utf-8")

    state = NewConfigWizardState(
        source_path=None,
        project_root=tmp_path,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=None,
        scoring_path=created_file,
        outline_path=tmp_path / "投标大纲.md",
        output_dir=tmp_path / "output",
        bidder_name="",
        created_paths=[created_file, created_dir],
        manual_inputs=False,
    )

    failures = cleanup_created_paths(state)

    assert failures == []
    assert not created_file.exists()
    assert created_dir.exists()
    assert nested_keep.exists()
    assert keep.exists()


def test_copy_source_file_if_needed_copies_external_source_and_records_path(tmp_path: Path):
    source = tmp_path / "Downloads" / "tender.pdf"
    source.parent.mkdir()
    source.write_text("source", encoding="utf-8")
    project = tmp_path / "项目"
    project.mkdir()
    state = NewConfigWizardState(
        source_path=source,
        project_root=project,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=True,
        source_copy_path=project / "招标文件" / "tender.pdf",
        copied_source_path=None,
        requirements_path=None,
        scoring_path=None,
        outline_path=project / "投标大纲.md",
        output_dir=project / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=False,
    )

    copied = copy_source_file_if_needed(state)

    assert copied == project / "招标文件" / "tender.pdf"
    assert copied.read_text(encoding="utf-8") == "source"
    assert state.copied_source_path == copied
    assert copied in state.created_paths


def test_copy_source_file_if_needed_skips_project_internal_source(tmp_path: Path):
    project = tmp_path / "项目"
    source = project / "招标文件" / "tender.pdf"
    source.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    state = NewConfigWizardState(
        source_path=source,
        project_root=project,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=None,
        scoring_path=None,
        outline_path=project / "投标大纲.md",
        output_dir=project / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=False,
    )

    copied = copy_source_file_if_needed(state)

    assert copied is None
    assert state.created_paths == []
