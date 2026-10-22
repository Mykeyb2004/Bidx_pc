# Nuitka 构建与验证

入口为仓库根目录的 `run.py`。构建工具在 `pyproject.toml` 的 `build` 依赖组中，由 `uv.lock` 锁定；当前最低 Nuitka 版本为 4.2.1。不需要更换 GUI 框架。

## 构建环境

- Python >= 3.10，且包含可用的 `tkinter` 和 Tcl/Tk。
- 使用 uv；`uv run --group build` 会同步构建依赖。
- macOS 安装 Xcode Command Line Tools（`xcode-select --install`）；在目标 Intel/Apple Silicon 架构上分别构建。
- Windows 安装 Visual Studio 2022 Build Tools 的 C++ 桌面开发组件和 Windows SDK，使用与目标架构一致的 Python。
- Linux 需要 C 编译器及 Python/Tk 开发环境；应在不高于目标系统 glibc 版本的环境构建。
- 编译机需要联网下载依赖及 Nuitka 所需工具。用户运行成品不需要 Python、uv 或编译器。AI 生成仍需要模型服务，`.doc` 预转换仍需要 LibreOffice。

## 命令

从仓库根目录运行：

```bash
uv run --group build python scripts/build_nuitka.py
uv run --group build python scripts/build_nuitka.py --clean --smoke-test
uv run --group build python scripts/build_nuitka.py --no-cache --smoke-test
uv run --group build python scripts/build_nuitka.py --dry-run --no-cache
```

脚本通过自身位置定位仓库，不依赖当前工作目录。`--mode auto`（默认）在 macOS 选择 `app`，Windows/Linux 选择 `standalone`。可显式传入 `--mode standalone`。不提供跨操作系统编译或 onefile 模式。

`--jobs N` 设置并行编译数，默认不超过 8；内存不足时可降低到 2。

## 清理范围

- `--clean`：删除当前平台、架构、模式的旧构建与发布目录，以及 `bid_writer/`、`scripts/`、`tests/` 下的 `__pycache__` 和根目录 `.pytest_cache`。
- `--no-cache`：隐含 `--clean`，并向 Nuitka 传入 `--clean-cache=all --disable-cache=all`。
- 脚本将 `NUITKA_CACHE_DIR` 设置为仓库内 `build/nuitka-cache/`，避免清理其他项目的编译缓存。
- 不清理业务 `caches/`、项目文件、模型配置、`output/` 或 `log/`。禁用编译缓存只影响构建，不直接提高成品启动速度。
- `--dry-run` 仅打印命令与范围，不创建目录、不清理、不编译。

## 产物与资源

中间文件：`build/nuitka/<系统>-<架构>-<模式>/`。

发布文件：`dist/nuitka/<系统>-<架构>-<模式>/bid-writer.app` 或 `bid-writer.dist/`。只分发发布文件中的完整应用包/目录，不能单独取出 Windows EXE。macOS 本地构建采用 Nuitka 默认签名方式；面向外部用户正式发布时另行配置开发者签名与公证。

脚本收集 Tcl/Tk（`tk-inter` 插件）、ttkbootstrap、DOCX 模板及实际导入的原生库。资源采用白名单：应用图标、通用角色、标书架构师、门禁、章节边界 YAML、配置/环境模板和软件说明书。不会把真实 `.env.local`、`config_*.yaml`、历史输出、采购材料或整个仓库复制进成品。新项目由现有新建配置向导初始化。

## 路径约定

| 内容 | 源码运行 | macOS 成品 | Windows 成品 |
| --- | --- | --- | --- |
| 图标、内置角色、模板 | 仓库资源 | `.app` 内部资源 | 独立目录内资源 |
| 共享 `.env.local` | 仓库根目录 | `~/.bid-writer/config/` | EXE 同目录 |
| 默认 GUI 状态/配置查找 | 当前工作目录 | 配置查找 `~/.bid-writer/config/`，状态 `~/.bid-writer/state/` | EXE 同目录 |
| 默认时序日志 | 仓库 `log/` | `~/.bid-writer/logs/` | EXE 同级 `log/` |
| 跨项目缓存 | 执行入口同级 | `~/.bid-writer/cache/` | EXE 同级 |
| 项目输入/输出 | 按项目配置 | 按项目配置 | 按项目配置 |

Linux 成品的共享配置和状态使用 `${XDG_DATA_HOME:-~/.local/share}/bid-writer/`。项目配置中的角色文件仍优先从配置同目录查找，缺失时回退内置资源。源码运行行为保持兼容。

## 验证

```bash
uv run --group build pytest tests/test_nuitka_packaging.py tests/test_gui_state.py tests/test_config_schema.py tests/test_config_editor.py tests/test_env_local_prompt.py -q
```

`--smoke-test` 在编译成功后，从临时工作目录运行成品的 `--smoke-test <报告路径>`，清除 `PYTHONHOME`、`PYTHONPATH`、`TCL_LIBRARY`、`TK_LIBRARY`，验证资源、真实 DOCX/XLSX/PDF 转换、Calamine、pandas/tabulate、Tk 主题和图片。无需 API Key，不调用模型，不读写真实项目。需要可访问桌面的图形会话，不能在禁止 macOS WindowServer 访问的沙箱中运行。

编译报告为 `log/nuitka-<模式>-report.xml`，成品自检报告为 `log/nuitka-<目标>-smoke.json`；脚本/编译/验证失败均返回非零状态。正式分发还应在未安装开发环境的目标机器验证首次启动、新建项目与文件导入。启动速度应在同一机器上测量“启动到窗口可交互”，自检总时长包含文档转换，不代表启动时间。
