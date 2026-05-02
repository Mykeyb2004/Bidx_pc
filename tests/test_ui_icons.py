from types import SimpleNamespace

import pytest
import tkinter as tk

from bid_writer.gui import ensure_tk_runtime
from bid_writer import ui_icons


def test_icon_registry_covers_main_bid_actions():
    assert {
        "generate",
        "merge",
        "select",
        "stop",
        "outline",
        "fact_card",
        "folder",
        "save",
    }.issubset(ui_icons.ICON_NAMES)


def test_icon_registry_uses_project_tabler_assets():
    assert ui_icons.ICON_SOURCE_NAME == "Tabler Icons"
    assert ui_icons.ICONS_DIR.name == "tabler"
    assert ui_icons.ICON_LICENSE_PATH.exists()
    assert "MIT License" in ui_icons.ICON_LICENSE_PATH.read_text(encoding="utf-8")
    assert "_BITMAP_DATA" not in vars(ui_icons)

    for icon_name in ui_icons.ICON_NAMES:
        icon_path = ui_icons.icon_asset_path(icon_name)
        assert icon_path.exists(), icon_path
        assert icon_path.suffix == ".png"


def test_brand_assets_are_project_local():
    assert ui_icons.BRAND_ASSETS_DIR.name == "brand"
    assert ui_icons.brand_asset_path("logo.svg").exists()

    for size in (16, 32, 64, 128):
        path = ui_icons.brand_asset_path(f"logo_{size}.png")
        assert path.exists(), path
        assert path.suffix == ".png"


def test_brand_asset_path_resolves_inside_brand_dir():
    assert ui_icons.brand_asset_path("logo_32.png") == ui_icons.BRAND_ASSETS_DIR / "logo_32.png"


def test_get_brand_image_rejects_unknown_size():
    assert ui_icons.get_brand_image(object(), 24) is None


def test_set_window_brand_icon_uses_available_brand_images(monkeypatch):
    images = {16: object(), 32: object(), 64: object(), 128: object()}
    calls = []
    window = SimpleNamespace(iconphoto=lambda *args: calls.append(args))

    monkeypatch.setattr(ui_icons, "get_brand_image", lambda _owner, size: images[size])

    assert ui_icons.set_window_brand_icon(window) is True
    assert calls == [(True, images[128], images[64], images[32], images[16])]


def test_configure_icon_button_sets_image_and_left_compound(monkeypatch):
    image = object()
    configured = []
    button = SimpleNamespace(configure=lambda **kwargs: configured.append(kwargs))

    monkeypatch.setattr(ui_icons, "get_icon_image", lambda *_args, **_kwargs: image)

    assert ui_icons.configure_icon_button(button, object(), "generate") is True
    assert configured == [{"image": image, "compound": "left"}]
    assert getattr(button, "_bid_writer_icon_images") == [image]


def test_menu_command_falls_back_when_fake_menu_rejects_image_options(monkeypatch):
    image = object()
    labels = []

    class FakeMenu:
        def add_command(self, *, label, command):
            del command
            labels.append(label)

    monkeypatch.setattr(ui_icons, "get_icon_image", lambda *_args, **_kwargs: image)

    ui_icons.add_icon_menu_command(
        FakeMenu(),
        label="生成所选",
        command=lambda: None,
        icon_name="generate",
        owner=object(),
    )

    assert labels == ["生成所选"]


def test_menu_command_keeps_image_reference_when_supported(monkeypatch):
    image = object()

    class FakeMenu:
        def __init__(self):
            self.entries = []

        def add_command(self, **kwargs):
            self.entries.append(kwargs)

    menu = FakeMenu()
    monkeypatch.setattr(ui_icons, "get_icon_image", lambda *_args, **_kwargs: image)

    ui_icons.add_icon_menu_command(
        menu,
        label="整合标书",
        command=lambda: None,
        icon_name="merge",
        owner=object(),
    )

    assert menu.entries[0]["label"] == "整合标书"
    assert menu.entries[0]["image"] is image
    assert menu.entries[0]["compound"] == "left"
    assert getattr(menu, "_bid_writer_icon_images") == [image]


def test_get_icon_image_creates_tk_photoimage_at_runtime():
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    try:
        root.withdraw()
        image = ui_icons.get_icon_image(root, "generate")

        assert image is not None
        assert image.width() == 16
        assert image.height() == 16
    finally:
        root.destroy()


def test_get_brand_image_creates_tk_photoimage_at_runtime():
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    try:
        root.withdraw()
        image = ui_icons.get_brand_image(root, 32)

        assert image is not None
        assert image.width() == 32
        assert image.height() == 32
    finally:
        root.destroy()
