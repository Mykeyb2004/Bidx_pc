from bid_writer.config_editor_tooltips import get_tooltip_text


def test_config_editor_tooltips_cover_key_sections_and_fields():
    keys = [
        "section.project",
        "section.processing",
        "project.root_dir",
        "project.bid_requirements_file",
        "writing.role_mode",
        "writing.hard_constraints_text",
        "processing.path",
        "processing.hybrid_extract.retrieval.vector_enabled",
        "models.generation.model",
        "runtime.trace.enabled",
        "runtime.output.overwrite_existing",
    ]

    for key in keys:
        assert get_tooltip_text(key).strip(), f"missing tooltip: {key}"
