from pathlib import Path
from types import SimpleNamespace

import pytest

from bid_writer import config as config_module
from bid_writer import gui_state
from scripts import build_nuitka as build


def test_app_keeps_writes_outside_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / "Applications" / "bid-writer.app" / "Contents" / "MacOS"
    source = bundle / "bid_writer" / "gui_state.py"
    monkeypatch.setattr(gui_state, "__file__", str(source))
    monkeypatch.setattr(gui_state, "__compiled__", SimpleNamespace(containing_dir=str(bundle)), raising=False)
    monkeypatch.setattr(gui_state.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path)

    resources = gui_state.get_resource_root_dir()
    data = gui_state.get_application_root_dir()
    assert resources == bundle
    assert data == tmp_path / "home" / ".bid-writer"
    assert gui_state.get_default_base_dir() == data / "config"
    assert gui_state.get_state_file() == data / "state" / gui_state.STATE_FILENAME
    gui_state.save_gui_state(gui_state.GUIState(last_config_path="/projects/bid/config.yaml"))
    assert gui_state.load_gui_state().last_config_path == "/projects/bid/config.yaml"
    gui_state.remember_last_config("/projects/next/config.yaml")
    assert gui_state.load_gui_state().last_config_path == "/projects/next/config.yaml"
    assert gui_state.get_startup_config_candidates()[0] == "/projects/next/config.yaml"
    assert not bundle.exists()


def test_compiled_caches_and_trace_use_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(gui_state, "__compiled__", SimpleNamespace(containing_dir=str(tmp_path / "bundle")), raising=False)
    monkeypatch.setattr(gui_state.sys, "platform", "darwin")
    monkeypatch.setattr(gui_state, "get_application_root_dir", lambda: tmp_path / "data")
    source = tmp_path / "config.yaml"
    source.write_text("project: {}\n", encoding="utf-8")
    config = config_module.Config(str(source))
    assert config.embedding_cache_dir == str(tmp_path / "data" / "cache" / "embedding_cache")
    assert config.generation_trace_directory == str(tmp_path / "data" / "logs" / "generation_traces")


def test_source_paths_remain_independent_of_working_directory(monkeypatch, tmp_path):
    monkeypatch.delattr(gui_state, "__compiled__", raising=False)
    monkeypatch.chdir(tmp_path)
    assert gui_state.get_default_base_dir() == tmp_path
    assert gui_state.get_application_root_dir() == Path(gui_state.__file__).resolve().parents[1]


def test_clean_removes_only_build_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    for relative in ("bid_writer/__pycache__", "scripts/__pycache__", "tests/unit/__pycache__", ".pytest_cache", "caches", "output"):
        directory = tmp_path / relative
        directory.mkdir(parents=True)
        (directory / "keep.txt").write_text("data", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text("project: {}", encoding="utf-8")
    build.clean_python_caches()
    assert not (tmp_path / "bid_writer/__pycache__").exists()
    assert not (tmp_path / "tests/unit/__pycache__").exists()
    assert not (tmp_path / ".pytest_cache").exists()
    assert (tmp_path / "caches/keep.txt").read_text() == "data"
    assert (tmp_path / "output/keep.txt").read_text() == "data"
    assert config.exists()


def test_cleanup_refuses_symlinks_outside_build(tmp_path):
    outside = tmp_path / "project-data"
    outside.mkdir()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    link = build_dir / "target"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        build.remove_build_path(link, build_dir)
    assert outside.exists()


def test_dry_run_never_cleans_or_runs_compiler(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "check_environment", lambda: pytest.fail("environment check in dry run"))
    monkeypatch.setattr(build, "remove_build_path", lambda *args: pytest.fail("cleanup in dry run"))
    monkeypatch.setattr(build.subprocess, "run", lambda *args, **kwargs: pytest.fail("subprocess in dry run"))
    assert build.main(["--dry-run", "--no-cache"]) == 0
    assert list(tmp_path.iterdir()) == []


def test_platform_modes_and_compiler_failure(monkeypatch, tmp_path):
    assert build.resolve_mode("auto", "darwin") == "app"
    assert build.resolve_mode("auto", "win32") == "standalone"
    with pytest.raises(ValueError):
        build.resolve_mode("app", "win32")
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "check_environment", lambda: None)

    def fail_compiler(*args, **kwargs):
        raise build.subprocess.CalledProcessError(9, args[0])

    monkeypatch.setattr(build.subprocess, "run", fail_compiler)
    assert build.main([]) == 1
    assert not (tmp_path / "dist").exists()
