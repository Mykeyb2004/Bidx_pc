from pathlib import Path
from types import SimpleNamespace

import pytest

import bid_writer.gui as gui
from bid_writer.file_saver import FileSaver
from bid_writer.gui import MainWindow
from bid_writer.gui_adapter import GUIAdapter
from bid_writer.main import BidWriter
from bid_writer.outline_parser import parse_outline


OUTLINE = """# 项目投标文件
## 服务方案
### 工作安排
#### 质量保障
#### 实施进度
## 运维方案
### 工作安排
#### 质量保障
"""


@pytest.fixture
def writer(tmp_path):
    writer = BidWriter.__new__(BidWriter)
    writer.parser = parse_outline(OUTLINE)
    writer.file_saver = FileSaver(str(tmp_path / "output"))
    writer.config = SimpleNamespace(output_normalize_soft_line_breaks_on_merge=False)
    return writer


def test_placeholder_has_empty_body_and_distinct_ids_for_duplicate_titles(writer):
    first, _, last = writer.parser.get_deepest_headings()
    writer.file_saver.include_title_header = False

    first_path = writer.file_saver.save_placeholder(first)
    last_path = writer.file_saver.save_placeholder(last)

    assert first_path != last_path
    for heading, filepath in ((first, first_path), (last, last_path)):
        assert writer.file_saver.find_existing_filepath(heading) == filepath
        assert writer.file_saver.load_section_body(filepath, heading.title) == ""
        assert f"# {heading.title}" in filepath.read_text(encoding="utf-8")
        assert writer.file_saver.read_metadata(filepath) == {
            "heading_id": writer.file_saver.build_heading_id(heading),
            "title": heading.title,
            "full_path": heading.full_path,
            "placeholder": True,
        }


@pytest.mark.parametrize("legacy", [False, True])
def test_placeholder_requires_explicit_overwrite_even_if_config_allows_it(writer, legacy):
    heading = writer.parser.get_deepest_headings()[0]
    saver = writer.file_saver
    saver.overwrite_existing = True
    existing = saver.save(heading.title if legacy else heading, "原有正文")
    original = existing.read_bytes()

    with pytest.raises(FileExistsError):
        saver.save_placeholder(heading)

    assert existing.read_bytes() == original
    assert saver.save_placeholder(heading, overwrite=True) == existing
    assert saver.load_section_body(existing, heading.title) == ""
    assert saver.find_existing_filepath(heading) == existing
    assert len(saver.list_saved_files()) == 1


def test_placeholder_overwrites_latest_version_and_remains_current(writer):
    heading = writer.parser.get_deepest_headings()[0]
    saver = writer.file_saver
    first = saver.save(heading, "旧版正文")
    latest = saver.save(heading, "新版正文")
    latest.touch()

    assert saver.save_placeholder(heading, overwrite=True) == latest
    assert saver.find_existing_filepath(heading) == latest
    assert "旧版正文" in first.read_text(encoding="utf-8")
    result = writer.merge_generated_sections(output_title="整合标书")
    assert "正文" not in result.filepath.read_text(encoding="utf-8")


def test_merge_preserves_placeholders_in_outline_order_and_skips_unmarked_empty_files(writer):
    first, second, last = writer.parser.get_deepest_headings()
    writer.file_saver.save_placeholder(first)
    writer.file_saver.save(second, "进度正文")
    writer.file_saver.save(last, "")

    result = writer.merge_generated_sections(output_title="整合标书")

    assert result.merged_sections == 2
    assert result.missing_sections == 1
    assert result.total_sections == 3
    assert result.filepath.read_text(encoding="utf-8") == (
        "# 项目投标文件\n\n## 服务方案\n\n### 工作安排\n\n"
        "#### 质量保障\n\n#### 实施进度\n\n进度正文\n"
    )


def test_all_placeholders_can_be_merged_and_are_detected_after_rescan(writer):
    headings = writer.parser.get_deepest_headings()
    for heading in headings:
        writer.file_saver.save_placeholder(heading)

    adapter = GUIAdapter(writer)
    result = writer.merge_generated_sections(output_title="整合标书")
    adapter.refresh_generated_titles()

    assert all(adapter.is_heading_generated(heading) for heading in headings)
    assert result.merged_sections == result.total_sections == 3
    assert result.missing_sections == 0
    content = result.filepath.read_text(encoding="utf-8")
    assert content.count("#### 质量保障") == 2
    assert content.index("#### 实施进度") < content.index("## 运维方案")
    assert "placeholder" not in content
    assert "heading_id" not in content


def test_manually_filled_placeholder_body_is_merged(writer):
    heading = writer.parser.get_deepest_headings()[0]
    filepath = writer.file_saver.save_placeholder(heading)
    with filepath.open("a", encoding="utf-8") as handle:
        handle.write("\n手工补充正文\n")

    result = writer.merge_generated_sections(output_title="整合标书")

    content = result.filepath.read_text(encoding="utf-8")
    assert "手工补充正文" in content
    assert content.count("#### 质量保障") == 1


def test_normal_generation_can_replace_placeholder_without_leaking_marker(writer):
    heading = writer.parser.get_deepest_headings()[0]
    writer.file_saver.save_placeholder(heading)
    generated = writer.file_saver.save(heading, "生成的正文", overwrite=True)

    assert writer.file_saver.read_metadata(generated) == {}
    result = writer.merge_generated_sections(output_title="整合标书")
    assert "生成的正文" in result.filepath.read_text(encoding="utf-8")


@pytest.fixture
def window(writer, monkeypatch):
    state = SimpleNamespace(status="", refreshed=0, warnings=[], errors=[], prompts=[])
    headings = writer.parser.get_deepest_headings()[:2]

    def refresh():
        state.refreshed += 1

    window = SimpleNamespace(
        bid_writer=writer,
        is_generating=False,
        status_text=SimpleNamespace(set=lambda value: setattr(state, "status", value)),
        _get_selected_leaf_headings=lambda: headings,
        _get_context_menu_heading=lambda: None,
        _sync_loaded_outline=refresh,
        _workspace_generation_failures={heading.full_path: object() for heading in headings},
        test_state=state,
    )
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *args, **kwargs: state.warnings.append(args))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *args, **kwargs: state.errors.append(args))

    def unexpected_prompt(*args, **kwargs):
        pytest.fail("没有文件冲突时不应弹出确认框")

    monkeypatch.setattr(gui.messagebox, "askyesnocancel", unexpected_prompt)
    return window


def test_gui_creates_selected_placeholders_and_refreshes_output_state(window):
    assert MainWindow.create_selected_placeholders(window) == "break"

    saver = window.bid_writer.file_saver
    assert len(saver.list_saved_files()) == 2
    assert all(saver.read_metadata(path)["placeholder"] for path in saver.list_saved_files())
    assert window.test_state.refreshed == 1
    assert window._workspace_generation_failures == {}
    assert window.test_state.status == "已创建 2 个占位文件，跳过 0 个已有文件"


@pytest.mark.parametrize("answer", [True, False, None])
def test_gui_existing_files_prompt_supports_skip_overwrite_and_cancel(window, monkeypatch, answer):
    saver = window.bid_writer.file_saver
    first, second = window._get_selected_leaf_headings()
    original_path = saver.save(first, "原有正文")
    original_content = original_path.read_bytes()

    def prompt(*args, **kwargs):
        window.test_state.prompts.append((args, kwargs))
        return answer

    monkeypatch.setattr(gui.messagebox, "askyesnocancel", prompt)

    MainWindow.create_selected_placeholders(window)

    args, kwargs = window.test_state.prompts[0]
    assert first.full_path in args[1]
    assert "原正文将被清空" in args[1]
    assert kwargs["default"] == gui.messagebox.YES
    if answer is None:
        assert original_path.read_bytes() == original_content
        assert saver.find_existing_filepath(second) is None
        assert window.test_state.refreshed == 0
        assert window.test_state.status == "已取消创建占位文件"
    else:
        assert saver.find_existing_filepath(second) is not None
        assert window.test_state.refreshed == 1
        if answer:
            assert original_path.read_bytes() == original_content
            assert window.test_state.status == "已创建 1 个占位文件，跳过 1 个已有文件"
        else:
            assert saver.load_section_body(original_path, first.title) == ""
            assert window.test_state.status == "已创建 2 个占位文件，跳过 0 个已有文件"


@pytest.mark.parametrize("lock", ["is_generating", "is_modal_workflow_active"])
def test_gui_does_not_create_placeholders_while_actions_are_locked(window, lock):
    setattr(window, lock, True)

    MainWindow.create_selected_placeholders(window)

    assert window.bid_writer.file_saver.list_saved_files() == []
    assert window.test_state.refreshed == 0


def test_gui_reports_partial_write_failure_and_refreshes_successful_files(window, monkeypatch):
    saver = window.bid_writer.file_saver
    first, _ = window._get_selected_leaf_headings()
    save = saver.save_placeholder

    def save_with_failure(heading, **kwargs):
        if heading is first:
            raise OSError("写入失败")
        return save(heading, **kwargs)

    monkeypatch.setattr(saver, "save_placeholder", save_with_failure)

    MainWindow.create_selected_placeholders(window)

    assert len(saver.list_saved_files()) == 1
    assert window.test_state.refreshed == 1
    assert "已创建 1 个占位文件" in window.test_state.status
    assert "失败 1 个" in window.test_state.status
    assert first.full_path in window.test_state.errors[0][1]
