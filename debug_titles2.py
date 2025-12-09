#!/usr/bin/env python3
"""
调试标题提取逻辑 - 修复版本
"""

import re
from pathlib import Path

# 模拟 _sanitize_for_comparison（修复后的版本）
def sanitize_for_comparison(title: str) -> str:
    invalid_chars = r'[\\/: *?"<>|\n\r\t]'
    clean = re.sub(invalid_chars, '_', title)
    clean = clean.strip(' .')
    clean = re.sub(r'[_\s]+', '_', clean)
    return clean

# 从四级标题中提取纯文本（移除编号）
def extract_title_from_heading(heading_title: str) -> str:
    match = re.match(r'^\d+([.]\d+)*[_\s]+(.+)$', heading_title)
    if match:
        return match.group(2)
    return heading_title

# 检查文件名提取
output_dir = Path("output")
generated_titles = set()

print("=" * 70)
print("文件名提取调试")
print("=" * 70)

for md_file in sorted(output_dir.glob("*.md")):
    stem = md_file.stem
    # 移除末尾的序号
    stem_no_suffix = re.sub(r'_\d+$', '', stem)
    # 提取标题部分
    match = re.match(r'^\d+([.]\d+)*[_\s]+(.+)$', stem_no_suffix)
    if match:
        title_part = match.group(2)
        clean_title = sanitize_for_comparison(title_part)
        generated_titles.add(clean_title)

print(f"生成的标题缓存: {len(generated_titles)} 个")
print(f"列表: {list(generated_titles)[:5]}")  # 只显示前5个

# 检查大纲四级标题
from bid_writer.main import BidWriter

app = BidWriter()
if app.load_outline():
    fourth_level = app.parser.get_level_headings(4)
    print(f"\n四级标题总数: {len(fourth_level)}")

    print("\n前10个四级标题对比:")
    for i, heading in enumerate(fourth_level[:10], 1):
        # 从四级标题中提取纯标题文本
        title_text = extract_title_from_heading(heading.title)
        clean = sanitize_for_comparison(title_text)
        is_generated = clean in generated_titles
        status = "✅" if is_generated else "❌"
        print(f"{i:2d}. {status} '{heading.title}'")
        print(f"    提取文本: '{title_text}' -> '{clean}'")
        if is_generated:
            print(f"    ✓ 匹配成功")
        print()
