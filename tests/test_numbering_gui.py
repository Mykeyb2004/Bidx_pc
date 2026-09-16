"""Exercise real background finalization and saving without a Tk display or API."""

import threading
import time
from types import SimpleNamespace

import pytest

import bid_writer.gui as gui
from test_numbering_generation import make_writer, heading


class WorkspaceHarness:
    GenerationSession = gui.MainWindow.GenerationSession
    _generate_into_workspace = gui.MainWindow._generate_into_workspace
    _report_generation_failure = gui.MainWindow._report_generation_failure

    def __init__(self, writer, saved_path):
        self.callbacks = {}
        self.deadline = time.monotonic() + 5
        self.stop_requested = False
        self._workspace_generation_buffers = {}
        self._workspace_generation_failures = {}
        self.messages = []
        self.saves = []
        self.facts = []
        self.statuses = []
        self.status_text = SimpleNamespace(set=self.statuses.append)
        self.workspace_meta_var = SimpleNamespace(set=self.statuses.append)
        self.bid_writer = SimpleNamespace(
            ai_writer=writer,
            config=SimpleNamespace(chapter_facts_enabled=True),
            resolve_generation_fact_cards=lambda *args, **kwargs: [],
            file_saver=SimpleNamespace(save=lambda node, content: self.save(saved_path, content)),
        )

    def save(self, path, content):
        self.saves.append(content)
        path.write_text(content, encoding="utf-8")
        return path

    def winfo_exists(self):
        return True

    def after(self, delay, callback=None):
        if callback is None:
            threading.Event().wait(0.001)
            return None
        token = object()
        self.callbacks[token] = callback
        return token

    def after_cancel(self, token):
        self.callbacks.pop(token, None)

    def update(self):
        assert time.monotonic() < self.deadline, "background generation did not terminate"
        callbacks = list(self.callbacks.values())
        self.callbacks.clear()
        for callback in callbacks:
            callback()

    def _show_generation_start_in_workspace(self, node):
        pass

    def _should_show_generation_updates(self, node):
        return True

    def _set_workspace_text(self, content, **kwargs):
        self.messages.append((content, kwargs))

    def _show_generated_content_in_workspace(self, node, content, **kwargs):
        self.messages.append((content, kwargs))

    def _show_generation_failure_in_workspace(self, node, feedback, **kwargs):
        self.messages.append((feedback.workspace_body_text, kwargs))

    def _trigger_async_fact_extraction(self, node):
        self.facts.append(node)


def prepare_workspace(monkeypatch, tmp_path, raw, *, stream=True, response="not json"):
    writer, calls, _ = make_writer(response)
    writer.config.generation_stream = stream
    writer.prepare_generation = lambda *args, **kwargs: SimpleNamespace(trace_session=None, trace_id="test")
    writer.expand_raw = lambda *args, **kwargs: iter([raw[:5], raw[5:]]) if stream else raw
    monkeypatch.setattr(gui, "write_timing_log", lambda *args, **kwargs: None)
    path = tmp_path / "chapter.md"
    path.write_text("原有正式正文", encoding="utf-8")
    return WorkspaceHarness(writer, path), writer, calls, path


@pytest.mark.parametrize("stream", [True, False])
def test_repaired_result_is_saved_after_background_finalization(monkeypatch, tmp_path, stream):
    raw = "（一）组织安排\n\n服务12人。\n\n1. 岗位职责"
    window, writer, calls, path = prepare_workspace(monkeypatch, tmp_path, raw, stream=stream)
    finalizer_threads = []
    finalize = writer.finalize_generation

    def finalize_in_worker(*args, **kwargs):
        finalizer_threads.append(threading.current_thread())
        return finalize(*args, **kwargs)

    monkeypatch.setattr(writer, "finalize_generation", finalize_in_worker)
    result = window._generate_into_workspace(heading(), "", 1200, 0, auto_extract_facts=True)

    expected = "一、组织安排\n\n服务12人。\n\n（一）岗位职责"
    assert result == "success"
    assert window.saves == [expected]
    assert path.read_text() == expected
    assert window._workspace_generation_buffers[heading().full_path] == expected
    assert finalizer_threads and finalizer_threads[0] is not threading.main_thread()
    assert "已修复正文编号并保存" in window.statuses[-1]
    assert len(window.facts) == 1
    assert not calls


@pytest.mark.parametrize("stream", [True, False])
def test_failed_repair_keeps_old_file_and_raw_workspace_draft(monkeypatch, tmp_path, stream):
    raw = "（一）组织安排\n\n服务12人。\n\n### 岗位职责"
    window, _, calls, path = prepare_workspace(monkeypatch, tmp_path, raw, stream=stream)
    result = window._generate_into_workspace(heading(), "", 1200, 0, auto_extract_facts=True, show_error_dialog=False)

    assert result == "failed"
    assert not window.saves and not window.facts
    assert path.read_text() == "原有正式正文"
    failure = window._workspace_generation_failures[heading().full_path]
    assert failure.partial_content == raw
    assert failure.feedback.category_title == "正文编号校验未通过"
    assert "未自动保存" in failure.feedback.workspace_body_text
    assert len(calls) == 1


def test_cancel_during_repair_does_not_apply_late_result(monkeypatch, tmp_path):
    raw = "（一）组织安排\n\n服务12人。\n\n### 岗位职责"
    window, writer, _, path = prepare_workspace(monkeypatch, tmp_path, raw)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def create(**kwargs):
        entered.set()
        release.wait(2)
        finished.set()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"headings":[{"line":1,"level":1},{"line":5,"level":2}]}'
        ))])

    writer.client.chat.completions.create = create
    update = window.update

    def update_and_cancel():
        update()
        if entered.is_set():
            window._active_generation_session.cancel()

    window.update = update_and_cancel
    try:
        result = window._generate_into_workspace(heading(), "", 1200, 0, auto_extract_facts=True)
        assert result == "stopped"
        assert not window.saves and not window.facts
        assert path.read_text() == "原有正式正文"
    finally:
        release.set()
        assert finished.wait(2)
    assert not window.saves


def test_batch_counts_bad_numbering_as_failure_and_continues(monkeypatch, tmp_path):
    window, writer, _, path = prepare_workspace(monkeypatch, tmp_path, "没有标题的正文。")
    second = heading()
    second.title = "3.3.2 后续服务"
    second.full_path = "项目 > 3.3.2 后续服务"
    writer.prepare_generation = lambda node, *args, **kwargs: SimpleNamespace(trace_session=None, trace_id="test", node=node)
    writer.expand_raw = lambda prepared, **kwargs: "没有标题的正文。" if prepared.node.title == heading().title else "一、后续安排\n\n正文。"
    window.progress_bar = SimpleNamespace(configure=lambda **kwargs: None)
    window.batch_progress_text = window.task_text = window.status_text
    window.update_action_states = window.update_idletasks = window.refresh_status = lambda: None
    warnings = []
    monkeypatch.setattr(gui.MainWindow, "_refresh_heading_tree_row", lambda *args: None)
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *args, **kwargs: warnings.append(args))

    gui.MainWindow._do_batch_generate(window, [heading(), second], "", 1200, 0)

    assert window.saves == ["一、后续安排\n\n正文。"]
    assert "成功: 1, 失败: 1" in window.statuses[-1]
    assert heading().title in warnings[0][1]


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize("valid_proposal", [True, False])
def test_bold_circled_chapter_is_repaired_before_gui_save(monkeypatch, tmp_path, stream, valid_proposal):
    import json
    from test_body_numbering_emphasis import SOURCE_PATH, CHAPTER_TITLE, PROPOSAL

    raw = SOURCE_PATH.read_text()
    response = json.dumps(PROPOSAL) if valid_proposal else '{"headings":[]}'
    window, _, calls, path = prepare_workspace(monkeypatch, tmp_path, raw, stream=stream, response=response)
    node = heading()
    node.title = node.full_path = CHAPTER_TITLE
    result = window._generate_into_workspace(node, "", 1200, 0, auto_extract_facts=True, show_error_dialog=False)

    assert len(calls) == 1
    if valid_proposal:
        assert result == "success"
        assert len(window.saves) == len(window.facts) == 1
        assert "**（一）平台运行管理**" in path.read_text()
        assert "**（五）信息质量保障**" in path.read_text()
        assert "已修复正文编号并保存" in window.statuses[-1]
    else:
        assert result == "failed"
        assert not window.saves and not window.facts
        assert path.read_text() == "原有正式正文"
        assert window._workspace_generation_failures[node.full_path].partial_content == raw
