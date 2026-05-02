# Outline Stage And Stream Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make outline generation feel alive by showing stage progress before the first token and streaming outline text into the dialog as soon as the model starts returning content.

**Architecture:** Reuse the existing OpenAI-compatible generation path and the current `runtime.stream.enabled` switch. Add stage callbacks to `OutlineGenerator`, thread-safe queue handling in `OutlinePrepareDialog`, and a small status vocabulary so the dialog can show preparation, request, first-token wait, streaming, validation, and completion as separate user-visible phases.

**Tech Stack:** Python 3, Tkinter/ttk, OpenAI-compatible SDK, PyYAML, pytest, `uv run`.

---

## File Structure

- Modify `bid_writer/outline_generator.py`: add stage/status callbacks, support optional streaming generation, and keep the existing cleaning/validation behavior for final output.
- Modify `bid_writer/outline_prepare_dialog.py`: consume staged status updates plus streamed text chunks, update the text box incrementally, and keep the confirm flow intact.
- Modify `bid_writer/config.py` only if a missing outline-specific stream default is discovered during implementation; otherwise reuse the current `generation_stream` and `generation_stream_idle_timeout_seconds` properties as-is.
- Modify `tests/test_outline_generator.py`: cover stage callbacks, streaming and non-streaming behavior, and final cleaning.
- Modify `tests/test_outline_prepare_dialog.py`: cover status-only progress before first token, streamed text append, and final replacement/validation behavior.
- Modify `docs/chapter_expansion_mechanism.md` and `docs/generation_trace.md` only if the outline flow needs explicit documentation of the new stage/status behavior.

## Task 1: Add Stage-Aware Outline Generation

**Files:**
- Modify: `bid_writer/outline_generator.py`
- Test: `tests/test_outline_generator.py`

- [ ] **Step 1: Write the failing stage/stream tests**

Append these tests to `tests/test_outline_generator.py`:

```python
def test_generate_streams_tokens_and_reports_stages(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))

    class FakeChunk:
        def __init__(self, token: str = "", finish_reason: str | None = None):
            self.choices = [type("Choice", (), {"delta": type("Delta", (), {"content": token})(), "finish_reason": finish_reason})()]

    class FakeStream:
        def __iter__(self):
            yield FakeChunk("## 生成中")
            yield FakeChunk("### 继续")
            yield FakeChunk(finish_reason="stop")

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["stream"] is True
            return FakeStream()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    stages: list[tuple[str, str]] = []
    generator = OutlineGenerator(config, client_factory=lambda **_kwargs: FakeClient())
    result = generator.generate(
        status_callback=lambda stage, message: stages.append((stage, message)),
    )

    assert result.outline_text.endswith("### 继续\n")
    assert ("准备大纲请求", "正在准备大纲生成请求...") in stages
    assert ("等待首批输出", "正在请求模型并等待首批内容...") in stages
    assert ("接收内容", "正在接收大纲生成内容...") in stages


def test_generate_can_run_without_streaming_but_still_reports_stages(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))

    class FakeMessage:
        content = "# 项目\n## 章\n### 节\n#### 单元\n"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["stream"] is False
            return FakeResponse()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    stages: list[str] = []
    generator = OutlineGenerator(config, client_factory=lambda **_kwargs: FakeClient())
    result = generator.generate(
        stream=False,
        status_callback=lambda stage, _message: stages.append(stage),
    )

    assert result.outline_text.endswith("#### 单元\n")
    assert "准备大纲请求" in stages
    assert "请求模型" in stages
    assert "清理与校验" in stages
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
uv run pytest tests/test_outline_generator.py::test_generate_streams_tokens_and_reports_stages tests/test_outline_generator.py::test_generate_can_run_without_streaming_but_still_reports_stages -q
```

Expected: FAIL because `OutlineGenerator.generate()` does not yet accept staged callbacks or per-call streaming.

- [ ] **Step 3: Implement the minimal stage-aware generator**

In `bid_writer/outline_generator.py`, extend the public generation flow so the generator can report progress before the first token and while streaming:

```python
class OutlineGenerator:
    def generate(
        self,
        *,
        stream: bool | None = None,
        status_callback: Callable[[str, str], None] | None = None,
    ) -> OutlineGenerationResult:
        ...

    def _emit_status(self, status_callback: Callable[[str, str], None] | None, stage: str, message: str) -> None:
        if status_callback is not None:
            status_callback(stage, message)
```

Implementation requirements:

```python
def generate(...):
    stream_enabled = self.config.generation_stream if stream is None else bool(stream)
    self._emit_status(status_callback, "准备大纲请求", "正在准备大纲生成请求...")
    ...
    self._emit_status(status_callback, "请求模型", "正在发起大纲生成请求...")
    if stream_enabled:
        self._emit_status(status_callback, "等待首批输出", "正在请求模型并等待首批内容...")
        raw_text = self._collect_streamed_outline(client, options, status_callback)
    else:
        self._emit_status(status_callback, "等待完整返回", "正在请求模型并等待完整返回...")
        raw_text = self._collect_sync_outline(client, options)
    self._emit_status(status_callback, "清理与校验", "正在清理与校验大纲结果...")
    result = clean_outline_response(raw_text)
    ...
```

Add a small streaming helper that yields token chunks through the response iterator and calls the callback when the first token arrives:

```python
def _collect_streamed_outline(
    self,
    client: OpenAI,
    options: dict[str, Any],
    status_callback: Callable[[str, str], None] | None,
) -> str:
    response = client.chat.completions.create(**options)
    chunks: list[str] = []
    saw_first_token = False
    for chunk in response:
        if not chunk.choices:
            continue
        token = chunk.choices[0].delta.content or ""
        if token:
            if not saw_first_token:
                self._emit_status(status_callback, "接收内容", "已收到首批内容，正在流式接收大纲...")
                saw_first_token = True
            chunks.append(token)
    return "".join(chunks)
```

Keep the current Markdown cleaning and validation behavior unchanged.

- [ ] **Step 4: Run the outline generator tests**

Run:

```bash
uv run pytest tests/test_outline_generator.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add bid_writer/outline_generator.py tests/test_outline_generator.py
git commit -m "feat: add outline generation stage feedback"
```

Expected: commit succeeds.

## Task 2: Show Stages In The Outline Preparation Dialog

**Files:**
- Modify: `bid_writer/outline_prepare_dialog.py`
- Test: `tests/test_outline_prepare_dialog.py`

- [ ] **Step 1: Write the failing dialog feedback tests**

Append these tests to `tests/test_outline_prepare_dialog.py`:

```python
def test_generate_outline_updates_status_before_text_arrives(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)

    class FakeGenerator:
        def generate(self, *, stream=True, status_callback=None):
            status_callback("准备大纲请求", "正在准备大纲生成请求...")
            status_callback("等待首批输出", "正在请求模型并等待首批内容...")
            return type("Result", (), {"outline_text": "# 项目\\n## 章\\n### 节\\n#### 单元\\n", "warnings": []})()

    dialog._generator_factory = lambda: FakeGenerator()
    dialog._start_generation()

    assert "准备大纲请求" in dialog.status_var.get()
    assert dialog.outline_text.get("1.0", "end").startswith("# 项目")


def test_generate_outline_streams_text_into_editor(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)

    class FakeGenerator:
        def generate(self, *, stream=True, status_callback=None):
            status_callback("等待首批输出", "正在请求模型并等待首批内容...")
            dialog._append_outline_text("## 章\n")
            dialog._append_outline_text("### 节\n")
            return type("Result", (), {"outline_text": "# 项目\\n## 章\\n### 节\\n#### 单元\\n", "warnings": []})()

    dialog._generator_factory = lambda: FakeGenerator()
    dialog._start_generation()

    assert dialog.outline_text.get("1.0", "end").endswith("#### 单元\\n")
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
uv run pytest tests/test_outline_prepare_dialog.py::test_generate_outline_updates_status_before_text_arrives tests/test_outline_prepare_dialog.py::test_generate_outline_streams_text_into_editor -q
```

Expected: FAIL because the dialog still treats generation as a single final result.

- [ ] **Step 3: Refactor the dialog to consume staged updates**

In `bid_writer/outline_prepare_dialog.py`, add a tiny queue-driven update path and keep the UI thread-safe:

```python
class OutlinePrepareDialog(tk.Toplevel):
    def _enqueue_status(self, stage: str, message: str) -> None:
        self.status_var.set(f"{stage}：{message}")

    def _append_outline_text(self, chunk: str) -> None:
        self.outline_text.insert(tk.END, chunk)
        self.outline_text.see(tk.END)

    def _start_generation(self) -> None:
        self.status_var.set("正在生成大纲...")
        self.validation_var.set("")
        if hasattr(self, "confirm_button"):
            self.confirm_button.configure(state="disabled")
        thread = threading.Thread(target=self._run_generate_outline, daemon=True)
        thread.start()

    def _run_generate_outline(self) -> None:
        ...
        for stage, message in status_events:
            self.after(0, lambda s=stage, m=message: self._enqueue_status(s, m))
        ...
```

Update the generation path so the dialog:

1. shows stage text even before any outline text arrives,
2. appends streamed outline content as it comes in,
3. replaces the editor with the cleaned final outline once generation completes,
4. keeps existing validation and confirmation behavior intact.

Do not change the confirmation save flow or the H4 validation rules.

- [ ] **Step 4: Run the dialog tests**

Run:

```bash
uv run pytest tests/test_outline_prepare_dialog.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add bid_writer/outline_prepare_dialog.py tests/test_outline_prepare_dialog.py
git commit -m "feat: stream outline progress in dialog"
```

Expected: commit succeeds.

## Task 3: Update Documentation And Verify Integration

**Files:**
- Modify: `docs/chapter_expansion_mechanism.md`
- Modify: `docs/generation_trace.md`
- Modify: `config.example.yaml` only if the outline generation flow needs an explicit example note
- Modify: `config_*.yaml` only if an active sample needs to demonstrate the new behavior

- [ ] **Step 1: Add a short note for outline-generation stages**

Update the outline preparation or generation docs with one short paragraph explaining that users now see stages before the first token and streamed text as soon as it appears.

Suggested wording:

```markdown
大纲准备窗口会先显示阶段状态，例如“准备请求”“等待首批输出”“清理与校验”；如果模型开始返回内容，文本会立即流式写入编辑框，因此即使首批内容较慢，用户也能持续看到进度。
```

- [ ] **Step 2: Run the relevant tests again**

Run:

```bash
uv run pytest tests/test_outline_generator.py tests/test_outline_prepare_dialog.py -q
```

Expected: PASS.

- [ ] **Step 3: Verify touched files and commit**

Run:

```bash
git status --short
```

Expected: only the intended plan-related implementation and documentation files are modified.

Then commit the documentation update:

```bash
git add docs/chapter_expansion_mechanism.md docs/generation_trace.md
git commit -m "docs: describe outline stage feedback"
```

Expected: commit succeeds.

## Coverage Check

- Stage feedback before first token: Task 1 and Task 2.
- Streaming outline content into the editor: Task 1 and Task 2.
- No new config surface unless required: File Structure and Task 1.
- Dialog validation and confirmation behavior preserved: Task 2.
- Documentation trail updated: Task 3.

