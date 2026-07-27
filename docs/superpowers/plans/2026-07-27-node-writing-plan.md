# Node Writing Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-outline-node JSON writing-plan library that pre-fills and persists the existing “附加扩写要求” field, uses a stable batch snapshot, and presents the plan as a focused final-stage instruction in the generation prompt.

**Architecture:** Keep JSON parsing, validation, optimistic external-change detection, and atomic persistence inside a new `WritingPlanStore`; `HeadingNode` remains an outline-only object. `BidWriter` owns the configured store and reconstructs it on config reload, while `MainWindow` resolves and saves plans through that facade. `AIWriter` receives only the resolved text through its existing `additional_requirements` argument (whose business meaning becomes “节点撰写计划”) and assembles it immediately before the final task card.

**Tech Stack:** Python 3.10+, standard-library `json`/`hashlib`/`os`, Tkinter/ttk, PyYAML, pytest, uv, GitNexus

---

## Target file structure

| File | Responsibility |
| --- | --- |
| `bid_writer/writing_plan_store.py` | JSON v1 model, node-number extraction, validation, immutable loaded snapshot, atomic save, and conflict detection. |
| `bid_writer/config.py` | Resolve `project.inputs.writing_plan_file` relative to `project.root_dir`. |
| `bid_writer/main.py` | Construct `WritingPlanStore` on startup/reload and provide narrow UI-facing lookup/save/coverage methods. |
| `bid_writer/ai_writer.py` | Reorder the user prompt and name injected text “节点撰写计划”; retain the real API system message. |
| `bid_writer/gui.py` | Single-node prefill/save/dirty-close behavior and batch coverage/snapshot behavior. |
| `tests/test_writing_plan_store.py` | Store and node-number unit tests, including atomic-update conflict protection. |
| `tests/test_config_schema.py` / `tests/test_config_editor.py` | New config path, legacy-generator compatibility, and editor passthrough coverage. |
| `tests/test_prompt_contract.py` | Prompt order, trace contract, conflict wording, and legacy compatibility checks. |
| `tests/test_generation_params_dialog.py` / `tests/test_gui_context_menu.py` | Single-node and batch UI integration through the existing fake-Tk harness. |
| `docs/config_schema.md`, `docs/prompt_contract.md`, `docs/chapter_expansion_mechanism.md` | User-facing config, prompt, and workflow contracts. |
| `config.example.yaml`, `config_松滋助联体.yaml`, `roles/system_gate_rules.md`, `tests/fixtures/roles/system_gate_rules.md` | Example/real configuration and the Mermaid exception to the system language gate. |

## Preconditions and guardrails

The plan changes high-fan-out symbols. Before editing each listed existing symbol, run the indicated GitNexus upstream analysis and record its result in the implementation notes. Warn the user before editing a `HIGH` or `CRITICAL` symbol; stop for direction only when the reported blast radius expands beyond the processes and files covered by this plan.

- `AIWriter.build_prompt_result`, `_build_task_card`, `_build_prompt_contract_blocks`, `_build_scope_reference`, `_build_structure_contract_section`, `_build_scoring_focus_section`, `_build_scoring_labeled_section`, `_build_project_background_section`, `_build_full_context_stable_prefix_sections`, and `build_system_prompt`
- `BidWriter._rebuild_services` and `BidWriter.reload_config`
- `MainWindow._get_generation_params`, `batch_generate`, `_do_batch_generate`, `_generate_into_workspace`, and `GenerationSession.start_generation`

Use `uv run` for every Python/test command. Do not call the production model during automated tests; prompt assertions must inspect `PromptBuildResult` and the real 松滋 configuration only through local parsing/building.

### Task 1: Build the JSON writing-plan store and its pure contract

**Files:**

- Create: `bid_writer/writing_plan_store.py`
- Create: `tests/test_writing_plan_store.py`

- [ ] **Step 1: Write the failing parser and matching tests**

Create tests that exercise the supported JSON v1 document and exact node matching. Use titles with both normal and deceptive numeric prefixes so matching cannot degrade into `startswith`.

```python
from bid_writer.writing_plan_store import WritingPlanStore, extract_node_number


def test_extract_node_number_accepts_only_leading_dot_separated_number():
    assert extract_node_number("1.4.2 进场核验") == "1.4.2"
    assert extract_node_number("1. 项目实施方案") == "1"
    assert extract_node_number("2.3.1：服务机制") == "2.3.1"
    assert extract_node_number("2.3.10 相邻编号") == "2.3.10"
    assert extract_node_number("项目 2.3.1") is None
    assert extract_node_number("2.3.1A 不应识别") is None


def test_load_snapshot_keeps_text_and_matches_exact_node(tmp_path):
    path = tmp_path / "writing-plan.json"
    path.write_text(
        '{"version": 1, "items": ['
        '{"node": "2.3.1", "writing_plan": "第一行\\n第二行"}, '
        '{"node": "2.3.10", "writing_plan": "相邻编号"}]}',
        encoding="utf-8",
    )

    snapshot = WritingPlanStore(path).load_snapshot()

    assert snapshot.get("2.3.1") == "第一行\n第二行"
    assert snapshot.get("2.3.10") == "相邻编号"
    assert snapshot.get("2.3") is None
```

- [ ] **Step 2: Run the focused store tests and verify RED**

Run: `uv run pytest tests/test_writing_plan_store.py -k 'extract_node_number or load_snapshot' -v`

Expected: FAIL because `bid_writer.writing_plan_store` does not exist.

- [ ] **Step 3: Implement the immutable v1 data model and validation boundary**

Create the following public contract. Keep this module independent of `Config`, Tkinter, `HeadingNode`, and `AIWriter` so it remains directly testable.

```python
@dataclass(frozen=True)
class WritingPlanItem:
    node: str
    writing_plan: str


@dataclass(frozen=True)
class WritingPlanSnapshot:
    items: tuple[WritingPlanItem, ...]
    fingerprint: str | None

    def get(self, node: str) -> str | None:
        return next((item.writing_plan for item in self.items if item.node == node), None)


class WritingPlanStoreError(RuntimeError):
    pass


class WritingPlanValidationError(WritingPlanStoreError):
    pass


class WritingPlanExternalModificationError(WritingPlanStoreError):
    pass


def extract_node_number(title: str) -> str | None:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)(?:\.|(?=\s|$|、|:|：|-))", title)
    return match.group(1) if match else None
```

`load_snapshot()` must accept a missing file as `WritingPlanSnapshot((), None)`. For an existing file, read UTF-8 JSON, require an object with `type(version) is int` and `version == 1` (JSON `true` is not a valid version), and require an `items` list. Each item must contain a string `node`; strip its surrounding whitespace into the canonical key, require the result to match `^\d+(?:\.\d+)*$`, require a string `writing_plan`, and reject duplicate canonical keys. Error messages must identify the path and failing condition, for example `撰写计划文件版本必须为 1：<path>` and `撰写计划文件存在重复节点“2.3.1”：<path>`.

Compute the fingerprint as the SHA-256 of the exact on-disk bytes; use `None` only for a missing file. Do not normalize user text, including newlines, while parsing or returning it.

- [ ] **Step 4: Run the parser/matching tests and verify GREEN**

Run: `uv run pytest tests/test_writing_plan_store.py -k 'extract_node_number or load_snapshot' -v`

Expected: PASS.

- [ ] **Step 5: Write failing mutation, format, and conflict tests**

Add tests covering all persistence semantics: first non-empty save creates the file, update preserves an existing item’s list position, new node appends, whitespace-only input removes an item, deleting the only item in a missing library does not create a file, output is two-space indented UTF-8 without escaped Chinese, malformed/duplicate/version-invalid input is never overwritten, and an external write after load blocks save.

```python
def test_save_refuses_to_overwrite_file_changed_since_snapshot(tmp_path):
    path = tmp_path / "writing-plan.json"
    path.write_text('{"version": 1, "items": []}', encoding="utf-8")
    store = WritingPlanStore(path)
    snapshot = store.load_snapshot()
    path.write_text(
        '{"version": 1, "items": [{"node": "9", "writing_plan": "外部编辑"}]}',
        encoding="utf-8",
    )

    with pytest.raises(WritingPlanExternalModificationError, match="外部修改"):
        store.save("2.3.1", "本地编辑", expected_snapshot=snapshot)

    assert '"node": "9"' in path.read_text(encoding="utf-8")
```

- [ ] **Step 6: Run the mutation tests and verify RED**

Run: `uv run pytest tests/test_writing_plan_store.py -k 'save or external_modification or invalid' -v`

Expected: FAIL because `WritingPlanStore.save` is not implemented.

- [ ] **Step 7: Implement optimistic save and atomic replace**

Implement this exact public method and private persistence sequence:

```python
def save(
    self,
    node: str,
    writing_plan: str,
    *,
    expected_snapshot: WritingPlanSnapshot,
) -> WritingPlanSnapshot:
    """Upsert one exact node, or delete it for whitespace-only input."""
```

Validate `node` with the same numeric pattern. Before constructing the new payload, recalculate the current fingerprint and compare it with `expected_snapshot.fingerprint`; raise `WritingPlanExternalModificationError` on any difference, including missing-at-load then created-before-save. Preserve all unaffected `WritingPlanItem` positions; replace an existing item in place, append only a new non-empty node, and remove only the matching node for a whitespace-only value.

For a write, serialize exactly as:

```python
payload = {
    "version": 1,
    "items": [asdict(item) for item in new_items],
}
content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
```

Create the parent directory with `parents=True, exist_ok=True`; create a same-directory temporary file, write and `flush()`/`os.fsync()` it, then use `os.replace(temp_path, self.path)`. After replacement, fsync the parent directory where the platform supports opening directories. On an exception, delete only the explicit temporary file if it exists and re-raise a `WritingPlanStoreError` with the source exception. A non-existent library plus a deletion remains a no-op and returns an empty missing-file snapshot.

- [ ] **Step 8: Run the complete store suite and verify GREEN**

Run: `uv run pytest tests/test_writing_plan_store.py -v`

Expected: PASS.

- [ ] **Step 9: Commit the independent store**

```bash
git add bid_writer/writing_plan_store.py tests/test_writing_plan_store.py
git commit -m "feat: add node writing plan store"
```

### Task 2: Wire the optional configuration and service lifecycle

**Files:**

- Modify: `bid_writer/config.py:247-267,1424-1449`
- Modify: `bid_writer/main.py:13-22,51-72`
- Modify: `bid_writer/ai_writer.py:97-116`
- Modify: `tests/test_config_schema.py`
- Modify: `tests/test_config_editor.py`
- Modify: `tests/test_prompt_contract.py`

- [ ] **Step 1: Run and record the required impact analyses**

Run GitNexus `impact(direction="upstream")` for `Config.chapter_writing_plan_enabled`, `BidWriter._rebuild_services`, `BidWriter.reload_config`, and `AIWriter.__init__`. Preserve the high-risk prompt work for Task 3; this task must only change construction/config behavior.

- [ ] **Step 2: Write failing config and service tests**

Add tests for a `project.inputs.writing_plan_file` relative to `project.root_dir`, missing configuration returning `None`, and `BidWriter.reload_config()` replacing the store after the file setting changes. Add the compatibility regression below to the prompt tests.

```python
def test_writing_plan_file_is_resolved_from_project_root(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "project:\n  root_dir: ./project\n  inputs:\n"
        "    writing_plan_file: ./plans/writing-plan.json\n",
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.writing_plan_file == project_root / "plans" / "writing-plan.json"


def test_configured_file_disables_legacy_generated_chapter_plan(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config["project"].setdefault("inputs", {})["writing_plan_file"] = "./writing-plan.json"
    config._config["processing"]["path"] = "full_context"
    config._config["processing"]["full_context"]["chapter_writing_plan"]["enabled"] = True

    writer = _build_writer(monkeypatch, config)

    assert writer.chapter_writing_plan_generator is None
```

- [ ] **Step 3: Run configuration/service tests and verify RED**

Run: `uv run pytest tests/test_config_schema.py tests/test_prompt_contract.py -k 'writing_plan_file or configured_file_disables' -v`

Expected: FAIL because `Config.writing_plan_file` and `BidWriter.writing_plan_store` do not exist.

- [ ] **Step 4: Add the config property and narrow `BidWriter` facade**

Implement the optional path with no new compatibility aliases:

```python
@property
def writing_plan_file(self) -> Path | None:
    value = self._get_first_defined(("project", "inputs", "writing_plan_file"), default="")
    if not isinstance(value, str) or not value.strip():
        return None
    return self._resolve_project_path(value.strip())
```

In `BidWriter._rebuild_services`, construct `self.writing_plan_store = WritingPlanStore(path)` only when `self.config.writing_plan_file` is not `None`; otherwise set it to `None`. Add three explicit methods so GUI code never imports or manipulates JSON directly:

```python
def load_writing_plan_snapshot(self) -> WritingPlanSnapshot:
    if self.writing_plan_store is None:
        raise WritingPlanStoreError("当前项目未配置撰写计划文件")
    return self.writing_plan_store.load_snapshot()


def save_writing_plan(
    self,
    node: str,
    text: str,
    snapshot: WritingPlanSnapshot,
) -> WritingPlanSnapshot:
    if self.writing_plan_store is None:
        raise WritingPlanStoreError("当前项目未配置撰写计划文件")
    return self.writing_plan_store.save(node, text, expected_snapshot=snapshot)


def summarize_writing_plans(
    self,
    headings: Iterable[HeadingNode],
    snapshot: WritingPlanSnapshot,
) -> WritingPlanCoverage:
    if self.writing_plan_store is None:
        raise WritingPlanStoreError("当前项目未配置撰写计划文件")
    return summarize_writing_plan_coverage(
        (heading.title for heading in headings),
        snapshot,
    )
```

`WritingPlanCoverage` belongs in `writing_plan_store.py` and has this exact shape. Its calculator receives heading titles (or `HeadingNode` objects only through the facade), calls `extract_node_number`, and counts only a non-empty exact plan as covered.

```python
@dataclass(frozen=True)
class WritingPlanCoverage:
    total_headings: int
    numbered_headings: int
    planned_headings: int

    @property
    def unplanned_headings(self) -> int:
        return self.total_headings - self.planned_headings

    @property
    def unnumbered_headings(self) -> int:
        return self.total_headings - self.numbered_headings


def summarize_writing_plan_coverage(
    titles: Iterable[str],
    snapshot: WritingPlanSnapshot,
) -> WritingPlanCoverage:
    title_list = list(titles)
    nodes = [extract_node_number(title) for title in title_list]
    return WritingPlanCoverage(
        total_headings=len(title_list),
        numbered_headings=sum(node is not None for node in nodes),
        planned_headings=sum(
            bool(snapshot.get(node).strip())
            for node in nodes
            if node is not None and snapshot.get(node) is not None
        ),
    )
```

Each facade method must raise `WritingPlanStoreError("当前项目未配置撰写计划文件")` if called without a configured store; callers use `writing_plan_store is None` to select the legacy temporary-input path.

In `AIWriter.__init__`, retain the old `ChapterWritingPlanGenerator` only where no file is configured:

```python
self.chapter_writing_plan_generator = (
    ChapterWritingPlanGenerator(config)
    if config.chapter_writing_plan_enabled and config.writing_plan_file is None
    else None
)
```

This preserves legacy full-context behavior for every project that has not opted in to the JSON library.

- [ ] **Step 5: Protect config-editor passthrough behavior**

Add a regression using a YAML document with `project.inputs.writing_plan_file`, open/save it through the existing config-editor serialization path, and assert that the same nested key/value survives. Do not add a new visual editor control in this feature; the editor’s existing unmanaged-field passthrough is the intended compatibility mechanism.

- [ ] **Step 6: Run configuration, editor, and legacy tests and verify GREEN**

Run: `uv run pytest tests/test_config_schema.py tests/test_config_editor.py tests/test_prompt_contract.py -k 'writing_plan or chapter_writing_plan' -v`

Expected: PASS, including both the new opt-in behavior and the old generated-plan behavior when the file is absent.

- [ ] **Step 7: Commit the configuration lifecycle**

```bash
git add bid_writer/config.py bid_writer/main.py bid_writer/ai_writer.py \
  tests/test_config_schema.py tests/test_config_editor.py tests/test_prompt_contract.py
git commit -m "feat: configure node writing plan library"
```

### Task 3: Rebuild the prompt as a readable execution sequence

**Files:**

- Modify: `bid_writer/ai_writer.py:192-337,422-451,564-815`
- Modify: `tests/test_prompt_contract.py`
- Modify: `roles/system_gate_rules.md`
- Modify: `tests/fixtures/roles/system_gate_rules.md`

- [ ] **Step 1: Run and record impact analysis for every prompt symbol**

Run GitNexus upstream impact for `AIWriter.build_prompt_result`, `_build_task_card`, `_build_prompt_contract_blocks`, `_build_task_basis_line`, `_build_scope_reference`, `_build_structure_contract_section`, `_build_scoring_focus_section`, `_build_scoring_labeled_section`, `_build_project_background_section`, `_build_full_context_stable_prefix_sections`, and `build_system_prompt`. The current paths are high risk because they feed all chapter generation; keep unrelated retrieval changes out of this task.

- [ ] **Step 2: Write failing ordering and conflict tests**

Add one auto/pruned and one full-context test. Each must pass a multi-line `additional_requirements` value and assert all user sections appear in the intended order; do not assert only a substring.

```python
def test_node_writing_plan_is_between_context_and_final_task_card(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(
        heading,
        additional_requirements="先写责任分工，再写闭环台账。\n必须对应评分点。",
        target_words=1200,
    )

    prompt = result.prompt
    assert "## 用户附加要求" not in prompt
    assert prompt.index("## 当前章节边界及招标/评分要求") < prompt.index("## 输出硬约束提醒")
    assert prompt.index("## 输出硬约束提醒") < prompt.index("## 节点撰写计划")
    assert prompt.index("## 节点撰写计划") < prompt.index("## 章节任务卡")
    assert prompt.rstrip().endswith("最终执行说明：直接输出当前章节投标正文。")
```

Also test: no plan means no plan header and no task-card plan instruction; a plan that says “写入同级章节” is bounded by the explicit conflict sentence; fact-card content precedes the node plan; the system prompt remains a separate `system` block; and the Mermaid code-fence exception is present in system rules without duplicating the 松滋 “禁止自解释” rule in the user prompt.

- [ ] **Step 3: Run prompt tests and verify RED**

Run: `uv run pytest tests/test_prompt_contract.py -k 'node_writing_plan or prompt_order or mermaid' -v`

Expected: FAIL because the current prompt still emits `## 用户附加要求`, has structural rules before chapter context, and places task-card content under the old contract.

- [ ] **Step 4: Split prompt helpers by information role rather than source file**

Replace the current `structure_contract` user section with two helpers:

```python
def _build_chapter_context_section(
    self,
    *,
    heading: HeadingNode,
    bid_requirements: str = "",
    scoring_section: str = "",
    project_background: str = "",
) -> str:
    lines = ["## 当前章节边界及招标/评分要求"]
    if bid_requirements.strip():
        lines.extend(["### 招标需求参考", bid_requirements.strip()])
    if project_background.strip():
        lines.extend(["### 项目背景参考", project_background.strip()])
    if scoring_section.strip():
        lines.extend(["### 评分要求", scoring_section.strip()])
    lines.extend(["### 当前章节边界", self._build_scope_reference(heading)])
    return "\n".join(lines)


def _build_output_constraint_reminder_section(self) -> str:
    return "\n".join([
        "## 输出硬约束提醒",
        "- 请严格遵守 system 中全部硬门禁，直接输出当前章节投标正文。",
        "- 节点撰写计划和事实材料不得突破本章边界及招标/评分要求。",
        "- 请优先围绕当前章节任务、上下文材料和章节边界展开，不要偏题，不要与同级章节重复。",
        "- 在满足完整响应前提下，优先提高针对性、可执行性和评审可读性，不为凑篇幅重复展开。",
        *[f"- {rule}" for rule in self.config.prompt_extra_rules],
    ])
```

Make the first helper include only actually available material: full-context bid requirements and scoring criteria; auto-mode project background and/or scoped scoring focus; then parent/current/sibling boundary bullets from `_build_scope_reference`. Change the latter helper to return boundary bullets without its own top-level heading, and adjust the scoring/background builders so their content can sit below this one context heading without nested duplicate `##` headings. Do not invent procurement requirements in auto mode when no source material was retrieved.

Keep `build_system_prompt()` as the first API message. Update `roles/system_gate_rules.md` and its fixture line to say that the English prohibition excludes an explicitly required Mermaid code fence and its necessary syntax. Keep the gate’s “最高优先级” scope to output form, bidder reference, and banned expression; do not claim it overrides tender facts or scoring.

- [ ] **Step 5: Put the node plan immediately before the final task card**

Use the existing function argument to avoid widening generation plumbing, but change its documented meaning to `节点撰写计划`. Append it only when non-blank:

```python
if additional_requirements.strip():
    self._append_prompt_section(
        prompt_parts,
        prompt_sections,
        "node_writing_plan",
        "## 节点撰写计划\n" + additional_requirements,
    )
```

Modify `_build_task_card` to accept `has_node_writing_plan: bool`. When true, include exactly this line before the final execution line:

```text
- 执行要求：按照节点撰写计划组织本节点正文；计划未覆盖的必要评分点应补齐，计划与当前章节边界、招标/评分要求或 system 硬约束冲突时不得照搬。
```

Always end the task card with:

```text
- 最终执行说明：直接输出当前章节投标正文。
```

Retain legacy `chapter_writing_plan` generation only when Task 2 left its generator non-`None`; do not emit both the legacy generated plan and the configured JSON plan.

- [ ] **Step 6: Update prompt-trace contract data**

Replace the old source-oriented block list with the exact business-order contract below; update `EXPECTED_BLOCK_IDS` and all section-name assertions in the prompt tests in the same step.

```python
_PROMPT_CONTRACT_BLOCKS = (
    ("system_constraints", "System Constraints", "system"),
    ("chapter_context", "Chapter Context", "user"),
    ("output_constraints", "Output Constraints", "user"),
    ("fact_card_context", "Fact Card Context", "user"),
    ("node_writing_plan", "Node Writing Plan", "user"),
    ("chapter_task", "Chapter Task", "user"),
)
```

Map those blocks respectively to `[]` with `chars_override=len(system_prompt)`, `["chapter_context"]`, `["output_constraint_reminder"]`, `["fact_card_context"]`, `["node_writing_plan"]`, and `["task_card"]`. Optional blocks remain present in trace with empty `section_names` and zero characters, matching the current fixed-contract convention. Set the node-plan block’s `source_context` to `["additional_requirements"]` only when its section exists. The trace preview now has exactly the same business reading order as the user message and does not double-count project-background/scoring text that has been folded into chapter context.

- [ ] **Step 7: Run all prompt contract tests and verify GREEN**

Run: `uv run pytest tests/test_prompt_contract.py -v`

Expected: PASS. In particular, tests prove the two API roles remain separate, the task card is last, the plan is not called a user add-on, and an empty plan changes neither prompt text nor task-card requirements.

- [ ] **Step 8: Commit the prompt contract change**

```bash
git add bid_writer/ai_writer.py tests/test_prompt_contract.py \
  roles/system_gate_rules.md tests/fixtures/roles/system_gate_rules.md
git commit -m "refactor: anchor node plans before chapter task"
```

### Task 4: Implement single-node prefill, explicit save, and safe close behavior

**Files:**

- Modify: `bid_writer/gui.py:4339-4679`
- Modify: `tests/test_generation_params_dialog.py`

- [ ] **Step 1: Run and record UI impact analysis**

Run GitNexus upstream impact for `MainWindow._get_generation_params` and `batch_generate`. Confirm the existing fact-card interactions remain in scope and preserve their single-node behavior unchanged.

- [ ] **Step 2: Extend the fake-Tk test harness**

Add `bind`, `protocol`, `delete`, and a way to invoke registered button/close callbacks to `_FakeText` / `_FakeDialog` in `tests/test_generation_params_dialog.py`. Add a fake writing-plan facade with `load_writing_plan_snapshot`, `save_writing_plan`, and predictable exceptions. Keep the existing fact-card fakes; this feature must compose with them rather than replacing their assertions.

- [ ] **Step 3: Write failing single-node behavior tests**

Cover these exact cases:

1. A configured file and title `1.4.2 进场核验` prefill the existing text widget and display `节点编号：1.4.2`.
2. Editing marks the plan `未保存`; clicking `保存撰写计划` invokes the facade with the exact multi-line text and replaces the saved snapshot.
3. Clicking `开始扩写` first saves, and a save exception keeps the dialog open and returns `None`.
4. Whitespace-only saved text removes the node record.
5. A title without a leading number shows `当前节点无可用编号`, disables the save button, and still returns its text for this generation only.
6. Closing a dirty configured dialog offers 保存 / 放弃 / 取消; the save branch calls the same save function, the discard branch destroys, and cancel leaves it open.
7. A malformed configured file shows its load error, disables persistence/start, and never treats the broken file as an empty plan library.
8. An external-modification save conflict preserves the typed text; “重新加载撰写计划” asks before discarding dirty text, then loads the new snapshot and re-prefills the field.

- [ ] **Step 4: Run the single-node UI tests and verify RED**

Run: `uv run pytest tests/test_generation_params_dialog.py -k 'writing_plan and single' -v`

Expected: FAIL because the current dialog neither loads nor persists a node plan.

- [ ] **Step 5: Add a self-contained writing-plan state branch in `_get_generation_params`**

Extend the method only with a keyword snapshot for batch callers:

```python
def _get_generation_params(
    self,
    headings: list[HeadingNode],
    *,
    initial_requirements: str = "",
    writing_plan_snapshot: WritingPlanSnapshot | None = None,
):
```

For one heading and a configured store, load a snapshot if none was supplied, calculate `node = extract_node_number(heading.title)`, and initialize the **existing** `req_text` widget from `snapshot.get(node) or ""`. Relabel its associated UI copy as `节点撰写计划（附加扩写要求）`; add an adjacent immutable node/status line and a `保存撰写计划` button. Use `req_text.get("1.0", "end-1c")` for configured saves so meaningful line breaks are not trimmed.

Implement one local `save_current_writing_plan(show_message: bool) -> bool` closure. It must call `self.bid_writer.save_writing_plan(node, raw_text, snapshot)`, replace the captured snapshot only on success, clear dirty state, update the status text, and return false after a `WritingPlanStoreError`. `on_start_generation` calls it before reading generation values and returns without destroying the dialog on failure. For an unnumbered heading, do not call save; keep the raw field value as the transient result.

Bind modification tracking to the `Text` widget, set `dialog.protocol("WM_DELETE_WINDOW", on_close)`, and make the ordinary `关闭` button call the same function. On dirty configured data, use `messagebox.askyesnocancel`: yes saves then closes only on success; no discards; `None` cancels close. Add “重新加载撰写计划” beside the save action; when dirty, require discard confirmation before replacing text/snapshot, and leave the text untouched if reload fails. When no plan file is configured, preserve the current temporary-input behavior and do not display persistence controls.

- [ ] **Step 6: Run the single-node UI tests and existing fact-card test together**

Run: `uv run pytest tests/test_generation_params_dialog.py -k 'writing_plan or start_button_saves_fact_card_references or save_fact_card_references' -v`

Expected: PASS. The fact-card save button and its result tuple remain intact.

- [ ] **Step 7: Commit the single-node dialog work**

```bash
git add bid_writer/gui.py tests/test_generation_params_dialog.py
git commit -m "feat: save node writing plans from generation dialog"
```

### Task 5: Freeze plan state for batch generation without bulk editing

**Files:**

- Modify: `bid_writer/gui.py:3557-3707,4339-4679,4787-5080`
- Modify: `tests/test_generation_params_dialog.py`
- Modify: `tests/test_gui_context_menu.py`

- [ ] **Step 1: Run and record batch/generation impact analysis**

Run GitNexus upstream impact for `MainWindow.batch_generate`, `_do_batch_generate`, `_generate_into_workspace`, and `GenerationSession.start_generation`. The expected blast radius includes batch cancellation/progress, stream startup, and fact-card selection; do not change cancellation semantics or session queue ownership.

- [ ] **Step 2: Write failing batch tests**

Add tests with three selected headings—two numbered where one has a plan, and one unnumbered—to assert all of the following:

```python
def test_batch_generation_uses_one_frozen_writing_plan_snapshot(monkeypatch):
    first = _heading("1.4.1 总体安排")
    second = _heading("1.4.2 进场核验")
    snapshot = FakeSnapshot({"1.4.2": "只写启动准备阶段"})
    generated_requirements = []

    window = _window_with_writing_plan_snapshot(snapshot)
    window._generate_into_workspace = lambda heading, requirements, *_args, **_kwargs: (
        generated_requirements.append((heading.title, requirements)) or "success"
    )

    MainWindow._do_batch_generate(
        window, [first, second], "", 1200, 0, writing_plan_snapshot=snapshot
    )

    assert generated_requirements == [
        ("1.4.1 总体安排", ""),
        ("1.4.2 进场核验", "只写启动准备阶段"),
    ]
```

The dialog test must assert that, when a plan file is configured and more than one heading is selected, it shows `节点撰写计划：1/3 个所选节点已配置` (with the unnumbered count if nonzero), has no editable `Text` plan widget, and returns an empty global requirements value. Add tests that a load failure blocks `batch_generate` before opening the dialog and that no batch code invokes `save_writing_plan`.

- [ ] **Step 3: Run batch tests and verify RED**

Run: `uv run pytest tests/test_generation_params_dialog.py tests/test_gui_context_menu.py -k 'writing_plan and batch' -v`

Expected: FAIL because batch generation currently passes one shared text value to every heading.

- [ ] **Step 4: Load exactly one snapshot before opening the batch dialog**

In `batch_generate`, after selection/model validation and only when `len(selected_headings) > 1` plus `self.bid_writer.writing_plan_store is not None`, call `self.bid_writer.load_writing_plan_snapshot()` once. If it raises `WritingPlanStoreError`, show an error that names the configured file and return without calling `_get_generation_params`. Pass the successful snapshot to `_get_generation_params` and then unchanged to `_do_batch_generate`.

In the multi-heading branch of `_get_generation_params`, call `self.bid_writer.summarize_writing_plans(headings, writing_plan_snapshot)` and render a read-only summary. Do not render the shared text editor, save button, or any batch plan editor. When no plan file is configured, keep the old shared temporary requirement field exactly as it works today.

- [ ] **Step 5: Resolve each batch requirement from the snapshot, not the filesystem**

Add this keyword-only parameter with a backward-compatible default:

```python
def _do_batch_generate(
    self,
    headings: list[HeadingNode],
    additional_requirements: str,
    target_words: int,
    max_mermaid_flowcharts_per_section: int,
    *,
    writing_plan_snapshot: WritingPlanSnapshot | None = None,
    fact_card_mode: bool = False,
    manual_fact_card_selections: Optional[list[FactCardSelection]] = None,
    auto_extract_facts: bool = False,
):
```

Inside the existing loop, calculate the per-heading text before `_generate_into_workspace`:

```python
node = extract_node_number(heading.title)
requirements = (
    writing_plan_snapshot.get(node) or ""
    if writing_plan_snapshot is not None and node is not None
    else additional_requirements
)
```

For a configured batch, `additional_requirements` is empty, so unnumbered/unmatched headings inject nothing. The snapshot must never be reloaded, refreshed, or saved during the loop. Do not change `_generate_into_workspace` or `GenerationSession.start_generation` signatures: they already carry the resolved per-heading requirement through to `AIWriter.prepare_generation`.

- [ ] **Step 6: Run batch and adjacent generation regressions and verify GREEN**

Run: `uv run pytest tests/test_generation_params_dialog.py tests/test_gui_context_menu.py -v`

Expected: PASS, including existing stop/progress assertions and the new frozen-plan behavior.

- [ ] **Step 7: Commit the batch snapshot behavior**

```bash
git add bid_writer/gui.py tests/test_generation_params_dialog.py tests/test_gui_context_menu.py
git commit -m "feat: freeze node plans for batch generation"
```

### Task 6: Publish the configuration, prompt, and operation contracts

**Files:**

- Create: `config.example.yaml`
- Modify: `config_松滋助联体.yaml:1-16`
- Modify: `docs/config_schema.md`
- Modify: `docs/prompt_contract.md`
- Modify: `docs/chapter_expansion_mechanism.md`

- [ ] **Step 1: Write documentation assertions/checks first**

Add a config-schema test that parses the new example and verifies it contains a relative `project.inputs.writing_plan_file`; add a local test fixture JSON file only where a test actually needs a non-empty plan. Do not point the repository example at a user-specific absolute path.

- [ ] **Step 2: Run the documentation/config check and verify RED**

Run: `uv run pytest tests/test_config_schema.py -k 'example or writing_plan_file' -v`

Expected: FAIL because no documented example contains the new field.

- [ ] **Step 3: Add the config and data-format documentation**

Create `config.example.yaml` with a minimal runnable project skeleton and this exact optional fragment:

```yaml
project:
  root_dir: ./project
  inputs:
    outline_file: ./outline.md
    writing_plan_file: ./writing-plan.json
```

Add `writing_plan_file: ./撰写计划.json` under `project.inputs` in `config_松滋助联体.yaml`; because `project.root_dir` is set, document that this resolves inside the 松滋 project directory, not beside the repository configuration. Remove the duplicate `绝对禁止在正文中写入自解释、自评述、自引导的内容` entry from that configuration’s `writing.extra_rules`, because `roles/system_gate_rules.md` already applies the same hard gate once.

In `docs/config_schema.md`, document the optional field, project-root path resolution, v1 JSON schema, exact-match/no-inheritance rule, UTF-8/two-space output format, empty-text deletion, missing-file first-save behavior, and external-edit conflict behavior. Include the exact sample:

```json
{
  "version": 1,
  "items": [
    {
      "node": "2.3.1",
      "writing_plan": "先回应评分点，再按实施步骤、责任分工和成果佐证展开。"
    }
  ]
}
```

- [ ] **Step 4: Update prompt and workflow documents to match the implementation**

In `docs/prompt_contract.md`, replace the old auto/full section orders with the common business order:

1. `chapter_context` — 当前章节边界及招标/评分要求
2. `output_constraint_reminder` — user-side system reminder
3. optional `fact_card_context`
4. optional `node_writing_plan`
5. `task_card` — always last

State that system remains a separate, higher-priority API message. In `docs/chapter_expansion_mechanism.md`, describe the single-node prefill/save/dirty-close flow, temporary behavior for an unnumbered title, batch coverage and frozen snapshot, and the fact that batch never writes plans. Replace references to “用户附加要求” as a separate input source with the unified node-plan meaning.

- [ ] **Step 5: Run documentation/config regressions and verify GREEN**

Run: `uv run pytest tests/test_config_schema.py tests/test_prompt_contract.py -v`

Expected: PASS.

- [ ] **Step 6: Commit documentation and examples**

```bash
git add config.example.yaml config_松滋助联体.yaml docs/config_schema.md \
  docs/prompt_contract.md docs/chapter_expansion_mechanism.md tests/test_config_schema.py
git commit -m "docs: document node writing plan workflow"
```

### Task 7: End-to-end verification and real-config review

**Files:**

- Verify: all files changed by Tasks 1–6

- [ ] **Step 1: Run the complete focused test matrix**

Run:

```bash
uv run pytest \
  tests/test_writing_plan_store.py \
  tests/test_config_schema.py \
  tests/test_config_editor.py \
  tests/test_prompt_contract.py \
  tests/test_generation_params_dialog.py \
  tests/test_gui_context_menu.py -v
```

Expected: PASS.

- [ ] **Step 2: Verify the real 松滋 configuration without calling a model**

Create a temporary `撰写计划.json` under the configured `project.root_dir` only if the user has authorized changing that project directory; otherwise copy the configuration and its referenced outline into a `tmp_path` fixture. Use node `1.4.2` with `只安排启动准备阶段的进场核验、人员到岗、制度衔接与试运行；不得展开第2个月后的规范运行工作。` Build the prompt locally and assert:

```python
assert "## 节点撰写计划" in result.prompt
assert result.prompt.index("## 事实卡片参考") < result.prompt.index("## 节点撰写计划")
assert result.prompt.index("## 节点撰写计划") < result.prompt.index("## 章节任务卡")
assert "第2个月后的规范运行工作" in result.prompt
```

The manual UI acceptance is: open `1.4.2`, confirm the plan pre-fills, modify/save/reopen it, then generate one chapter. Review the generated text for a first-month boundary and no expansion into the sibling “服务周期总体进度安排” topic. Do not label model prose deterministic; the automated acceptance target is the persisted text and prompt boundary, while the final prose review is human judgment.

- [ ] **Step 3: Run the complete suite and whitespace check**

Run:

```bash
uv run pytest
git diff --check
```

Expected: pytest exits 0 and `git diff --check` has no output.

- [ ] **Step 4: Run change detection before final commit**

Run GitNexus `detect_changes(scope="all")`. Review changed symbols and affected execution flows. Confirm the diff contains only the store/config/service/prompt/UI/docs/test paths enumerated above and any already-present user changes are left untouched.

- [ ] **Step 5: Verify repository state after the task commits**

Run: `git status --short`

Expected: no uncommitted feature files. If verification required a corrective edit, rerun its focused test and `detect_changes(scope="all")`, then commit only that correction with a message describing the actual fix.

## Scope coverage self-review

| Confirmed requirement | Plan task(s) |
| --- | --- |
| Optional file config, project-root resolution, JSON v1 | 1, 2, 6 |
| Exact numeric node matching, no inheritance/fuzzy fallback | 1 |
| Read/update/delete, first save, atomic output, external-edit protection | 1, 4 |
| Existing input’s unified “节点撰写计划” semantics | 3, 4, 6 |
| Single-node prefill/save/start-save/dirty-close/no-number fallback | 4 |
| Batch coverage, one frozen snapshot, no batch write | 5 |
| Disable old generated plan only for configured JSON library | 2, 3 |
| System remains separate; reordered user prompt and task-card anchor | 3 |
| Mermaid exception and duplicate 松滋 rule removal | 3, 6 |
| Documentation, production-config review, focused/full regression | 6, 7 |

No parent-plan inheritance, title/path fuzzy matching, batch plan editing, automatic plan rewriting, new auto-mode procurement retrieval, or fact-card data-model changes are included.
