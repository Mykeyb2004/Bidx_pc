# 招标文件导入与章节自动抽取开发方案

> 状态：已按用户确认意见修订，待进入实施计划  
> 日期：2026-04-30  
> 目标功能：在“新建配置...”流程中，支持导入单个 Word、PDF、Excel 招标文件，先转换为 Markdown，再自动抽取“项目采购需求”和“评分标准”两部分，写入配置引用的独立 Markdown 文件。

## 1. 背景与目标

当前新建配置已经支持填写：

- `project.inputs.bid_requirements_file`
- `project.inputs.scoring_criteria_file`

但用户仍需要手动从招标文件中摘录“项目采购需求”和“评分标准”。本功能要在新建配置阶段增加“从招标文件导入...”能力，让系统自动完成：

1. 选择一个招标文件。
2. 将源文件统一转换为可预览的 Markdown。
3. 在 Markdown 中定位“项目采购需求”和“评分标准”章节。
4. 原文摘录章节全部内容。
5. 写入 `项目要求/项目采购需求.md` 与 `项目要求/评分标准.md`。
6. 自动把这两个路径填入新建配置表单。

本方案强调“原文摘录”。LLM 不参与正文生成；如后续加入 LLM，也只能用于候选边界复核，最终内容必须由程序从转换后的 Markdown 原文回填。

## 2. v1 范围

### 包含

- 在 `ConfigEditorDialog` 新建配置模式下增加“从招标文件导入...”入口。
- 支持用户选择一个本地文件。
- 支持文本型 PDF、`.docx`、`.xlsx`、`.xls`、`.doc` 的导入路径。
- 不支持 WPS 原生格式，例如 `.wps`、`.et`。
- 暂不考虑 OCR；PDF 没有文本层时直接提示“不支持，请先转为可复制文字的 PDF 或 Word”。
- 将源文件转换为 Markdown，并保存转换产物。
- 保存转换来源映射 JSON，记录每个 Markdown block 的来源文件、页码、sheet、行列范围等。
- 自动抽取采购需求和评分标准两个章节。
- 自动写入项目资料文件并更新配置表单路径。
- 抽取低置信度时给出清晰错误或确认提示。
- 增加单元测试、集成测试和用户文档。

### 不包含

- OCR、扫描件识别、图片文字识别。
- 压缩包批量解压。
- OFD、图片、PPT/PPTX 等格式。
- 在线文档下载或网页抓取。
- 对抽取内容做摘要、改写或结构化重排。
- 自动生成投标大纲。

## 3. 推荐技术选型

### PDF

首选 `PyMuPDF` / `PyMuPDF4LLM`。

- 用于读取文本型 PDF。
- 转换为 Markdown。
- 保留页码、block 顺序、表格文本。
- 检查文本层是否存在；如果全文可抽取字符数过低，判定为扫描件或图片型 PDF。

### Word

首选 `python-docx` 自研轻量转换器。

- 读取段落、标题样式、表格。
- 将 Word heading 样式转换为 Markdown `#` / `##` / `###`。
- 表格转换为 Markdown 表格。
- 保留段落序号和表格序号，用于来源映射。

`.doc` 由 LibreOffice headless 预转换为 `.docx` 后再解析。若本机没有 LibreOffice 或转换失败，则提示用户另存为 `.docx` 或可复制文字 PDF。

### Excel

首选 `openpyxl`，可选补充 `python-calamine`。

- `.xlsx` 使用 `openpyxl`。
- `.xls` 可通过 LibreOffice 转 `.xlsx`，或使用 `python-calamine` 读取。
- 每个 sheet 转为一个 Markdown 章节：`## 工作表：<sheet name>`。
- 连续非空区域转为 Markdown 表格。
- 合并单元格按左上角值展开到表格输出，避免标题缺失。

不支持 WPS 表格原生 `.et` 格式。用户需要先另存为 `.xlsx` 或 `.xls`。

### 统一转换器备选

`Docling` 和 `Microsoft MarkItDown` 可以作为后续增强，但 v1 不建议作为唯一主路径。

- MarkItDown 轻量，适合 LLM 输入，但来源映射能力较弱。
- Docling 能统一 PDF/DOCX/XLSX 到 Markdown/JSON，但依赖较重，v1 可暂不引入。
- v1 优先选择“分格式精确转换 + 自有来源映射”，保证可控性和可测试性。

### 建议依赖

```bash
uv add pymupdf pymupdf4llm python-docx openpyxl pandas tabulate rapidfuzz markdown-it-py
```

可选依赖：

```bash
uv add python-calamine
```

系统可选依赖：

- LibreOffice，用于 `.doc` / `.xls` 预转换。

## 4. 产物目录

导入后在项目根目录下创建：

```text
项目要求/
  项目采购需求.md
  评分标准.md

.bid_writer/imports/<import_id>/
  sources/
    原始文件副本或引用信息
  converted.md
  conversion_map.json
  extraction_report.json
```

说明：

- `项目要求/*.md` 是正式进入配置的文件。
- `.bid_writer/imports/<import_id>/converted.md` 是完整转换后的 Markdown，便于用户检查。
- `conversion_map.json` 保存来源映射。
- `extraction_report.json` 保存候选标题、分数、起止 block、置信度、失败原因等。

## 5. 中间数据模型

新增 `bid_writer/tender_import_models.py`。

核心模型：

```python
@dataclass(frozen=True)
class ConvertedBlock:
    block_id: str
    source_file: str
    source_type: str
    block_type: str
    markdown: str
    text: str
    order_index: int
    heading_level: int | None = None
    heading_title: str = ""
    page_number: int | None = None
    sheet_name: str = ""
    cell_range: str = ""
    paragraph_index: int | None = None
    table_index: int | None = None


@dataclass(frozen=True)
class TenderExtractionResult:
    section_key: str
    title: str
    markdown: str
    start_block_id: str
    end_block_id: str
    confidence: float
    warnings: tuple[str, ...] = ()
```

`ConvertedBlock.markdown` 保存转换后的 Markdown 原文片段；最终摘录只拼接这些 block，不重新生成正文。

## 6. 转换流程

新增 `bid_writer/tender_markdown_converter.py`。

入口：

```python
convert_tender_document(path: Path, output_dir: Path) -> TenderConversionResult
```

流程：

1. 读取用户选择的单个文件。
2. 按扩展名选择转换器：
   - `.pdf`：PDF converter。
   - `.docx`：Word converter。
   - `.xlsx`：Excel converter。
   - `.doc`：LibreOffice 转 `.docx` 后再走 Word converter。
   - `.xls`：优先使用 `python-calamine` 读取；不可用时尝试 LibreOffice 转 `.xlsx` 后再走 Excel converter。
   - `.wps` / `.et`：不支持，提示用户另存为 `.docx` / `.xlsx`。
3. 输出 `ConvertedBlock`。
4. 将 block 按源文档顺序合并。
5. 写出 `converted.md`。
6. 写出 `conversion_map.json`。

PDF 特殊规则：

- 先统计可抽取文本字符数。
- 如果平均每页可抽取中文/英文/数字字符过低，判定为无文本层。
- 无文本层直接失败，不走 OCR。

Excel 特殊规则：

- 每个 sheet 先输出标题：`## 工作表：<sheet name>`。
- 识别连续非空区域。
- 对很稀疏的 sheet，按 used range 输出一个表格。
- 对疑似评分表的 sheet，即使没有标准标题，也参与评分标准候选。

## 7. 章节抽取流程

新增 `bid_writer/tender_section_extractor.py`。

入口：

```python
extract_tender_sections(conversion: TenderConversionResult) -> TenderSectionExtraction
```

抽取对象固定为两个：

- `bid_requirements`：项目采购需求。
- `scoring_criteria`：评分标准。

### 7.1 标题别名词典

采购需求别名：

- 项目采购需求
- 采购需求
- 项目需求
- 服务需求
- 技术需求
- 技术和服务要求
- 采购内容及要求
- 项目内容及要求
- 服务内容及要求
- 技术参数及要求
- 用户需求书
- 商务技术要求

评分标准别名：

- 评分标准
- 评审标准
- 评审办法
- 评审方法
- 评分办法
- 评分细则
- 综合评分法
- 详细评审
- 评审因素
- 技术商务评分表
- 综合评分表
- 评标办法

### 7.2 候选起点识别

候选来自：

- Markdown heading。
- Word 标题样式转换出的 heading。
- PDF 中疑似标题的独立短行。
- Excel sheet 名、合并单元格标题、表格首行。

评分方法：

- 标题与别名词典精确匹配：高分。
- 使用 `RapidFuzz` 模糊匹配：中高分。
- 命中关键词但标题较长：中分。
- 表格含 `评审因素`、`评分项`、`评分标准`、`分值`、`权重`、`得分` 等列：提高评分标准候选分。
- 位于目录页或目录区：扣分或排除。

### 7.3 终点识别

常规章节：

- 起点为 H2，则终点为下一个 H2 或 H1 前。
- 起点为 H3，则终点为下一个 H3/H2/H1 前。
- 起点为 H4，则终点为下一个 H4/H3/H2/H1 前。

无显式层级时：

- 根据标题候选的相邻同级标题推断终点。
- 若后续出现“合同条款”“投标人须知”“响应文件格式”“开标评标定标”等明显非目标章节，作为强终止信号。

评分标准特殊规则：

- 如果只命中“评审办法”父章节，但内部存在评分表，则优先截取包含评分表的子区间。
- 如果 Excel sheet 名或表格标题命中评分标准，抽取整张 sheet 的相关表格区域。
- 如果评分表跨多个连续 block，按 block 顺序合并到同一摘录。

### 7.4 目录区排除

排除特征：

- 标题为“目录”后的连续短行。
- 行尾大量页码。
- 含点线连接符，例如 `采购需求 ........ 23`。
- 同一区域密集出现多个目标章节名但正文很短。

目录区只用于辅助定位页码，不作为正文起点。

### 7.5 置信度

每个抽取结果给出 `confidence`。

建议阈值：

- `>= 0.80`：自动应用。
- `0.55 - 0.79`：展示确认提示，用户确认后应用。
- `< 0.55`：不自动写入，展示失败原因和候选列表。

采购需求校验：

- 摘录长度不能过短。
- 应包含 `服务`、`技术`、`要求`、`内容`、`范围`、`参数`、`成果`、`验收` 等需求词中的若干项。

评分标准校验：

- 应包含 `评分`、`评审`、`分值`、`满分`、`权重`、`得分` 等词。
- 或至少包含一张疑似评分表。

## 8. 配置编辑器交互设计

修改 `bid_writer/config_editor_dialog.py`。

在新建配置模式的“输入资源”区域增加：

- 按钮：`从招标文件导入...`
- 状态文本：显示最近一次导入结果。

点击按钮后：

1. 弹出文件选择框，只允许选择一个文件。
2. 运行转换与抽取。
3. 如果两个章节均高置信度命中：
   - 写入 `项目要求/项目采购需求.md`。
   - 写入 `项目要求/评分标准.md`。
   - 将 `project.bid_requirements_mode` 设置为 `file`。
   - 将 `project.scoring_criteria_mode` 设置为 `file`。
   - 将对应路径设置为 `./项目要求/项目采购需求.md` 与 `./项目要求/评分标准.md`。
   - 刷新 YAML 预览和校验状态。
4. 如果低置信度：
   - 显示候选标题、页码/sheet、置信度、摘录预览。
   - 用户确认后再写入。
5. 如果失败：
   - 不修改配置表单。
   - 提示失败原因。
   - 保留 `converted.md` 和 `extraction_report.json` 供排查。

建议新增一个轻量对话框：

`bid_writer/tender_import_dialog.py`

用途：

- 展示导入进度。
- 展示抽取结果摘要。
- 展示低置信度确认。
- 提供“打开转换 Markdown”和“查看报告”的入口。

如果先做最小版本，也可以不新增完整对话框，只用 `filedialog` + `messagebox` + 结果摘要文本。

## 9. 文件写入策略

正式摘录文件：

- 默认写入项目根目录下的 `项目要求/项目采购需求.md`。
- 默认写入项目根目录下的 `项目要求/评分标准.md`。

覆盖策略：

- 如果目标文件不存在，直接创建。
- 如果目标文件存在且内容为空，直接覆盖。
- 如果目标文件存在且有内容，弹窗确认：
  - 覆盖并备份为 `.bak`。
  - 取消导入。

写入内容格式：

```markdown
# 项目采购需求

<从招标文件摘录的原文 Markdown>
```

```markdown
# 评分标准

<从招标文件摘录的原文 Markdown>
```

正式文件不写入调试用 block id 注释，避免影响后续 prompt。来源追踪放在 `.bid_writer/imports/<import_id>/extraction_report.json`。

## 10. 建议新增与修改文件

新增：

- `bid_writer/tender_import_models.py`
- `bid_writer/tender_markdown_converter.py`
- `bid_writer/tender_section_extractor.py`
- `bid_writer/tender_import_service.py`
- `bid_writer/tender_import_dialog.py`（可选，若做确认 UI）
- `tests/test_tender_markdown_converter.py`
- `tests/test_tender_section_extractor.py`
- `tests/test_tender_import_service.py`
- `tests/test_config_editor_tender_import.py`

修改：

- `bid_writer/config_editor_dialog.py`
- `bid_writer/config_editor_tooltips.py`
- `pyproject.toml`
- `uv.lock`
- `README.md`
- `docs/config_schema.md`（仅补充“新建配置导入体验”，不改变 schema）

不建议修改：

- `bid_writer/source_unit_parser.py`
- `bid_writer/hybrid_retriever.py`

原因：这两个模块已经负责“采购需求/评分标准文件进入后”的解析与检索。新功能应在更上游完成“招标文件导入与原文抽取”。

## 11. 实施阶段

### 阶段 1：数据模型与章节抽取核心

目标：

- 建立 `ConvertedBlock` 等模型。
- 用手写 Markdown fixture 验证章节定位算法。

验收：

- 能从包含目录、采购需求、评分表的 Markdown 中抽取两个章节。
- 能排除目录区。
- 能识别“评审办法”下的评分表。
- 单元测试覆盖别名、终止边界、低置信度场景。

### 阶段 2：Word 与 Excel 转 Markdown

目标：

- `.docx` 转 Markdown。
- `.xlsx` 转 Markdown。
- 输出 `converted.md` 与 `conversion_map.json`。

验收：

- Word 标题和表格保留。
- Excel sheet 和表格区域保留。
- 抽取器能基于转换结果抽取目标章节。

### 阶段 3：PDF 转 Markdown

目标：

- 文本型 PDF 转 Markdown。
- 检测无文本层 PDF 并给出明确错误。

验收：

- 可复制文字 PDF 能抽取。
- 扫描件或图片型 PDF 不进入 OCR，返回“不支持无文本层 PDF”。

### 阶段 4：旧 Office 格式预转换与不支持格式提示

目标：

- `.doc` 尝试用 LibreOffice 转 `.docx`。
- `.xls` 优先尝试用 `python-calamine` 读取；不可用时尝试用 LibreOffice 转 `.xlsx`。
- `.wps` / `.et` 明确提示不支持，请另存为 `.docx` / `.xlsx`。
- LibreOffice 不可用时，对需要 LibreOffice 的格式给用户明确提示。

验收：

- 有 LibreOffice 环境时，`.doc` 能完成预转换。
- `.xls` 在 `python-calamine` 或 LibreOffice 可用时能读取。
- `.wps` / `.et` 不进入转换流程，直接给出不支持提示。
- 无 LibreOffice 环境时失败信息可理解，不影响新建配置窗口状态。

### 阶段 5：新建配置 UI 集成

目标：

- 在新建配置输入资源区域增加导入入口。
- 导入成功后写入文件并填充表单。
- 支持覆盖确认和低置信度确认。

验收：

- 新建配置时可以从招标文件导入。
- 导入后配置表单自动变为文件模式。
- YAML 预览使用生成的两个文件路径。
- 保存配置后，现有生成链路可读取这两个文件。

### 阶段 6：文档与回归测试

目标：

- 更新 README。
- 更新相关配置文档说明。
- 增加完整测试。

验收：

```bash
uv run pytest tests/test_tender_section_extractor.py tests/test_tender_markdown_converter.py tests/test_tender_import_service.py tests/test_config_editor_tender_import.py -q
uv run pytest -q
```

## 12. 测试策略

### 单元测试

- 标题别名匹配。
- 目录区排除。
- 同级标题终止。
- 评分表特殊识别。
- Excel sheet 名命中。
- 低置信度不自动应用。
- 无文本层 PDF 错误。

### 集成测试

- 创建临时项目根目录。
- 模拟导入文件。
- 生成 `项目要求/项目采购需求.md` 与 `项目要求/评分标准.md`。
- 检查配置编辑器变量被更新。
- 检查 YAML 预览中路径正确。

### 回归测试

- 现有新建配置流程不导入文件时仍可保存。
- 现有编辑当前配置流程不受影响。
- `SourceUnitParser` 继续能解析生成后的 Markdown。

## 13. 风险与应对

### 风险 1：用户上传 WPS 原生格式

应对：

- v1 明确不支持 `.wps` / `.et`。
- 上传时立即提示用户另存为 `.docx` / `.xlsx` / 可复制文字 PDF。

### 风险 2：PDF 转换后的标题层级不可靠

应对：

- 结合短行、编号、关键词、相邻标题、目录排除综合评分。
- 保留 extraction report 便于调整规则。

### 风险 3：评分标准经常藏在“评审办法”中

应对：

- 不只匹配标题，还要识别评分表列名和分值词。
- 对“评审办法”父章节下的评分表做子区间抽取。

### 风险 4：自动覆盖用户已有资料

应对：

- 已有非空目标文件必须确认。
- 覆盖时生成 `.bak`。

### 风险 5：转换 Markdown 与正式摘录文件混用

应对：

- `converted.md` 只作为导入中间产物。
- 正式进入配置的只有 `项目要求/项目采购需求.md` 和 `项目要求/评分标准.md`。
- 正式文件不写调试注释。

## 14. 已确认决策

1. v1 不允许一次选择多个招标文件；每次只导入一个文件。
2. v1 取消 WPS 原生格式解析，不支持 `.wps` / `.et`。
3. 目标文件已存在且非空时，采用“确认后覆盖并备份 `.bak`”。
4. 低置信度结果 v1 就需要提供预览确认对话框，用户确认后才写入。
5. v1 入口仅放在“新建配置...”流程中，不扩展到“编辑当前配置”。

## 15. 验收标准

- 用户在“新建配置...”中能点击“从招标文件导入...”。
- 文件选择框每次只允许选择一个招标文件。
- 支持导入文本型 PDF、DOCX、XLSX。
- `.doc` 在 LibreOffice 可用时能预转换，不可用时给出明确提示。
- `.xls` 在 `python-calamine` 或 LibreOffice 可用时能读取，不可用时给出明确提示。
- `.wps` / `.et` 明确不支持，并提示另存为 `.docx` / `.xlsx`。
- 成功导入后自动生成：
  - `项目要求/项目采购需求.md`
  - `项目要求/评分标准.md`
  - `.bid_writer/imports/<import_id>/converted.md`
  - `.bid_writer/imports/<import_id>/conversion_map.json`
  - `.bid_writer/imports/<import_id>/extraction_report.json`
- 配置表单自动填入采购需求和评分标准文件路径。
- 保存新配置后，现有生成链路能读取这两个文件。
- 无文本层 PDF 不做 OCR，并有明确错误提示。
- 相关测试通过。
