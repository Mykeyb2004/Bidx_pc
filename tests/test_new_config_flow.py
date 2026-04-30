from pathlib import Path

import yaml

from bid_writer.new_config_flow import (
    NewConfigWizardState,
    build_editor_document_from_state,
    build_initial_state_from_source,
    build_manual_state,
    copy_source_file_if_needed,
    cleanup_created_paths,
    derive_project_name,
    format_relative_path,
    infer_project_root,
    is_transient_location,
    register_created_path,
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


def test_initial_state_config_path_uses_current_config_directory(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "公共服务满意度招标文件.docx"
    source.write_text("fake", encoding="utf-8")
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    state = build_initial_state_from_source(
        source,
        current_config_path=config_dir / "config.yaml",
    )

    assert state.project_root == source_dir
    assert state.config_path == config_dir / "config_公共服务满意度.yaml"


def test_initial_state_import_dir_uses_project_pending_import_area(tmp_path: Path):
    source = tmp_path / "公共服务满意度招标文件.docx"
    source.write_text("fake", encoding="utf-8")

    state = build_initial_state_from_source(source, current_config_path=tmp_path / "config.yaml")

    assert state.import_dir == tmp_path / ".bid_writer" / "imports" / "pending"


def test_materials_directory_uses_parent_as_project_root(tmp_path: Path):
    project = tmp_path / "公共服务项目"
    source_dir = project / "招标文件"
    source_dir.mkdir(parents=True)
    source = source_dir / "采购文件.pdf"
    source.write_text("fake", encoding="utf-8")

    state = build_initial_state_from_source(source, current_config_path=tmp_path / "config.yaml")

    assert state.project_root == project
    assert state.should_copy_source is False


def test_materials_directory_includes_plain_materials_name(tmp_path: Path):
    project = tmp_path / "公共服务项目"
    source_dir = project / "资料"
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
    assert derive_project_name("公共服务满意度项目采购公告.pdf") == "公共服务满意度项目"
    assert derive_project_name("某项目公开招标文件.pdf") == "某项目"
    assert derive_project_name("采购文件") == "新项目"


def test_build_manual_state_uses_manual_paths(tmp_path: Path):
    project = tmp_path / "项目"
    config = tmp_path / "configs" / "config_项目.yaml"

    state = build_manual_state(project_root=project, config_path=config)

    assert state.source_path is None
    assert state.project_root == project
    assert state.config_path == config
    assert state.import_dir is None
    assert state.should_copy_source is False
    assert state.requirements_path == project / "项目要求" / "项目采购需求.md"
    assert state.scoring_path == project / "项目要求" / "评分标准.md"
    assert state.outline_path == project / "投标大纲.md"
    assert state.output_dir == project / "output"
    assert state.manual_inputs is True


def test_build_editor_document_uses_relative_project_paths(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()
    config_path = tmp_path / "config_项目.yaml"
    requirements = project / "项目要求" / "项目采购需求.md"
    scoring = project / "项目要求" / "评分标准.md"
    requirements.parent.mkdir()
    requirements.write_text("需求", encoding="utf-8")
    scoring.write_text("评分", encoding="utf-8")

    state = NewConfigWizardState(
        source_path=None,
        project_root=project,
        config_path=config_path,
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=requirements,
        scoring_path=scoring,
        outline_path=project / "投标大纲.md",
        output_dir=project / "output",
        bidder_name="测试公司",
        created_paths=[],
        manual_inputs=True,
    )

    document = build_editor_document_from_state(state)
    payload = yaml.safe_load(document.render_yaml())

    assert document.config_path == config_path.resolve()
    assert payload["project"]["root_dir"] == "./项目"
    assert payload["project"]["bidder_name"] == "测试公司"
    assert payload["project"]["outline_locked"] is False
    assert payload["project"]["inputs"]["outline_file"] == "./投标大纲.md"
    assert payload["project"]["inputs"]["bid_requirements_file"] == "./项目要求/项目采购需求.md"
    assert payload["project"]["inputs"]["scoring_criteria_file"] == "./项目要求/评分标准.md"
    assert payload["project"]["output_dir"] == "./output"


def test_build_editor_document_requires_bidder_identity(tmp_path: Path):
    state = build_manual_state(project_root=tmp_path, config_path=tmp_path / "config.yaml")
    document = build_editor_document_from_state(state)

    messages = document.validate(document.model, config_path=state.config_path)

    assert any(item.level == "error" and "投标主体名称不能为空" in item.text for item in messages)


def test_build_editor_document_preserves_default_runtime_and_processing(tmp_path: Path):
    state = build_manual_state(project_root=tmp_path, config_path=tmp_path / "config.yaml")
    state.bidder_name = "测试公司"
    document = build_editor_document_from_state(state)
    payload = yaml.safe_load(document.render_yaml())

    assert payload["processing"]["path"] == "auto"
    assert payload["runtime"]["stream"]["enabled"] is True
    assert payload["writing"]["role_file"] == "./roles/通用投标角色.md"


def test_infer_project_root_uses_material_parent_transient_config_or_source_parent(tmp_path: Path):
    project = tmp_path / "项目"
    materials = project / "资料" / "采购文件.pdf"
    downloads = tmp_path / "Downloads" / "项目招标文件.pdf"
    regular = tmp_path / "regular" / "项目招标文件.pdf"
    config_dir = tmp_path / "configs"

    assert infer_project_root(materials, config_dir, "项目") == project
    assert infer_project_root(downloads, config_dir, "项目") == config_dir / "项目"
    assert infer_project_root(regular, config_dir, "项目") == regular.parent


def test_is_transient_location_detects_common_temporary_locations(tmp_path: Path):
    assert is_transient_location(tmp_path / "Downloads" / "采购文件.pdf") is True
    assert is_transient_location(tmp_path / "桌面" / "采购文件.pdf") is True
    assert is_transient_location(tmp_path / "项目" / "采购文件.pdf") is False


def test_format_relative_path_prefers_project_relative(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()
    target = project / "项目要求" / "评分标准.md"

    assert format_relative_path(target, project) == "./项目要求/评分标准.md"


def test_format_relative_path_does_not_treat_dotdot_escape_as_project_relative(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()
    escaped = project / ".." / "Downloads" / "tender.pdf"

    assert format_relative_path(escaped, project) == str(escaped)


def test_should_copy_source_file_only_for_project_external_sources(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()

    assert should_copy_source_file(project / "招标文件" / "a.pdf", project) is False
    assert should_copy_source_file(tmp_path / "Downloads" / "a.pdf", project) is True


def test_should_copy_source_file_treats_dotdot_escape_as_external(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()

    assert should_copy_source_file(project / ".." / "Downloads" / "tender.pdf", project) is True


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


def test_register_created_path_records_each_path_once(tmp_path: Path):
    state = NewConfigWizardState(
        source_path=None,
        project_root=tmp_path,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=None,
        scoring_path=None,
        outline_path=tmp_path / "投标大纲.md",
        output_dir=tmp_path / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=False,
    )
    created = tmp_path / "created.md"

    register_created_path(state, created)
    register_created_path(state, created)

    assert state.created_paths == [created]


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


def test_copy_source_file_if_needed_avoids_overwriting_existing_project_file(tmp_path: Path):
    source = tmp_path / "Downloads" / "tender.pdf"
    source.parent.mkdir()
    source.write_text("source", encoding="utf-8")
    project = tmp_path / "项目"
    target_dir = project / "招标文件"
    target_dir.mkdir(parents=True)
    existing = target_dir / "tender.pdf"
    existing.write_text("existing", encoding="utf-8")
    state = NewConfigWizardState(
        source_path=source,
        project_root=project,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=True,
        source_copy_path=existing,
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

    assert copied == target_dir / "tender_1.pdf"
    assert copied.read_text(encoding="utf-8") == "source"
    assert existing.read_text(encoding="utf-8") == "existing"
    assert state.copied_source_path == copied
    assert copied in state.created_paths


def test_copy_source_file_if_needed_records_new_parent_dir_for_cleanup(tmp_path: Path):
    source = tmp_path / "Downloads" / "tender.pdf"
    source.parent.mkdir()
    source.write_text("source", encoding="utf-8")
    project = tmp_path / "项目"
    project.mkdir()
    target_dir = project / "招标文件"
    state = NewConfigWizardState(
        source_path=source,
        project_root=project,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=True,
        source_copy_path=target_dir / "tender.pdf",
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
    failures = cleanup_created_paths(state)

    assert copied == target_dir / "tender.pdf"
    assert failures == []
    assert not copied.exists()
    assert not target_dir.exists()


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
