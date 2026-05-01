# 招标文件章节边界增强抽取设计

## 背景

当前招标文件导入已经能把文件转换为 Markdown blocks，并通过关键词、模糊匹配、标题层级和人工确认窗口定位“项目采购需求”“评分标准”。但实际招标文件，尤其是 PDF 转换结果，经常保留“第五章”“第六部分”“附件一”等文本章节标记，却不一定被转换器识别为 Markdown heading。

用户确认的目标是：算法命中“项目采购需求”或“评分标准”的精确行后，默认向外扩展到所在的大章节范围。例如命中“第五章 采购需求”或其章内内容时，人工确认窗口默认选中整个第五章，直到下一大章节前。若找不到大章节，再用小节边界兜底。人工确认窗口仍必须出现。

## 设计原则

- 优先定位大章节，不优先截取小片段。
- 章节标记特征不硬编码在 Python 逻辑中，放到仓库根目录现有 `roles/` 目录下的配置文件中维护。用户口头称 `/role`，项目现有规范目录为 `roles/`，本设计沿用现有目录，避免新增并行目录。
- 解析时只对匹配用的影子文本做空白和不可打印字符归一化；最终摘录、展示、写入仍使用原始 block markdown。
- 不通过粗暴删除“第x章”“第x部分”等前缀来识别标题，避免切掉实体词；使用捕获组保留 `marker_text`、`ordinal`、`title`。
- 新逻辑是现有抽取器的边界增强层，不替代现有候选定位、置信度和人工确认流程。

## 外部配置

新增配置文件：

`roles/tender_section_boundaries.yaml`

配置按优先级分为大章节标记和兜底小节标记：

```yaml
normalization:
  strip_invisible: true
  collapse_space: true

major_markers:
  - name: chapter
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)"
    priority: 100
  - name: part
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*部分\\s*(?P<title>.*)"
    priority: 100
  - name: volume_or_book
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*[篇卷册]\\s*(?P<title>.*)"
    priority: 95
  - name: section
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*节\\s*(?P<title>.*)"
    priority: 85
  - name: appendix
    pattern: "附件\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９A-Za-zＡ-Ｚａ-ｚ]+)?\\s*[:：、.．]?\\s*(?P<title>.*)"
    priority: 85
  - name: appendix_table
    pattern: "附表\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９A-Za-zＡ-Ｚａ-ｚ]+)?\\s*[:：、.．]?\\s*(?P<title>.*)"
    priority: 85
  - name: package
    pattern: "(?:第\\s*)?(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*(?:包|标包|采购包)\\s*(?P<title>.*)"
    priority: 80

fallback_markers:
  - name: chinese_top
    pattern: "(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)"
    priority: 60
  - name: parenthesized
    pattern: "[（(]\\s*(?P<ordinal>[一二三四五六七八九十百千万0-9０-９]+)\\s*[）)]\\s*(?P<title>.+)"
    priority: 50
  - name: numeric
    pattern: "(?P<ordinal>[0-9０-９]+(?:\\s*[.．]\\s*[0-9０-９]+)*)\\s*[.．、]?\\s*(?P<title>.+)"
    priority: 45
```

配置中的 `pattern` 是数据，不是代码常量。后续维护更多招标文件章节格式时，只改配置和测试夹具。

## 组件

### `tender_section_boundary_config`

负责从 `roles/tender_section_boundaries.yaml` 加载规则。

- 默认路径为项目根目录下 `roles/tender_section_boundaries.yaml`。
- 如果文件不存在，返回空规则并在转换报告中记录 warning，然后回退现有算法；不在包内隐藏一份包含章节特征词的默认规则。
- 校验每条规则必须有 `name`、`pattern`、`priority`。
- 正则编译失败时跳过该规则并写入 warning，不让一次配置错误导致整个导入崩溃。

### `tender_section_boundary_detector`

负责把每个 block 识别为章节边界候选。

输出结构建议包含：

- `block_id`
- `marker_kind`：`major` 或 `fallback`
- `rule_name`
- `priority`
- `marker_text`
- `ordinal`
- `title`
- `normalized_text`

检测逻辑：

- 使用 block 的第一行文本作为主要检测对象。
- 同时兼容 `heading_title`、`text` 和 Markdown 第一行。
- 匹配前生成归一化副本：移除 BOM、零宽字符和控制字符；全角空格转普通空格；连续空白折叠。
- 匹配成功后，原始 block 不被修改。

### `tender_section_extractor` 增强

现有 `_build_result()` 流程保持不变，但在确定 candidate index 后增加边界扩展：

1. 找到候选命中块。
2. 向前查找最近的 `major` 边界。
3. 如果找到，从该大章节边界作为 start。
4. 向后查找下一个 `major` 边界作为 end。
5. 如果找不到大章节边界，使用 `fallback` 小节边界执行同样逻辑。
6. 如果两者都找不到，回退现有 heading/强停止词逻辑。

对于“第五章 采购需求”内命中的任意块，默认选中范围为第五章整章。

## 数据流

1. `TenderImportService.import_document()` 调用转换器生成 blocks。
2. 抽取器加载章节边界配置。
3. 抽取器先收集现有“项目采购需求”“评分标准”候选。
4. 对每个候选调用章节边界扩展器得到更完整的 start/end block。
5. `TenderExtractionResult` 仍保存最终 markdown、start/end block id、置信度和 warning。
6. 人工确认窗口默认展示增强后的完整章节选区。
7. 用户确认后，只写入人工确认后的内容。

## 边界和冲突处理

- 如果“项目采购需求”和“评分标准”都落在同一大章节内，不能盲目把两者都扩到整章；应降级到 fallback 小节边界或现有逻辑，并写入 warning，避免两个输出文件高度重复。
- 如果大章节标题是目录页内容，沿用现有目录过滤逻辑，不把目录行作为真实章节。
- 如果下一大章节在转换结果中缺失，则截到文件末尾，但降低置信度并提示人工确认。
- 如果配置中多个规则同时命中，选择 priority 更高的规则；priority 相同则选择文本跨度更长、title 非空的规则。
- 如果标题中含不可打印字符，匹配副本可清理，但保存摘录必须保留原始可见文本。

## 测试计划

- `第 五 章 项目采购需求` 命中时默认选中整个第五章，截到第六章前。
- `第五部分 评分标准`、`第六篇 评标办法`、`附件一：评分细则`、`附表1：技术商务评分表` 能作为大章节边界。
- PDF 转换为普通 paragraph 而不是 heading 时，也能识别大章节边界。
- 只有 `一、采购需求` 时，用 fallback 小节边界兜底。
- `项目采购需求` 和 `评分标准` 位于同一大章节时，不把两个部分都扩成同一整章。
- `第\u200b五　章　项目采购需求` 这类不可见字符和全角空格不影响匹配。
- 最终 markdown 不丢失 `第五章`、`采购需求`、`评分标准` 等实体词。
- 配置规则无效时记录 warning 并回退现有算法。

## 非目标

- 不引入 OCR。
- 不取消人工确认窗口。
- 不让 LLM 判断章节边界。
- 不把章节边界配置放入主 YAML 配置项，避免新建配置流程变复杂。
