"""
Lightweight icon helpers for Tk/ttk controls.

The desktop UI uses a small local subset of Tabler Icons rendered to PNG so
runtime code can stay dependency-free and Tk can load images directly.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Callable


ICON_SOURCE_NAME = "Tabler Icons"
ICONS_DIR = Path(__file__).with_name("assets") / "icons" / "tabler"
ICON_LICENSE_PATH = ICONS_DIR / "LICENSE.tabler"

ICON_NAMES = frozenset(
    {
        "add",
        "back",
        "browse",
        "clear",
        "close",
        "edit",
        "expand",
        "fact_card",
        "folder",
        "format",
        "generate",
        "help",
        "import",
        "merge",
        "next",
        "outline",
        "refresh",
        "save",
        "scan",
        "select",
        "settings",
        "stop",
        "switch",
    }
)


def icon_asset_path(name: str) -> Path:
    """Return the project-local PNG path for a logical icon name."""
    return ICONS_DIR / f"{name}.png"


def _image_cache(owner: object) -> dict[str, tk.PhotoImage]:
    cache = getattr(owner, "_bid_writer_icon_cache", None)
    if cache is None:
        cache = {}
        setattr(owner, "_bid_writer_icon_cache", cache)
    return cache


def _remember_image(owner: object, image: object) -> None:
    images = getattr(owner, "_bid_writer_icon_images", None)
    if images is None:
        images = []
        setattr(owner, "_bid_writer_icon_images", images)
    if image not in images:
        images.append(image)


def get_icon_image(owner: object, name: str, *, foreground: str = "#2f3a45") -> tk.PhotoImage | None:
    """Return a cached 16x16 icon image, or None when Tk cannot load it."""
    del foreground
    if name not in ICON_NAMES:
        return None

    path = icon_asset_path(name)
    if not path.exists():
        return None

    cache = _image_cache(owner)
    cache_key = str(path)
    if cache_key not in cache:
        try:
            cache[cache_key] = tk.PhotoImage(file=str(path))
        except (RuntimeError, tk.TclError):
            return None
    return cache[cache_key]


def configure_icon_button(
    button: tk.Misc,
    owner: object,
    icon_name: str,
    *,
    foreground: str = "#2f3a45",
) -> bool:
    """Attach an icon to a ttk button while preserving a text fallback."""
    image = get_icon_image(owner, icon_name, foreground=foreground)
    if image is None:
        return False
    try:
        button.configure(image=image, compound="left")
    except (AttributeError, TypeError, tk.TclError):
        return False
    _remember_image(button, image)
    return True


def add_icon_menu_command(
    menu: tk.Menu,
    *,
    label: str,
    command: Callable[[], object],
    icon_name: str,
    owner: object,
    foreground: str = "#2f3a45",
) -> None:
    """Add a menu command with an image when supported, otherwise plain text."""
    image = get_icon_image(owner, icon_name, foreground=foreground)
    if image is None:
        menu.add_command(label=label, command=command)
        return

    try:
        menu.add_command(label=label, command=command, image=image, compound="left")
    except TypeError:
        menu.add_command(label=label, command=command)
        return
    except tk.TclError:
        menu.add_command(label=label, command=command)
        return
    _remember_image(menu, image)
