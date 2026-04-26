from bid_writer.gui import (
    MainWindow,
    _build_gui_scale_profile,
    _build_generation_error_feedback,
    _compute_main_outline_pane_width,
    _compute_main_window_target_size,
    _compute_outline_tree_column_widths,
    _count_text_characters,
    _compute_dialog_target_size,
    _compute_gui_font_delta,
    _format_dependency_summary_busy_message,
    _format_batch_generation_failure_message,
    _format_dependency_tooltip,
    _format_heading_tree_title,
    _format_workspace_char_count,
    _extract_heading_serial_token,
    _shift_hex_color,
)
from bid_writer.outline_parser import HeadingNode


class _FakeLayoutWidget:
    def __init__(self, *, width: int = 1, reqwidth: int = 1):
        self._width = width
        self._reqwidth = reqwidth
        self.grid_kwargs = None

    def winfo_width(self):
        return self._width

    def winfo_reqwidth(self):
        return self._reqwidth

    def grid_forget(self):
        pass

    def grid(self, **kwargs):
        self.grid_kwargs = kwargs


class _FakeGridContainer:
    def __init__(self):
        self.configured_columns = []

    def grid_columnconfigure(self, column, **kwargs):
        self.configured_columns.append((column, kwargs))


class _FakeMainWindowForControlLayout:
    def __init__(self):
        self._control_layout_mode = "stacked"
        self.control_group = _FakeLayoutWidget(width=1)
        self.action_frame = _FakeLayoutWidget(reqwidth=260)
        self.search_filter_group = _FakeLayoutWidget(reqwidth=440)
        self.selection_action_group = _FakeLayoutWidget(reqwidth=120)

    def winfo_width(self):
        return 640


class _FakeMainWindowForActionLayout:
    def __init__(self):
        self.top_outline_controls = _FakeLayoutWidget()
        self.action_frame = _FakeLayoutWidget()
        self.action_bar = _FakeGridContainer()


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


def test_main_window_target_size_matches_screenshot_width_on_large_display():
    width, height = _compute_main_window_target_size(screen_width=2048, screen_height=1226)

    assert width == 2000
    assert height == 1176


def test_main_outline_pane_width_uses_left_right_ratio_for_wide_window():
    assert _compute_main_outline_pane_width(total_width=1960) == 608


def test_outline_tree_columns_split_title_status_progress_by_ratio():
    assert _compute_outline_tree_column_widths(total_width=600) == (396, 102, 102)


def test_top_control_layout_accounts_for_action_buttons_before_window_is_realized():
    fake_window = _FakeMainWindowForControlLayout()

    layout_mode = MainWindow._get_control_layout_mode(fake_window)

    assert layout_mode == "stacked"


def test_action_buttons_align_to_bottom_of_top_controls():
    fake_window = _FakeMainWindowForActionLayout()

    MainWindow._layout_action_bar(fake_window, "single")

    assert fake_window.action_frame.grid_kwargs["sticky"] == "se"


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


def test_format_heading_tree_title_adds_dependency_marker():
    assert _format_heading_tree_title("进度计划安排", is_dependency_source=True) == "进度计划安排 🔗"


def test_format_heading_tree_title_shows_dependency_count_when_reused_multiple_times():
    assert _format_heading_tree_title("进度计划安排", depends_on_count=3) == "进度计划安排 ⇢3章"


def test_format_heading_tree_title_shows_both_source_and_target_markers():
    assert (
        _format_heading_tree_title(
            "进度计划安排",
            is_dependency_source=True,
            depends_on_count=2,
        )
        == "进度计划安排 🔗 ⇢2章"
    )


def test_extract_heading_serial_token_supports_multilevel_numbers():
    assert _extract_heading_serial_token("3.2.1 质量保障措施") == "3.2.1"


def test_extract_heading_serial_token_supports_chinese_outline_numbers():
    assert _extract_heading_serial_token("（三）实施方案") == "（三）"


def test_format_dependency_tooltip_lists_dependency_titles():
    dependencies = [
        HeadingNode(level=3, title="3.2.1 质量保障措施", full_path="", line_number=1),
        HeadingNode(level=3, title="应急保障机制", full_path="", line_number=2),
    ]

    tooltip = _format_dependency_tooltip(dependencies)

    assert "当前章节依赖了 2 个章节" in tooltip
    assert "- 3.2.1 质量保障措施" in tooltip
    assert "- 应急保障机制" in tooltip


def test_format_dependency_summary_busy_message_for_check_mode():
    message = _format_dependency_summary_busy_message("check", 2)

    assert "正在后台检查 2 个依赖章节" in message
    assert "自动刷新可复用结果" in message


def test_format_dependency_summary_busy_message_for_generate_mode():
    message = _format_dependency_summary_busy_message("generate", 3)

    assert "正在后台为 3 个依赖章节提炼关联摘要" in message
    assert "自动继续当前生成流程" in message


def test_build_generation_error_feedback_for_timeout_before_output():
    class APITimeoutError(Exception):
        pass

    feedback = _build_generation_error_feedback(
        heading_title="实施方案",
        heading_full_path="项目 > 实施方案",
        stage_label="等待模型首批输出",
        exc=APITimeoutError("timed out while waiting for response"),
        has_partial_output=False,
    )

    assert feedback.category_title == "模型调用超时"
    assert not feedback.append_to_workspace
    assert "正文开始输出前就失败了" in feedback.workspace_body_text
    assert "等待模型首批输出" in feedback.dialog_message


def test_build_generation_error_feedback_for_partial_output_connection_error():
    class APIConnectionError(Exception):
        pass

    feedback = _build_generation_error_feedback(
        heading_title="服务保障",
        heading_full_path="项目 > 服务保障",
        stage_label="接收模型输出",
        exc=APIConnectionError("Connection error."),
        has_partial_output=True,
    )

    assert feedback.category_title == "无法连接模型服务"
    assert feedback.append_to_workspace
    assert "已返回内容会保留在工作区" in feedback.workspace_body_text
    assert "接收模型输出" in feedback.workspace_body_text


def test_format_batch_generation_failure_message_summarizes_titles():
    message = _format_batch_generation_failure_message(
        ["第一章", "第二章", "第三章", "第四章", "第五章", "第六章"]
    )

    assert "有 6 个章节失败" in message
    assert "- 第一章" in message
    assert "- 第五章" in message
    assert "其余 1 个章节" in message
