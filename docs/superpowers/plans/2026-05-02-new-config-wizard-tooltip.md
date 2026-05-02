# New Config Wizard Tooltip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hover tooltips to the new-config wizard so every interactive control explains its purpose and the main workflow stays clear.

**Architecture:** Extract the shared hover tooltip widget into a tiny reusable module, then register tooltips from the new wizard with concise, user-facing copy. Keep the change local to the wizard, tooltip text registry, and focused tests so the existing config editor can reuse the same hover behavior without duplicating logic.

**Tech Stack:** Python 3, Tkinter/ttk, pytest, `uv run`

---

### Task 1: Add shared hover tooltip support

**Files:**
- Create: `bid_writer/hover_tooltip.py`
- Modify: `bid_writer/config_editor_dialog.py`

- [ ] **Step 1: Move the hover tooltip implementation into a shared module**

```python
class HoverTooltip:
    def __init__(self, widget: tk.Misc, text: str, *, delay_ms: int = 450):
        ...
```

- [ ] **Step 2: Import the shared helper from the config editor dialog**

```python
from .hover_tooltip import HoverTooltip
```

- [ ] **Step 3: Keep the existing config editor tooltip behavior intact**

```bash
uv run pytest tests/test_config_editor_dialog.py -q
```

Expected: pass.

### Task 2: Register wizard tooltips

**Files:**
- Modify: `bid_writer/new_config_wizard.py`
- Modify: `bid_writer/config_editor_tooltips.py`

- [ ] **Step 1: Add tooltip keys for wizard steps and controls**

```python
FIELD_TOOLTIPS["new_config.step.source"] = "第一步：先决定是从招标文件导入，还是直接手动创建项目骨架。"
```

- [ ] **Step 2: Wire the wizard to the shared hover tooltip helper**

```python
from bid_writer.hover_tooltip import HoverTooltip
```

- [ ] **Step 3: Register tooltips on every interactive control**

```python
self._register_tooltip(select_source_button, "new_config.source.select_file")
```

- [ ] **Step 4: Keep the current wizard behavior unchanged aside from the tooltips**

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: pass.

### Task 3: Verify the tooltip coverage

**Files:**
- Modify: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Add coverage for tooltip keys and shared helper usage**

```python
def test_new_config_wizard_tooltips_cover_core_controls():
    assert get_tooltip_text("new_config.step.source").strip()
```

- [ ] **Step 2: Run the focused test suite**

```bash
uv run pytest tests/test_new_config_wizard.py tests/test_config_editor_dialog.py -q
```

Expected: all pass.

