# 章节扩写正文从“（一）”起始的诊断

日期：2026-09-16。范围：检查提示词、回放真实输出与本地校验；未修改业务代码、门禁或项目材料，未发起大模型请求。

## 结论

“从一、开始编号”已经进入真实请求的 system 消息，但模型输出仍可违反它。当前规则存在“禁止一级标题的形式”的歧义；输出检查只统计是否存在任意正式序号，不校验起始层级，后处理也不重排编号。因此违规输出可以被保留并标记完成。

能确定的是规则送达、实际违规和本地检查漏检。不能仅凭一次输出证明模型一定因某一句提示词而违反规则，未进行模型对照实验。

## 实际记录

武穴项目 trace：`eea203e2e70e`，创建时间 2026-09-16 17:42:59，章节为“3.3.1 困难群众家庭状况及需求变化监测”，状态 completed，输出 7200 字符。

目录：`/Users/zhangqijin/Documents/Field/项目数据库/2026/投标项目/武穴市社会救助联合体项目/log/generation_traces/20260916_174259__3.3.1_困难群众家庭状况及需求变化监测__eea203e2e70e/`。

- `03_prompt_system.md` 第 18 行：“严禁使用Markdown标题符号（#），禁止一级标题的形式。”
- 同文件第 20 行：明确要求“从‘一、’开始编号”。因此这次不是漏加载门禁，也不是历史版本缺少这条要求。
- `04_prompt_user.md` 第 25 行：包含完整章节路径；第 28 行：要求“不重复标题”。没有明确说明外部大纲层级不占用正文内部编号。
- `06_generation_output.md` 的实际输出以 `### 3.3.1 困难群众家庭状况及需求变化监测` 开头，随后第一个正式编号是“（一）监测目标与基本原则”，后续使用 `1.` 和 `（1）`。
- `manifest.json` 的 `postprocess.format_repair_issues` 为 `[]`，`format_repair_applied` 为 false。

注意：trace 文件的“## 正文输出”是日志包装；其后 `### 3.3.1 ...` 属于记录的输出内容。`GenerationTraceSession._build_output_document()` 不会自动添加这一行章节标题。

## 提示词中的问题

`roles/system_gate_rules.md:2` 的“禁止一级标题的形式”未明确限定为 Markdown H1，可能被理解为禁止“一、”这类一级标题；同文件第 4 行又要求从“一、”开始。两句位于同一个 system 硬约束区，单纯提升 role 不能消除歧义。

完整章节路径和“不重复标题”也可能促使模型把外部标题当成已存在的上级，再从“（一）”展开。这是与输出表现一致的解释，并非已经证明的模型内部原因。

## 确定的检查缺口

- `bid_writer/ai_writer.py:81`：`_FORMAL_HEADING_LINE_RE` 同时匹配“一、”“（一）”“1.”和“（1）”，不区分起始层级，也不验证父子关系。
- `bid_writer/ai_writer.py:483`：`_collect_output_issues()` 仅在正文需要层级且正式序号数量为零时记录 `missing_formal_hierarchy`；只要出现“（一）”就能通过这一项。
- `bid_writer/ai_writer.py:494`：`_finalize_generated_content()` 仅规范化投标主体称谓并记录问题；不执行编号修复，`format_repair_applied` 固定为 false。

最小回放命令（从项目根目录运行；断言失败为本次问题的复现结果）：

```bash
UV_CACHE_DIR=/private/tmp/bidx-uv-cache uv run --no-sync python - <<'PY'
from bid_writer.ai_writer import AIWriter
writer = AIWriter.__new__(AIWriter)
body = '（一）服务组织与实施\n\n' + '\n\n'.join(
    ['建立服务台账，明确岗位职责、办理流程和质量验收标准。' * 30 for _ in range(4)]
)
issues = writer._collect_output_issues(body)
print(len(body), writer._requires_formal_hierarchy(body), writer._formal_heading_count(body), issues)
assert issues, '从（一）开始且没有一级标题的正文未被识别'
PY
```

实测：`3138 True 1 []`，断言失败。只把首行换成“一、”“1.”或“（1）”，同样返回 `[]`；去掉所有编号后返回 `['missing_formal_hierarchy']`。

对上述真实 trace 的“## 正文输出”之后完整 7200 字符进行原样回放：首行是 Markdown 章节标题，首个正式序号为“（一）”，正式序号计数 118，问题列表仍为 `[]`。

## 建议（尚未实施）

1. 删除“禁止一级标题的形式”的歧义，只明确禁止 Markdown 标题标记，同时说明“一、”等正式序号标题允许且必需。
2. 在 system 门禁中明确：输入大纲标题和路径只用于确定写作范围，不占用正文内部编号；每次独立扩写的第一个正文标题必须从“一、”开始，不得从“（一）”“1.”或“（1）”起始。
3. 增加首个正文标题及编号父子关系的校验，并设计明确的失败处理；提示词优先级本身不能替代程序校验。
4. 修改时同步测试门禁夹具、提示词契约文档及相关测试。不要仅把首个“（一）”替换成“一、”，这会留下后续“（二）”及子级关系不一致的问题。
