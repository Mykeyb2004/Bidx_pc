#!/usr/bin/env python3
"""
测试UI标记功能
"""

from bid_writer.main import BidWriter
from bid_writer.terminal_ui import TerminalUI
from bid_writer.outline_parser import parse_outline

# 创建BidWriter实例
app = BidWriter()

# 加载大纲
if not app.load_outline():
    print("加载大纲失败")
    exit(1)

# 只生成四级标题，所以检查四级标题
fourth_level = app.parser.get_level_headings(4)

print("=" * 70)
print("测试已生成功能（四级标题）")
print("=" * 70)
print(f"Output目录: {app.ui.output_directory}")
print(f"生成标题缓存数量: {len(app.ui._generated_titles)}")
print()

# 显示前10个四级标题的生成状态
print("前10个四级标题生成状态：")
print("-" * 70)
for i, heading in enumerate(fourth_level[:10], 1):
    filename = app.ui._sanitize_for_comparison(heading.title)
    is_generated = filename in app.ui._generated_titles
    status = "✅" if is_generated else "❌"
    print(f"{i:2d}. {status} {heading.title}")

print()
print("=" * 70)
print("完整四级标题列表：")
print("-" * 70)

# 显示所有四级标题
all_generated = []
all_not_generated = []

for heading in fourth_level:
    filename = app.ui._sanitize_for_comparison(heading.title)
    if filename in app.ui._generated_titles:
        all_generated.append(heading.title)
    else:
        all_not_generated.append(heading.title)

print(f"\n已生成的章节 ({len(all_generated)} 个)：")
for title in all_generated:
    print(f"  ✅ {title}")

print(f"\n未生成的章节 ({len(all_not_generated)} 个)：")
for title in all_not_generated[:10]:  # 只显示前10个
    print(f"  ❌ {title}")
if len(all_not_generated) > 10:
    print(f"  ... 还有 {len(all_not_generated) - 10} 个未显示")
