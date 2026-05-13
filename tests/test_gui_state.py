import json
import sys
from pathlib import Path

from bid_writer.gui import _resolve_generation_dialog_defaults
from bid_writer.gui_state import (
    get_default_base_dir,
    get_startup_config_candidates,
    get_state_file,
    load_gui_state,
    remember_generation_dialog_settings,
)


def test_remember_generation_dialog_settings_persists_values(tmp_path):
    remember_generation_dialog_settings(1800, 2, base_dir=tmp_path)

    state = load_gui_state(tmp_path)

    assert state.last_generation_target_words == 1800
    assert state.last_max_mermaid_flowcharts_per_section == 2


def test_load_gui_state_ignores_invalid_generation_values(tmp_path):
    state_file = get_state_file(tmp_path)
    state_file.write_text(
        json.dumps(
            {
                "last_config_path": "config.yaml",
                "last_generation_target_words": "abc",
                "last_max_mermaid_flowcharts_per_section": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    state = load_gui_state(tmp_path)

    assert state.last_config_path == "config.yaml"
    assert state.last_generation_target_words is None
    assert state.last_max_mermaid_flowcharts_per_section is None


def test_default_base_dir_prefers_frozen_executable(monkeypatch, tmp_path):
    exe_path = tmp_path / "bid-writer.exe"
    exe_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_path))

    assert get_default_base_dir() == tmp_path.resolve()


def test_startup_candidates_use_exe_dir_when_frozen(monkeypatch, tmp_path):
    exe_dir = tmp_path / "app"
    cwd = tmp_path / "other"
    exe_dir.mkdir()
    cwd.mkdir()
    (exe_dir / "config.yaml").write_text("project: {}\n", encoding="utf-8")
    (cwd / "config.yaml").write_text("project: {}\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "bid-writer.exe"))

    candidates = get_startup_config_candidates()

    assert Path(candidates[0]) == (exe_dir / "config.yaml").resolve()


def test_startup_candidates_can_skip_discovered_project_configs(tmp_path):
    discovered_config = tmp_path / "config_项目.yaml"
    discovered_config.write_text("project: {}\n", encoding="utf-8")

    manual_candidates = get_startup_config_candidates(
        base_dir=tmp_path,
        include_discovered_configs=False,
    )
    all_candidates = get_startup_config_candidates(
        base_dir=tmp_path,
        include_discovered_configs=True,
    )

    assert discovered_config.resolve() not in [Path(path) for path in manual_candidates]
    assert discovered_config.resolve() in [Path(path) for path in all_candidates]


def test_resolve_generation_dialog_defaults_prefers_persisted_values():
    target_words, mermaid_limit = _resolve_generation_dialog_defaults(
        persisted_target_words=2200,
        persisted_max_mermaid_flowcharts_per_section=3,
        target_words_default=1500,
        target_words_min=100,
        target_words_max=5000,
    )

    assert target_words == 2200
    assert mermaid_limit == 3


def test_resolve_generation_dialog_defaults_clamps_out_of_range_values():
    target_words, mermaid_limit = _resolve_generation_dialog_defaults(
        persisted_target_words=99999,
        persisted_max_mermaid_flowcharts_per_section=-5,
        target_words_default=1500,
        target_words_min=100,
        target_words_max=5000,
    )

    assert target_words == 5000
    assert mermaid_limit == 0
