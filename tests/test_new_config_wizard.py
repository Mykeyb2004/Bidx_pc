from pathlib import Path
import tkinter as tk
from types import SimpleNamespace

import pytest

from bid_writer.new_config_wizard import NewConfigWizardDialog, WIZARD_STEPS


class StubVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class StubButton:
    def __init__(self):
        self.config_calls = []

    def configure(self, **kwargs):
        self.config_calls.append(kwargs)


class StubFrame:
    def __init__(self):
        self.raised = False

    def tkraise(self):
        self.raised = True


def _dialog(tmp_path: Path) -> NewConfigWizardDialog:
    dialog = NewConfigWizardDialog.__new__(NewConfigWizardDialog)
    dialog.current_step_index = 0
    dialog.max_completed_step_index = 0
    dialog.result = {"saved_path": None, "apply_path": None}
    dialog.status_var = StubVar("")
    dialog.back_button = StubButton()
    dialog.next_button = StubButton()
    dialog.step_buttons = []
    dialog.step_frames = {key: StubFrame() for key in [step.key for step in WIZARD_STEPS]}
    dialog.state = SimpleNamespace(
        source_path=None,
        project_root=tmp_path,
        config_path=tmp_path / "config.yaml",
        requirements_path=None,
        scoring_path=None,
        bidder_name="",
    )
    return dialog


def test_wizard_defines_five_steps():
    assert [step.key for step in WIZARD_STEPS] == [
        "source",
        "location",
        "materials",
        "basics",
        "review",
    ]


def test_constructor_builds_initial_wizard_shell(tmp_path: Path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    dialog = None
    try:
        root.withdraw()
        config_path = tmp_path / "config_test.yaml"

        dialog = NewConfigWizardDialog(root, config_path=config_path)

        assert dialog.result == {"saved_path": None, "apply_path": None}
        assert dialog.current_step_index == 0
        assert dialog.max_completed_step_index == 0
        assert dialog.state.config_path == config_path.resolve()
        assert set(dialog.step_frames) == {step.key for step in WIZARD_STEPS}
    finally:
        if dialog is not None:
            dialog.destroy()
        root.destroy()


def test_go_next_advances_when_current_step_valid(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog._validate_current_step = lambda: True

    NewConfigWizardDialog._go_next(dialog)

    assert dialog.current_step_index == 1
    assert dialog.max_completed_step_index == 1


def test_go_next_stays_when_current_step_invalid(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog._validate_current_step = lambda: False

    NewConfigWizardDialog._go_next(dialog)

    assert dialog.current_step_index == 0
    assert dialog.max_completed_step_index == 0


def test_go_back_moves_to_previous_step(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.current_step_index = 2

    NewConfigWizardDialog._go_back(dialog)

    assert dialog.current_step_index == 1


def test_jump_to_step_only_allows_completed_steps(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.max_completed_step_index = 1

    NewConfigWizardDialog._jump_to_step(dialog, 2)
    assert dialog.current_step_index == 0

    NewConfigWizardDialog._jump_to_step(dialog, 1)
    assert dialog.current_step_index == 1


def test_sync_footer_sets_status_and_final_button_text(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.current_step_index = len(WIZARD_STEPS) - 1

    NewConfigWizardDialog._sync_footer(dialog)

    assert dialog.status_var.get() == "第 5 步，共 5 步"
    assert dialog.next_button.config_calls[-1]["text"] == "保存并应用"
