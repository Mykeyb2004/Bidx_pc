from bid_writer.gui import (
    _build_gui_scale_profile,
    _count_text_characters,
    _compute_dialog_target_size,
    _compute_gui_font_delta,
    _format_workspace_char_count,
    _shift_hex_color,
)


def test_compute_gui_font_delta_keeps_standard_display_unchanged():
    assert _compute_gui_font_delta(screen_width=1366, screen_height=768, dpi=96.0) == 0


def test_compute_gui_font_delta_increases_for_retina_like_display():
    assert _compute_gui_font_delta(screen_width=1512, screen_height=982, dpi=144.0) == 1


def test_compute_gui_font_delta_increases_more_for_large_high_resolution_display():
    assert _compute_gui_font_delta(screen_width=2560, screen_height=1440, dpi=96.0) == 2


def test_build_gui_scale_profile_scales_fonts_and_spacing_together():
    profile = _build_gui_scale_profile(screen_width=1920, screen_height=1080, dpi=96.0)

    assert profile.default_font_size == 12
    assert profile.compact_font_size == 11
    assert profile.heading_font_size == 13
    assert profile.tree_rowheight == 32
    assert profile.button_padding == (14, 8)
    assert profile.field_padding == (7, 6)
    assert profile.text_padding == (11, 9)


def test_compute_gui_font_delta_allows_manual_adjustment():
    assert _compute_gui_font_delta(
        screen_width=1366,
        screen_height=768,
        dpi=96.0,
        manual_delta=1,
    ) == 1


def test_compute_dialog_target_size_preserves_minimum_space_for_scaled_content():
    width, height = _compute_dialog_target_size(
        requested_width=500,
        requested_height=268,
        min_width=520,
        min_height=280,
        extra_width=24,
        extra_height=20,
    )

    assert width == 524
    assert height == 288


def test_compute_dialog_target_size_keeps_existing_larger_window_size():
    width, height = _compute_dialog_target_size(
        requested_width=480,
        requested_height=250,
        min_width=520,
        min_height=280,
        current_width=560,
        current_height=320,
    )

    assert width == 560
    assert height == 320


def test_shift_hex_color_darkens_surface_color_for_subtle_borders():
    assert _shift_hex_color("#dcdad5", -18) == "#cac8c3"


def test_count_text_characters_keeps_newlines_for_workspace_display():
    assert _count_text_characters("第一段\n第二段") == 7


def test_format_workspace_char_count_uses_placeholder_without_active_node():
    assert _format_workspace_char_count(None) == "当前节点已生成字符数：-"


def test_format_workspace_char_count_formats_large_numbers_for_readability():
    assert _format_workspace_char_count(12345) == "当前节点已生成字符数：12,345"
