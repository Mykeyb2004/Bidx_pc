#!/usr/bin/env python3
"""
调试标题提取逻辑
"""

import re
from pathlib import Path

# 模拟 _sanitize_for_comparison
def sanitize_for_comparison(title: str) -> str:
    invalid_chars = r'[\\/: *?"<>|\n\r\t]'
    clean = re.sub(invalid_chars, '_', title)
    clean = clean.strip(' .')
    clean = re.sub(r'[_\s]+', '_', title)
    return clean

# 检查文件名提取
output_dir = Path("output")
generated_titles = set()

print("=" * 70)
print("文件名提取调试")
print("=" * 70)

for md_file in sorted(output_dir.glob("*.md")):
    stem = md_file.stem
    print(f"\n文件名: {stem}")

    # 移除末尾的序号
    stem_no_suffix = re.sub(r'_\d+$', '', stem)
    print(f"移除序号后: {stem_no_suffix}")

    # 提取标题部分
    match = re.match(r'^\d+([.]\d+)*[_\s]+(.+)$', stem_no_suffix)

    if match:
        title_part = match.group(2)
        print(f"正则匹配到的标题: '{title_part}'")

        clean_title = sanitize_for_comparison(title_part)
        print(f"清理后的标题: '{clean_title}'")

        generated_titles.add(clean_title)
    else:
        print("❌ 无法解析")

print(f"\n生成的标题缓存: {generated_titles}")

# 检查大纲四级标题
from bid_writer.main import BidWriter

app = BidWriter()
if app.load_outline():
    fourth_level = app.parser.get_level_headings(4)
    print(f"\n四级标题总数: {len(fourth_level)}")

    print("\n前10个四级标题对比:")
    for i, heading in enumerate(fourth_level[:10], 1):
        clean = sanitize_for_comparison(heading.title)
        is_generated = clean in generated_titles
        status = "✅" if is_generated else "❌"
        print(f"{i:2d}. {status} '{heading.title}' -> '{clean}'")
