"""
交互式终端界面模块
提供用户友好的命令行交互体验
"""

import re
import questionary
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.syntax import Syntax
from typing import List, Optional, Tuple, Set

from .outline_parser import HeadingNode, OutlineParser
from .history import HistoryRecord


console = Console()


class TerminalUI:
    """交互式终端界面"""
    
    def __init__(self):
        self.console = console
        self.output_directory: Optional[Path] = None
        self._generated_titles: Set[str] = set()

    def _sanitize_for_comparison(self, title: str) -> str:
        """
        清理标题用于比对（与file_saver的sanitize_filename保持一致）

        Args:
            title: 要清理的标题

        Returns:
            清理后的标题
        """
        if not title:
            return ""

        invalid_chars = r'[\\/: *?"<>|\n\r\t]'
        clean = re.sub(invalid_chars, '_', title)
        clean = clean.strip(' .')
        clean = re.sub(r'[_\s]+', '_', clean)

        return clean
    
    def set_output_directory(self, directory: str) -> None:
        """
        设置输出目录，用于检查已生成的文件
        
        Args:
            directory: 输出目录路径
        """
        self.output_directory = Path(directory)
        self._refresh_generated_titles()
    
    def _refresh_generated_titles(self) -> None:
        """刷新已生成标题的缓存"""
        self._generated_titles.clear()
        if self.output_directory and self.output_directory.exists():
            for md_file in self.output_directory.glob("*.md"):
                # 提取文件名中的标题部分
                # 支持格式："1.1.1_标题_2" 或 "1.1.1_标题" 或 "1.1.1 标题.md"
                stem = md_file.stem

                # 移除末尾的序号（如 _1, _2）
                stem_no_suffix = re.sub(r'_\d+$', '', stem)

                # 提取标题部分，支持多级序号（如 1, 1.1, 1.1.1, 1.1.1.1）
                # 正则解释：
                # ^\d+([.]\d+)*  - 匹配开头多级编号（支持任意层级）
                # [_\s]+         - 匹配下划线或空格作为分隔符
                # (.+?)          - 非贪婪匹配标题文本（.+? 会匹配剩余所有字符）
                match = re.match(r'^\d+([.]\d+)*[_\s]+(.+)$', stem_no_suffix)

                if match:
                    title_part = match.group(2)
                    clean_title = self._sanitize_for_comparison(title_part)
                    if clean_title:
                        self._generated_titles.add(clean_title)

    def get_heading_generation_status(self, heading: HeadingNode) -> tuple:
        """
        检查标题及所有子标题的生成状态

        返回: (状态图标, 已生成数量, 总数量)
        - 状态图标: ✅ (全部完成) / 📝 (部分完成) / ❌ (未开始)
        """
        if not self.output_directory:
            return "❌", 0, 0

        # 获取所有可生成的叶子节点（四级标题）
        leaf_nodes = []

        def collect_leaves(node):
            if not node.children:
                leaf_nodes.append(node)
            else:
                for child in node.children:
                    collect_leaves(child)

        for child in heading.children:
            collect_leaves(child)

        if not leaf_nodes:
            # 没有可生成的子标题
            return "❌", 0, 0

        total = len(leaf_nodes)
        generated = 0

        # 统计已生成的数量
        for node in leaf_nodes:
            filename = self._sanitize_for_comparison(node.title)
            if filename in self._generated_titles:
                generated += 1

        # 确定状态图标
        if generated == total and total > 0:
            icon = "✅"  # 全部完成
        elif generated > 0:
            icon = "📝"  # 部分完成
        else:
            icon = "❌"  # 未开始

        return icon, generated, total

    def is_heading_generated(self, heading: HeadingNode) -> bool:
        """
        检查标题是否已生成（兼容性方法，任一子标题已生成即返回True）

        Args:
            heading: 标题节点

        Returns:
            是否已生成
        """
        icon, generated, total = self.get_heading_generation_status(heading)
        return generated > 0
    
    
    def show_welcome(self) -> None:
        """显示欢迎信息"""
        self.console.print(Panel.fit(
            "[bold blue]自动标书撰写系统[/bold blue]\n"
            "[dim]基于AI的智能标书内容生成工具[/dim]",
            border_style="blue"
        ))
    
    def show_outline_tree(self, parser: OutlineParser) -> None:
        """
        显示大纲树形结构
        
        Args:
            parser: 大纲解析器实例
        """
        tree = Tree("📄 [bold]标书大纲[/bold]")
        
        def add_to_tree(node: HeadingNode, parent_tree):
            # 根据级别设置不同的样式
            if node.level == 1:
                style = "bold cyan"
                icon = "📁"
            elif node.level == 2:
                style = "green"
                icon = "📂"
            else:
                style = "yellow"
                icon = "📝"
            
            branch = parent_tree.add(f"{icon} [{style}]{node.title}[/{style}]")
            for child in node.children:
                add_to_tree(child, branch)
        
        for root in parser.root_headings:
            add_to_tree(root, tree)
        
        self.console.print(tree)
        self.console.print()
    
    def select_headings(
        self,
        headings: List[HeadingNode],
        allow_multiple: bool = True
    ) -> List[HeadingNode]:
        """
        让用户选择要扩写的标题
        
        Args:
            headings: 可选的标题列表
            allow_multiple: 是否允许多选
            
        Returns:
            用户选择的标题列表
        """
        if not headings:
            self.console.print("[red]没有可选的3级标题！[/red]")
            return []
        
        # 构建选项 - 只显示三级标题本身
        choices = []
        for i, h in enumerate(headings, 1):
            # 只显示标题本身，不显示完整路径
            choices.append({
                "name": f"{h.title}",
                "value": h
            })
        
        self.console.print("\n[bold]请选择要扩写的标题：[/bold]")
        self.console.print("[dim]（使用空格选择，回车确认）[/dim]\n")
        
        # 定义反白高亮样式
        custom_style = questionary.Style([
            ('qmark', 'fg:cyan bold'),           # 问号标记
            ('question', 'bold'),                 # 问题文字
            ('answer', 'fg:cyan bold'),           # 答案
            ('pointer', 'fg:white bg:blue bold'), # 指针（反白效果）
            ('highlighted', 'fg:white bg:blue bold'),  # 高亮选中项（反白效果）
            ('selected', 'fg:green bold'),        # 已选中的项
            ('separator', 'fg:gray'),             # 分隔符
            ('instruction', 'fg:gray'),           # 使用说明
            ('text', ''),                         # 普通文字
        ])
        
        if allow_multiple:
            selected = questionary.checkbox(
                "选择标题（可多选）：",
                choices=[c["name"] for c in choices],
                style=custom_style
            ).ask()
            
            if not selected:
                return []
            
            # 根据选择的名称找到对应的HeadingNode
            result = []
            for name in selected:
                for choice in choices:
                    if choice["name"] == name:
                        result.append(choice["value"])
                        break
            return result
        else:
            selected = questionary.select(
                "选择标题：",
                choices=[c["name"] for c in choices],
                style=custom_style
            ).ask()
            
            if not selected:
                return []
            
            for choice in choices:
                if choice["name"] == selected:
                    return [choice["value"]]
            return []
    
    def select_heading_hierarchical(
        self,
        parser: OutlineParser
    ) -> List[HeadingNode]:
        """
        层级导航选择标题

        通过三层导航逐步深入选择：
        1. 选择1级标题（章节）
        2. 选择2级标题（子章节）
        3. 选择叶子节点（可扩写的标题，支持多选）

        Args:
            parser: 大纲解析器实例

        Returns:
            用户选择的标题列表
        """
        # 反白高亮样式
        custom_style = questionary.Style([
            ('qmark', 'fg:cyan bold'),
            ('question', 'bold'),
            ('answer', 'fg:cyan bold'),
            ('pointer', 'fg:white bg:blue bold'),
            ('highlighted', 'fg:white bg:blue bold'),
            ('selected', 'fg:green bold'),
            ('separator', 'fg:gray'),
            ('instruction', 'fg:gray'),
            ('text', ''),
        ])
        
        # 第一层：选择1级标题
        while True:
            level1_headings = parser.get_level_headings(1)
            if not level1_headings:
                self.console.print("[red]大纲中没有章节标题！[/red]")
                return []
            
            self.console.print("\n[bold cyan]📁 第一步：选择章节[/bold cyan]")

            # 构建选项（移除翻页功能）
            level1_result = self._select_with_pagination(
                headings=level1_headings,
                prompt="选择章节：",
                icon="📁",
                style=custom_style,
                allow_back=False
            )
            
            if level1_result is None:  # 用户取消
                return []
            
            selected_level1 = level1_result
            
            # 第二层：选择2级标题
            while True:
                level2_headings = selected_level1.children
                
                if not level2_headings:
                    # 如果没有2级标题，检查是否为叶子节点
                    if not selected_level1.children:
                        self.console.print(f"[yellow]「{selected_level1.title}」没有子标题，已选中该标题[/yellow]")
                        return [selected_level1]
                
                self.console.print(f"\n[bold green]📂 第二步：选择子章节[/bold green]")
                self.console.print(f"[dim]当前位置：{selected_level1.title}[/dim]")

                level2_result = self._select_with_pagination(
                    headings=level2_headings,
                    prompt="选择子章节：",
                    icon="📂",
                    style=custom_style,
                    allow_back=True
                )
                
                if level2_result == "BACK":  # 返回上一级
                    break
                if level2_result is None:  # 用户取消
                    return []
                
                selected_level2 = level2_result
                
                # 第三层：选择叶子节点（多选）
                while True:
                    # 获取该节点下的所有叶子节点
                    # 获取三级标题作为分类（不是直接获取叶子节点）
                    level3_headings = selected_level2.children

                    if not level3_headings:
                        # 该节点本身就是叶子节点
                        self.console.print(f"[yellow]「{selected_level2.title}」没有子标题，已选中该标题[/yellow]")
                        return [selected_level2]

                    self.console.print(f"\n[bold yellow]📝 第三步：选择三级分类[/bold yellow]")
                    self.console.print(f"[dim]当前位置：{selected_level1.title} > {selected_level2.title}[/dim]\n")

                    # 选择三级标题（作为分类）
                    level3_selected = self._select_with_pagination(
                        headings=level3_headings,
                        prompt="选择三级分类（显示该分类下的所有四级标题）：",
                        icon="📁",
                        style=custom_style,
                        allow_back=True
                    )

                    if level3_selected == "BACK":
                        continue  # 返回重新选择二级标题
                    if level3_selected is None:
                        continue  # 取消选择

                    # 获取选中的三级标题下的所有叶子节点（四级标题）
                    leaf_headings = self._get_leaf_nodes(level3_selected)

                    if not leaf_headings:
                        # 该三级标题没有子节点，本身就是四级标题
                        return [level3_selected]

                    self.console.print(f"\n[bold cyan]📝 第四步：选择要扩写的标题（可多选）[/bold cyan]")
                    self.console.print(f"[dim]当前位置：{selected_level1.title} > {selected_level2.title} > {level3_selected.title}[/dim]")

                    leaf_result = self._select_leaves_with_pagination(
                        headings=leaf_headings,
                        parent_title=f"{selected_level1.title} > {selected_level2.title} > {level3_selected.title}",
                        prompt="选择四级标题（空格选择，回车确认）：",
                        style=custom_style
                    )

                    if leaf_result == "BACK":
                        continue  # 返回重新选择三级分类
                    if leaf_result is None or len(leaf_result) == 0:
                        continue  # 未选择任何标题

                    return leaf_result
    
    def _get_leaf_nodes(self, heading: HeadingNode) -> List[HeadingNode]:
        """获取某节点下的所有叶子节点"""
        leaves = []
        
        def collect_leaves(node: HeadingNode):
            if not node.children:
                leaves.append(node)
            else:
                for child in node.children:
                    collect_leaves(child)
        
        for child in heading.children:
            collect_leaves(child)
        
        return leaves
    
    def _select_with_pagination(
        self,
        headings: List[HeadingNode],
        prompt: str,
        icon: str,
        style,
        allow_back: bool = False
    ) -> Optional[HeadingNode]:
        """
        单选（移除翻页功能，page_size参数不再需要）

        Returns:
            选中的HeadingNode，"BACK"表示返回上一级，None表示取消
        """
        # 构建选项
        choices = []
        for h in headings:
            # 获取生成状态
            status_icon, generated, total = self.get_heading_generation_status(h)

            # 对于一、二、三级标题（有子节点的），使用固定的图标
            if h.children:
                # 有子节点的标题，使用文件夹图标
                if status_icon == "✅":
                    folder_icon = "📁"  # 全部完成
                elif status_icon == "📝":
                    folder_icon = "📂"  # 部分完成，显示进度
                else:
                    folder_icon = "📁"  # 未开始

                if status_icon == "📝":
                    choice_text = f"{folder_icon} {h.title} ({generated}/{total})"
                else:
                    choice_text = f"{folder_icon} {h.title}"
            else:
                # 叶子节点（四级标题），使用状态图标
                if status_icon == "📝":
                    choice_text = f"{status_icon} {h.title} ({generated}/{total})"
                else:
                    choice_text = f"{status_icon} {h.title}"
            choices.append(choice_text)

        # 添加导航选项
        choices.append(questionary.Separator())
        if allow_back:
            choices.append("↩️  返回上一级")
        choices.append("❌ 取消")

        selected = questionary.select(
            prompt,
            choices=choices,
            style=style
        ).ask()

        # Esc键返回None，等同于返回上一级（如果允许）
        if selected is None:
            if allow_back:
                return "BACK"
            else:
                return None
        elif selected == "❌ 取消":
            return None
        elif selected == "↩️  返回上一级":
            return "BACK"
        else:
            # 找到对应的HeadingNode
            # 移除状态图标前缀（✅/📝/❌）和进度信息
            title = selected

            # 移除进度信息 (格式: "标题 (X/Y)") - 先处理，因为包含空格
            if '(' in title and title.endswith(')'):
                title = title.rsplit(' (', 1)[0]

            # 移除状态图标（分割第一个空格后的部分）
            if ' ' in title:
                title = title.split(' ', 1)[1]

            # 移除首尾空格
            title = title.strip()

            for h in headings:
                if h.title == title:
                    return h
    
    def _select_leaves_with_pagination(
        self,
        headings: List[HeadingNode],
        parent_title: str,
        prompt: str,
        style
    ):
        """
        多选（用于选择叶子节点，移除翻页功能）

        Args:
            headings: 叶子节点列表
            parent_title: 父节点路径（如：一级标题 > 二级标题）
            prompt: 提示文本
            style: 样式

        Returns:
            选中的HeadingNode列表，"BACK"表示返回上一级，None表示取消
        """
        all_selected = set()  # 记录所有已选中的标题

        # 显示上级节点信息（只显示一次）
        self.console.print(f"\n[dim]上级节点：{parent_title}[/dim]")

        while True:
            # 构建选项
            choices = []
            for h in headings:
                # 对于四级标题，需要从完整标题中提取纯文本（移除编号）
                title_match = re.match(r'^\d+([.]\d+)*[_\s]+(.+)$', h.title)
                if title_match:
                    title_text = title_match.group(2)  # 提取纯标题文本
                else:
                    title_text = h.title

                # 检查是否已生成
                filename = self._sanitize_for_comparison(title_text)
                is_generated = filename in self._generated_titles
                status_icon = "✅" if is_generated else "❌"
                choice_name = f"{status_icon} {h.title}"

                # 标记已选中的项
                choices.append(questionary.Choice(
                    title=choice_name,
                    checked=h.title in all_selected
                ))

            selected = questionary.checkbox(
                prompt,
                choices=choices,
                style=style
            ).ask()
            
            if selected is None:
                # 用户按Ctrl+C取消
                return None
            
            # 更新已选集合
            for h in headings:
                # 重建选择名称（与实际显示一致）
                # 需要从完整标题中提取纯文本
                title_match = re.match(r'^\d+([.]\d+)*[_\s]+(.+)$', h.title)
                if title_match:
                    title_text = title_match.group(2)
                else:
                    title_text = h.title

                filename = self._sanitize_for_comparison(title_text)
                is_generated = filename in self._generated_titles
                status_icon = "✅" if is_generated else "❌"
                choice_name = f"{status_icon} {h.title}"

                if choice_name in selected:
                    all_selected.add(h.title)
                else:
                    all_selected.discard(h.title)

            # 显示操作菜单
            nav_choices = []
            nav_choices.append("↩️  返回上一级")
            if all_selected:
                nav_choices.append(f"✅ 确认选择（{len(all_selected)}项）")
            nav_choices.append("❌ 取消")
            
            action = questionary.select(
                "操作：",
                choices=nav_choices,
                style=style
            ).ask()
            
            if action is None or action == "❌ 取消":
                return None
            elif action == "⬆️  上一页":
                current_page -= 1
            elif action == "⬇️  下一页":
                current_page += 1
            elif action == "↩️  返回上一级":
                return "BACK"
            elif action.startswith("✅ 确认选择"):
                # 返回所有选中的HeadingNode
                result = []
                for h in headings:
                    if h.title in all_selected:
                        result.append(h)
                return result
    
    def get_expansion_params(self) -> Tuple[str, int]:
        """
        获取扩写参数
        
        Returns:
            (附加要求, 最低字数)
        """
        self.console.print("\n[bold]请输入扩写参数：[/bold]\n")
        
        # 获取附加要求
        additional_requirements = Prompt.ask(
            "附加扩写要求",
            default="",
            console=self.console
        )
        
        # 获取最低字数
        min_words = IntPrompt.ask(
            "最低字数要求",
            default=500,
            console=self.console
        )
        
        return additional_requirements, min_words
    
    def get_batch_expansion_params(
        self,
        headings: List[HeadingNode]
    ) -> List[Tuple[HeadingNode, str, int]]:
        """
        获取批量扩写参数
        
        Args:
            headings: 要扩写的标题列表
            
        Returns:
            [(标题, 附加要求, 最低字数), ...]
        """
        self.console.print("\n[bold]批量扩写参数设置[/bold]")
        
        # 询问是否使用统一参数
        use_unified = Confirm.ask(
            "是否对所有标题使用相同的参数？",
            default=True,
            console=self.console
        )
        
        if use_unified:
            additional_requirements, min_words = self.get_expansion_params()
            return [(h, additional_requirements, min_words) for h in headings]
        else:
            results = []
            for i, heading in enumerate(headings, 1):
                self.console.print(f"\n[cyan]标题 {i}/{len(headings)}：{heading.title}[/cyan]")
                additional_requirements, min_words = self.get_expansion_params()
                results.append((heading, additional_requirements, min_words))
            return results
    
    def show_generating_progress(self, title: str) -> None:
        """显示生成中的提示"""
        self.console.print(f"\n[bold green]正在生成：{title}[/bold green]")
        self.console.print("[dim]" + "─" * 50 + "[/dim]")
    
    def show_streaming_content(self, content: str) -> None:
        """显示流式生成的内容片段"""
        self.console.print(content, end="")
    
    def show_generation_complete(self, word_count: int, filepath: str) -> None:
        """显示生成完成信息"""
        self.console.print("\n[dim]" + "─" * 50 + "[/dim]")
        self.console.print(f"[green]✓ 生成完成！[/green]")
        self.console.print(f"  字数：{word_count}")
        self.console.print(f"  保存至：{filepath}")
    
    def preview_content(self, title: str, content: str) -> bool:
        """
        预览生成的内容
        
        Args:
            title: 标题
            content: 内容
            
        Returns:
            用户是否确认保存
        """
        self.console.print("\n[bold]内容预览：[/bold]")
        
        # 如果内容太长，只显示前500字
        preview_content = content
        if len(content) > 1000:
            preview_content = content[:1000] + "\n\n[dim]... (内容已截断，完整内容将保存到文件)[/dim]"
        
        self.console.print(Panel(
            Markdown(f"# {title}\n\n{preview_content}"),
            border_style="blue",
            title="预览"
        ))
        
        return Confirm.ask("确认保存此内容？", default=True, console=self.console)
    
    def ask_for_modification(self) -> Optional[str]:
        """
        询问用户是否要修改内容
        
        Returns:
            修改要求，如果不修改返回None
        """
        action = questionary.select(
            "请选择操作：",
            choices=[
                "保存",
                "修改后重新生成",
                "放弃"
            ]
        ).ask()
        
        if action == "修改后重新生成":
            return Prompt.ask("请输入修改要求", console=self.console)
        elif action == "放弃":
            return "DISCARD"
        else:
            return None
    
    def show_history(self, records: List[HistoryRecord]) -> None:
        """显示历史记录"""
        if not records:
            self.console.print("[dim]暂无历史记录[/dim]")
            return
        
        table = Table(title="扩写历史记录", show_lines=True)
        table.add_column("时间", style="cyan", width=20)
        table.add_column("标题", style="green")
        table.add_column("字数", justify="right", style="yellow")
        table.add_column("状态", justify="center")
        table.add_column("文件", style="dim")
        
        for record in records:
            # 格式化时间
            time_str = record.timestamp[:19].replace("T", " ")
            
            # 状态颜色
            status_style = {
                "success": "[green]✓ 成功[/green]",
                "failed": "[red]✗ 失败[/red]",
                "modified": "[yellow]📝 已修改[/yellow]"
            }.get(record.status, record.status)
            
            table.add_row(
                time_str,
                record.heading_title[:30] + ("..." if len(record.heading_title) > 30 else ""),
                str(record.actual_words),
                status_style,
                record.output_file.split("/")[-1]
            )
        
        self.console.print(table)
    
    def show_statistics(self, stats: dict) -> None:
        """显示统计信息"""
        self.console.print(Panel(
            f"[bold]统计信息[/bold]\n\n"
            f"总扩写次数：{stats['total']}\n"
            f"成功：[green]{stats['success']}[/green]\n"
            f"失败：[red]{stats['failed']}[/red]\n"
            f"已修改：[yellow]{stats['modified']}[/yellow]\n"
            f"总生成字数：{stats['total_words']:,}",
            border_style="blue"
        ))
    
    def main_menu(self) -> str:
        """
        显示主菜单
        
        Returns:
            用户选择的操作
        """
        return questionary.select(
            "请选择操作：",
            choices=[
                "开始扩写",
                "查看历史记录",
                "查看统计信息",
                "重新加载配置",
                "退出"
            ]
        ).ask()
    
    def show_error(self, message: str) -> None:
        """显示错误信息"""
        self.console.print(f"[red]错误：{message}[/red]")
    
    def show_success(self, message: str) -> None:
        """显示成功信息"""
        self.console.print(f"[green]✓ {message}[/green]")
    
    def show_info(self, message: str) -> None:
        """显示提示信息"""
        self.console.print(f"[blue]ℹ {message}[/blue]")
