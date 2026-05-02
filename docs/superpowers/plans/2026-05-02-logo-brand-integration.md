# Logo Brand Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a polished project-local Logo for 标书智写 and surface it in the Tkinter app window and main toolbar.

**Architecture:** Keep the Logo deterministic and package-friendly by storing a hand-authored SVG source plus generated PNG sizes under `bid_writer/assets/brand/`. Extend `bid_writer/ui_icons.py` with brand-image helpers that reuse the existing Tk image cache pattern. Wire `bid_writer/gui.py` to set the window icon and add a compact brand block without changing the main generation workflow.

**Tech Stack:** Python 3, Tkinter/ttk, project-local SVG/PNG assets, `uv run pytest`.

---

## File Structure

- Create `bid_writer/assets/brand/logo.svg`: canonical vector source for the B “智能文档感” Logo.
- Create `bid_writer/assets/brand/logo_16.png`, `logo_32.png`, `logo_64.png`, `logo_128.png`: Tk-loadable raster assets generated from the SVG design.
- Modify `bid_writer/ui_icons.py`: expose brand asset paths, brand image loading, and window icon setup.
- Modify `bid_writer/gui.py`: set app icon and add a compact brand block to the main toolbar.
- Modify `tests/test_ui_icons.py`: cover brand assets and helper behavior.

## Task 1: Brand Asset Registry Tests

**Files:**
- Modify: `tests/test_ui_icons.py`
- Modify: `bid_writer/ui_icons.py`
- Create: `bid_writer/assets/brand/logo.svg`
- Create: `bid_writer/assets/brand/logo_16.png`
- Create: `bid_writer/assets/brand/logo_32.png`
- Create: `bid_writer/assets/brand/logo_64.png`
- Create: `bid_writer/assets/brand/logo_128.png`

- [ ] **Step 1: Write failing brand asset tests**

Add these tests to `tests/test_ui_icons.py` after `test_icon_registry_uses_project_tabler_assets`:

```python
def test_brand_assets_are_project_local():
    assert ui_icons.BRAND_ASSETS_DIR.name == "brand"
    assert ui_icons.brand_asset_path("logo.svg").exists()

    for size in (16, 32, 64, 128):
        path = ui_icons.brand_asset_path(f"logo_{size}.png")
        assert path.exists(), path
        assert path.suffix == ".png"


def test_brand_asset_path_resolves_inside_brand_dir():
    assert ui_icons.brand_asset_path("logo_32.png") == ui_icons.BRAND_ASSETS_DIR / "logo_32.png"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/test_ui_icons.py::test_brand_assets_are_project_local tests/test_ui_icons.py::test_brand_asset_path_resolves_inside_brand_dir -v
```

Expected: FAIL because `ui_icons.BRAND_ASSETS_DIR` or `ui_icons.brand_asset_path` does not exist.

- [ ] **Step 3: Add minimal registry constants and path helper**

In `bid_writer/ui_icons.py`, add these constants after `ICON_LICENSE_PATH`:

```python
BRAND_ASSETS_DIR = Path(__file__).with_name("assets") / "brand"
BRAND_LOGO_SIZES = (16, 32, 64, 128)
```

Add this function after `icon_asset_path`:

```python
def brand_asset_path(name: str) -> Path:
    """Return the project-local path for a brand asset."""
    return BRAND_ASSETS_DIR / name
```

- [ ] **Step 4: Create brand SVG source**

Create `bid_writer/assets/brand/logo.svg` with this exact content:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 112 112" role="img" aria-label="标书智写 Logo">
  <defs>
    <linearGradient id="logoGradient" x1="18" y1="16" x2="94" y2="98" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#0F4C81"/>
      <stop offset="0.56" stop-color="#1D768D"/>
      <stop offset="1" stop-color="#29A37E"/>
    </linearGradient>
  </defs>
  <rect x="12" y="12" width="88" height="88" rx="26" fill="url(#logoGradient)"/>
  <path d="M36 31h25l19 19v31H36c-6 0-10-4-10-10V41c0-6 4-10 10-10Z" fill="#F9FCFF"/>
  <path d="M61 31v18h18" fill="#D7F2ED"/>
  <path d="M39 56h28M39 67h21" fill="none" stroke="#0F4C81" stroke-width="4" stroke-linecap="round"/>
  <circle cx="76" cy="70" r="13" fill="#F4C84C"/>
  <path d="M76 62v16M68 70h16" fill="none" stroke="#103B5B" stroke-width="4" stroke-linecap="round"/>
  <circle cx="30" cy="28" r="3" fill="#F4C84C"/>
  <circle cx="88" cy="35" r="3" fill="#D7F2ED"/>
  <path d="M30 28h12M88 35h-10" fill="none" stroke="#D7F2ED" stroke-width="2" stroke-linecap="round"/>
</svg>
```

- [ ] **Step 5: Generate PNG assets from the SVG design**

Use a local script or existing image library to rasterize the same design into `logo_16.png`, `logo_32.png`, `logo_64.png`, and `logo_128.png`. The PNG files must be valid, square, and match their filename dimensions.

If using Pillow, draw the same shapes directly with antialiasing at 4x scale, then downsample. Do not add a new runtime dependency.

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
uv run pytest tests/test_ui_icons.py::test_brand_assets_are_project_local tests/test_ui_icons.py::test_brand_asset_path_resolves_inside_brand_dir -v
```

Expected: PASS.

## Task 2: Brand Image Loading Helpers

**Files:**
- Modify: `tests/test_ui_icons.py`
- Modify: `bid_writer/ui_icons.py`

- [ ] **Step 1: Write failing helper tests**

Add these tests to `tests/test_ui_icons.py` after the brand asset tests:

```python
def test_get_brand_image_rejects_unknown_size():
    assert ui_icons.get_brand_image(object(), 24) is None


def test_set_window_brand_icon_uses_available_brand_images(monkeypatch):
    images = {16: object(), 32: object(), 64: object(), 128: object()}
    calls = []
    window = SimpleNamespace(iconphoto=lambda *args: calls.append(args))

    monkeypatch.setattr(ui_icons, "get_brand_image", lambda _owner, size: images[size])

    assert ui_icons.set_window_brand_icon(window) is True
    assert calls == [(True, images[128], images[64], images[32], images[16])]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/test_ui_icons.py::test_get_brand_image_rejects_unknown_size tests/test_ui_icons.py::test_set_window_brand_icon_uses_available_brand_images -v
```

Expected: FAIL because `get_brand_image` and `set_window_brand_icon` do not exist.

- [ ] **Step 3: Implement brand image helpers**

In `bid_writer/ui_icons.py`, add these functions after `get_icon_image`:

```python
def get_brand_image(owner: object, size: int) -> tk.PhotoImage | None:
    """Return a cached brand logo image for a supported square PNG size."""
    if size not in BRAND_LOGO_SIZES:
        return None

    path = brand_asset_path(f"logo_{size}.png")
    if not path.exists():
        return None

    cache = _image_cache(owner)
    cache_key = f"brand:{path}"
    if cache_key not in cache:
        try:
            cache[cache_key] = tk.PhotoImage(file=str(path))
        except (RuntimeError, tk.TclError):
            return None
    return cache[cache_key]


def set_window_brand_icon(window: tk.Misc) -> bool:
    """Set the Tk window icon from bundled brand PNGs when supported."""
    images = [image for size in (128, 64, 32, 16) if (image := get_brand_image(window, size)) is not None]
    if not images:
        return False

    try:
        window.iconphoto(True, *images)
    except (AttributeError, TypeError, tk.TclError):
        return False

    for image in images:
        _remember_image(window, image)
    return True
```

- [ ] **Step 4: Run helper tests to verify GREEN**

Run:

```bash
uv run pytest tests/test_ui_icons.py::test_get_brand_image_rejects_unknown_size tests/test_ui_icons.py::test_set_window_brand_icon_uses_available_brand_images -v
```

Expected: PASS.

- [ ] **Step 5: Run existing icon tests**

Run:

```bash
uv run pytest tests/test_ui_icons.py -v
```

Expected: PASS, or skip only the Tk runtime test if Tk is unavailable.

## Task 3: Main Window Brand Integration

**Files:**
- Modify: `bid_writer/gui.py`
- Modify: `tests/test_ui_icons.py`

- [ ] **Step 1: Add a Tk image dimension test**

Add this test after `test_get_icon_image_creates_tk_photoimage_at_runtime`:

```python
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
```

- [ ] **Step 2: Run test to verify RED or asset-dependent GREEN**

Run:

```bash
uv run pytest tests/test_ui_icons.py::test_get_brand_image_creates_tk_photoimage_at_runtime -v
```

Expected: PASS if Task 2 and PNG assets are complete, or SKIP if Tk is unavailable. If it fails because the image cannot load, fix the PNG generation before touching GUI layout.

- [ ] **Step 3: Wire brand helpers into GUI imports**

In `bid_writer/gui.py`, change:

```python
from .ui_icons import add_icon_menu_command, configure_icon_button
```

to:

```python
from .ui_icons import add_icon_menu_command, configure_icon_button, get_brand_image, set_window_brand_icon
```

- [ ] **Step 4: Set the window icon**

In `MainWindow.__init__`, replace the commented icon block:

```python
        # 图标（如果有的话）
        # self.iconbitmap('assets/icon.ico')
```

with:

```python
        set_window_brand_icon(self)
```

- [ ] **Step 5: Add toolbar brand block**

In `MainWindow.create_tool_bar`, after:

```python
        self.action_bar = ttk.Frame(toolbar)
        self.action_bar.pack(fill=tk.X)
```

insert:

```python
        self.brand_frame = ttk.Frame(self.action_bar)
        self.brand_frame.grid(row=0, column=0, sticky="w", padx=(0, 18))
        brand_image = get_brand_image(self, 32)
        if brand_image is not None:
            brand_logo = ttk.Label(self.brand_frame, image=brand_image)
            brand_logo.pack(side=tk.LEFT, padx=(0, 8))
            self._brand_logo_label = brand_logo

        brand_text = ttk.Frame(self.brand_frame)
        brand_text.pack(side=tk.LEFT)
        ttk.Label(brand_text, text=APP_DISPLAY_NAME, style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(brand_text, text="AI bid writing workspace", style="Muted.TLabel").pack(anchor=tk.W)
```

- [ ] **Step 6: Update action bar layout to account for brand block**

In `_layout_action_bar`, replace the method body with:

```python
        del layout_mode
        self.top_outline_controls.grid_forget()
        self.action_frame.grid_forget()
        if hasattr(self, "brand_frame"):
            self.brand_frame.grid_forget()
        self.action_bar.grid_columnconfigure(0, weight=0)
        self.action_bar.grid_columnconfigure(1, weight=0)
        self.action_bar.grid_columnconfigure(2, weight=0)
        self.action_bar.grid_columnconfigure(1, weight=1)
        if hasattr(self, "brand_frame"):
            self.brand_frame.grid(row=0, column=0, sticky="w", padx=(0, 18))
        self.top_outline_controls.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        self.action_frame.grid(row=0, column=2, sticky="se")
```

- [ ] **Step 7: Update available-width calculation**

In `_get_control_layout_mode`, inside:

```python
            if hasattr(self, "action_frame"):
                available_width -= self.action_frame.winfo_reqwidth() + 24
```

add:

```python
            if hasattr(self, "brand_frame"):
                available_width -= self.brand_frame.winfo_reqwidth() + 18
```

- [ ] **Step 8: Run focused tests**

Run:

```bash
uv run pytest tests/test_ui_icons.py -v
```

Expected: PASS, or skip only Tk runtime image tests if Tk is unavailable.

- [ ] **Step 9: Manually smoke test GUI startup**

Run:

```bash
uv run python run.py
```

Expected: main window opens with the Logo as the window/app icon where the OS displays it, and the top toolbar shows a compact Logo + “标书智写” brand block. The “大纲结构” controls and “整合标书/生成所选” buttons remain usable and do not overlap.

## Task 4: Final Verification And Commit

**Files:**
- Verify all files touched in previous tasks.

- [ ] **Step 1: Inspect working tree**

Run:

```bash
git status --short
```

Expected: only planned files are modified or created, aside from pre-existing user-owned changes already present before this work.

- [ ] **Step 2: Run final automated verification**

Run:

```bash
uv run pytest tests/test_ui_icons.py -v
```

Expected: PASS, or skip only tests that explicitly report Tk unavailable.

- [ ] **Step 3: Review diff**

Run:

```bash
git diff -- bid_writer/ui_icons.py bid_writer/gui.py tests/test_ui_icons.py bid_writer/assets/brand/logo.svg
```

Expected: diff matches this plan: brand helpers, toolbar integration, tests, and Logo assets only.

- [ ] **Step 4: Commit implementation**

Run:

```bash
git add bid_writer/assets/brand/logo.svg bid_writer/assets/brand/logo_16.png bid_writer/assets/brand/logo_32.png bid_writer/assets/brand/logo_64.png bid_writer/assets/brand/logo_128.png bid_writer/ui_icons.py bid_writer/gui.py tests/test_ui_icons.py
git commit -m "feat: add brand logo to Tk app"
```

Expected: commit succeeds.
