import bid_writer.gui as gui
from bid_writer.gui import (
    MainWindow,
    _build_gui_scale_profile,
    _build_generation_error_feedback,
    _compute_main_outline_pane_width,
    _compute_main_window_target_size,
    _compute_outline_tree_column_widths,
    _count_text_characters,
    _compute_dialog_target_size,
    _compute_centered_window_geometry,
    _compute_gui_font_delta,
    _format_batch_generation_failure_message,
    _format_heading_tree_title,
    _format_workspace_char_count,
    _shift_hex_color,
)


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


class _FakeActivationWindow:
    def __init__(self):
        self.calls: list[object] = []

    def deiconify(self):
        self.calls.append("deiconify")

    def lift(self):
        self.calls.append("lift")

    def update_idletasks(self):
        self.calls.append("update_idletasks")

    def focus_force(self):
        self.calls.append("focus_force")

    def attributes(self, *args):
        self.calls.append(("attributes", args))

    def after(self, delay_ms, callback):
        self.calls.append(("after", delay_ms))
        callback()


class _FakeStartupActivationWindow:
    def __init__(self):
        self.scheduled_delays: list[int] = []
        self.scheduled_callbacks = []

    def after(self, delay_ms, callback):
        self.scheduled_delays.append(delay_ms)
        self.scheduled_callbacks.append(callback)


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


def test_main_window_target_size_uses_sixty_five_percent_cap_on_large_display():
    width, height = _compute_main_window_target_size(screen_width=2048, screen_height=1226)

    assert width == 1331
    assert height == 796


def test_main_window_target_size_leaves_breathing_room_on_low_resolution_display():
    width, height = _compute_main_window_target_size(screen_width=1366, screen_height=768)

    assert width == 887
    assert height == 499


def test_main_window_min_size_shrinks_when_screen_is_shorter_than_default_minimum():
    size_fn = getattr(gui, "_compute_main_window_min_size", None)
    assert size_fn is not None

    width, height = size_fn(screen_width=1024, screen_height=600)

    assert width == 665
    assert height == 390


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


def test_activate_window_requests_frontmost_focus_and_releases_topmost():
    activate_fn = getattr(gui, "_activate_window", None)
    assert activate_fn is not None
    fake_window = _FakeActivationWindow()

    activate_fn(fake_window)

    assert fake_window.calls == [
        "deiconify",
        "lift",
        "update_idletasks",
        "focus_force",
        ("attributes", ("-topmost", True)),
        ("after", 200),
        ("attributes", ("-topmost", False)),
    ]


def test_startup_activation_is_scheduled_after_main_window_setup(monkeypatch):
    activated = []
    monkeypatch.setattr(gui, "_activate_window", lambda window: activated.append(window), raising=False)
    fake_window = _FakeStartupActivationWindow()

    MainWindow._schedule_startup_activation(fake_window)

    assert fake_window.scheduled_delays == [50]
    fake_window.scheduled_callbacks[0]()
    assert activated == [fake_window]


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


def test_compute_centered_window_geometry_uses_screen_center():
    geometry = _compute_centered_window_geometry(
        width=887,
        height=499,
        screen_width=1366,
        screen_height=768,
    )

    assert geometry == "887x499+239+134"


def test_screen_limited_dialog_size_caps_target_and_minimum_to_display():
    size_fn = getattr(gui, "_compute_screen_limited_dialog_size", None)
    assert size_fn is not None

    size = size_fn(
        desired_width=1280,
        desired_height=860,
        min_width=1100,
        min_height=760,
        screen_width=1366,
        screen_height=768,
    )

    assert size.width == 1229
    assert size.height == 691
    assert size.min_width == 1100
    assert size.min_height == 691


def test_shift_hex_color_darkens_surface_color_for_subtle_borders():
    assert _shift_hex_color("#dcdad5", -18) == "#cac8c3"


def test_count_text_characters_keeps_newlines_for_workspace_display():
    assert _count_text_characters("第一段\n第二段") == 7


def test_format_workspace_char_count_uses_placeholder_without_active_node():
    assert _format_workspace_char_count(None) == "当前节点已生成字符数：-"


def test_format_workspace_char_count_formats_large_numbers_for_readability():
    assert _format_workspace_char_count(12345) == "当前节点已生成字符数：12,345"


def test_format_heading_tree_title_returns_plain_title():
    assert _format_heading_tree_title("进度计划安排") == "进度计划安排"


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
