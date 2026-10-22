import pytest


@pytest.fixture(autouse=True)
def isolate_app_environment_files(monkeypatch, tmp_path):
    """Keep tests independent from a developer's repo-level `.env.local`."""
    env_root = tmp_path.resolve()
    for target in (
        "bid_writer.config.get_shared_config_dir",
        "bid_writer.config_editor.get_shared_config_dir",
        "bid_writer.env_local_prompt.get_shared_config_dir",
        "bid_writer.config.get_resource_root_dir",
        "bid_writer.config_editor.get_resource_root_dir",
    ):
        monkeypatch.setattr(target, lambda: env_root)
