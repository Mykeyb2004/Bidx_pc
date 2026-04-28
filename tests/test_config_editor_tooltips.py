from bid_writer.config_editor_tooltips import get_tooltip_text


def test_config_editor_tooltips_cover_key_sections_and_fields():
    keys = [
        "section.project",
        "section.processing",
        "project.root_dir",
        "project.bid_requirements_file",
        "writing.role_mode",
        "writing.hard_constraints_text",
        "writing.max_mermaid_flowcharts_per_section",
        "processing.path",
        "processing.project_background.enabled",
        "processing.full_context.chapter_writing_plan.enabled",
        "processing.hybrid_extract.retrieval.vector_enabled",
        "runtime.trace.enabled",
        "runtime.output.overwrite_existing",
    ]

    for key in keys:
        assert get_tooltip_text(key).strip(), f"missing tooltip: {key}"


def test_config_editor_tooltips_omit_deprecated_writing_fields():
    assert get_tooltip_text("writing.allow_markdown_headings") == ""
    assert get_tooltip_text("writing.allow_english_terms") == ""
    assert get_tooltip_text("writing.summary_title") == ""
    assert get_tooltip_text("writing.output_format") == ""
    assert get_tooltip_text("writing.first_line_template") == ""
