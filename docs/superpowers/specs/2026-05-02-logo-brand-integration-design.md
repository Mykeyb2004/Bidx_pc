# 标书智写 Logo 与主窗口接入设计

## 背景

标书智写当前是 Python + Tkinter 桌面应用，已有 `bid_writer/assets/icons/tabler/` 存放本地按钮图标，并通过 `bid_writer/ui_icons.py` 统一加载。主窗口标题为“标书智写 - GUI版”，顶部工具区目前直接从“大纲结构”与操作按钮开始，缺少独立品牌识别。

本次目标是为应用配置一个精美、专业、可打包的 Logo，并把它接入 app，使用户打开软件时能感知产品身份，同时不引入新的运行时依赖。

## 视觉方向

采用已确认的 B 方案：“智能文档感”。

- 主符号：蓝绿渐变圆角底板 + 白色结构化文档 + 黄色智能节点。
- 含义：文档代表标书正文和大纲结构，黄色节点代表 AI 生成/智能补全，蓝绿代表专业、可信、效率。
- 风格：现代、清爽、软件产品化，但保持政府采购和正式文档场景所需的稳重感。
- 小尺寸策略：Logo 在 16px、32px、64px 下仍应能看出“文档 + 智能节点”的核心轮廓，不依赖细小文字。

## 方案选择

采用“Logo 资产 + 接入主窗口”的方案。

不选择只加资产，因为用户打开 app 时感知弱；不选择 AI 位图 Logo，因为复杂位图在窗口图标和 Tk 小尺寸控件中不稳定，也不利于后续打包维护。

## 资源设计

新增品牌资源目录：

- `bid_writer/assets/brand/logo.svg`：主 Logo 源文件，手写矢量，便于维护。
- `bid_writer/assets/brand/logo_16.png`
- `bid_writer/assets/brand/logo_32.png`
- `bid_writer/assets/brand/logo_64.png`
- `bid_writer/assets/brand/logo_128.png`

PNG 用于 Tk `PhotoImage` 与窗口 `iconphoto`。SVG 作为源文件，不要求 Tk 直接加载。

## 代码接入

在 `bid_writer/ui_icons.py` 中新增品牌资源 helper：

- `BRAND_ASSETS_DIR`
- `brand_asset_path(name: str)`
- `get_brand_image(owner, size: int)`
- `set_window_brand_icon(window)`

复用现有图片缓存机制，避免 Tk 图片被垃圾回收。加载失败时静默降级，不影响应用启动。

在 `bid_writer/gui.py` 中接入：

- `MainWindow.__init__` 创建窗口后调用 `set_window_brand_icon(self)`。
- `create_tool_bar()` 顶部左侧加入品牌块：Logo + “标书智写” + 简短英文副标题。
- 保持当前“大纲结构”、搜索筛选和“整合标书/生成所选”操作按钮布局，只把品牌块作为左侧稳定识别区域。
- 响应式布局中保留品牌块固定宽度，空间不足时不挤压操作按钮，必要时让大纲控件区域继续使用现有自适应逻辑。

## 测试与验证

新增或扩展 `tests/test_ui_icons.py`：

- 验证品牌目录和指定 PNG/SVG 文件存在。
- 验证 Tk 可加载品牌 PNG，并检查 32px 图片尺寸。
- 验证窗口图标 helper 在 fake window 或无 Tk 环境下可降级。

运行验证：

```bash
uv run pytest tests/test_ui_icons.py
```

人工检查：

- `uv run python run.py` 打开主窗口，确认窗口标题区图标和主工具栏品牌块显示正常。
- 在常规窗口宽度和较窄宽度下确认顶部文字、Logo、按钮不重叠。

## 非目标

- 不重做整套 GUI 视觉主题。
- 不替换 Tabler 按钮图标。
- 不新增 Pillow、Cairo、WebView 等运行时依赖。
- 不把 Logo 做成复杂位图或带真实文字的小图标。

## 风险与处理

- Tk 图片加载可能在无显示环境下失败：helper 返回 `None` 或静默跳过，测试允许跳过真实 Tk 场景。
- SVG 不能被 Tk 原生加载：运行时只使用 PNG，SVG 仅作为源文件。
- 顶部空间不足：品牌块保持紧凑，现有响应式布局继续处理搜索和选择控件。
