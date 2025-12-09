"""
大纲解析模块
解析Markdown格式的标书大纲，支持1-3级标题
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class HeadingNode:
    """标题节点"""
    level: int  # 标题级别: 1, 2, 3
    title: str  # 标题文本
    full_path: str  # 完整路径，如 "1. 项目概述 > 1.1 项目背景 > 1.1.1 政策背景"
    line_number: int  # 在原文件中的行号
    parent: Optional['HeadingNode'] = None
    children: List['HeadingNode'] = field(default_factory=list)
    
    def __str__(self) -> str:
        return f"{'#' * self.level} {self.title}"
    
    def __repr__(self) -> str:
        return f"HeadingNode(level={self.level}, title='{self.title}')"


class OutlineParser:
    """大纲解析器"""
    
    # 匹配Markdown标题的正则表达式（支持1-6级标题）
    HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$')
    
    def __init__(self):
        self.headings: List[HeadingNode] = []
        self.root_headings: List[HeadingNode] = []  # 1级标题列表
    
    def parse(self, content: str) -> List[HeadingNode]:
        """
        解析Markdown大纲内容
        
        Args:
            content: Markdown格式的大纲文本
            
        Returns:
            所有标题节点的列表
        """
        self.headings = []
        self.root_headings = []
        
        lines = content.split('\n')
        parent_stack: List[HeadingNode] = []  # 用于追踪父级标题
        
        for line_num, line in enumerate(lines, start=1):
            match = self.HEADING_PATTERN.match(line.strip())
            if not match:
                continue
            
            level = len(match.group(1))
            title = match.group(2).strip()
            
            # 创建节点
            node = HeadingNode(
                level=level,
                title=title,
                full_path=title,
                line_number=line_num
            )
            
            # 建立父子关系
            # 弹出所有级别 >= 当前级别的节点
            while parent_stack and parent_stack[-1].level >= level:
                parent_stack.pop()
            
            if parent_stack:
                parent = parent_stack[-1]
                node.parent = parent
                parent.children.append(node)
                # 构建完整路径
                node.full_path = f"{parent.full_path} > {title}"
            else:
                self.root_headings.append(node)
            
            parent_stack.append(node)
            self.headings.append(node)
        
        return self.headings
    
    def get_level_headings(self, level: int) -> List[HeadingNode]:
        """
        获取指定级别的所有标题

        Args:
            level: 标题级别 (1, 2, 或 3)

        Returns:
            指定级别的标题列表
        """
        return [h for h in self.headings if h.level == level]

    def get_all_headings(self) -> List[HeadingNode]:
        """
        获取所有标题节点

        Returns:
            所有标题节点的列表
        """
        return self.headings
    
    def get_third_level_headings(self) -> List[HeadingNode]:
        """获取所有3级标题"""
        return self.get_level_headings(3)
    
    def get_deepest_headings(self) -> List[HeadingNode]:
        """
        获取最深层的可扩写标题
        
        逻辑：遍历所有标题，如果该标题没有子标题（是叶子节点），则纳入结果。
        这样可以确保：
        - 如果有3级标题，则显示3级标题
        - 如果某个2级标题没有3级子标题，则显示该2级标题
        - 如果某个1级标题没有子标题，则显示该1级标题
        
        Returns:
            叶子节点标题列表（按出现顺序）
        """
        result = []
        for heading in self.headings:
            # 只选择叶子节点（没有子标题的节点）
            if not heading.children:
                result.append(heading)
        return result
    
    def get_heading_context(self, heading: HeadingNode) -> str:
        """
        获取标题的上下文信息（包括父级标题）
        
        Args:
            heading: 标题节点
            
        Returns:
            格式化的上下文字符串
        """
        context_parts = []
        current = heading
        while current:
            context_parts.insert(0, current.title)
            current = current.parent
        return " > ".join(context_parts)
    
    def find_heading_by_title(self, title: str) -> Optional[HeadingNode]:
        """
        根据标题文本查找标题节点
        
        Args:
            title: 标题文本
            
        Returns:
            匹配的标题节点，如果没找到返回None
        """
        for heading in self.headings:
            if heading.title == title:
                return heading
        return None
    
    def get_siblings(self, heading: HeadingNode) -> List[HeadingNode]:
        """获取同级标题"""
        if heading.parent:
            return [h for h in heading.parent.children if h != heading]
        else:
            return [h for h in self.root_headings if h != heading]
    
    def to_tree_string(self, indent: str = "  ") -> str:
        """
        将大纲转换为树形结构字符串
        
        Args:
            indent: 缩进字符串
            
        Returns:
            树形结构的字符串表示
        """
        lines = []
        
        def _build_tree(node: HeadingNode, level: int = 0):
            prefix = indent * level
            lines.append(f"{prefix}{'#' * node.level} {node.title}")
            for child in node.children:
                _build_tree(child, level + 1)
        
        for root in self.root_headings:
            _build_tree(root)
        
        return "\n".join(lines)


def parse_outline(content: str) -> OutlineParser:
    """
    解析大纲内容的便捷函数
    
    Args:
        content: Markdown格式的大纲文本
        
    Returns:
        配置好的OutlineParser实例
    """
    parser = OutlineParser()
    parser.parse(content)
    return parser
