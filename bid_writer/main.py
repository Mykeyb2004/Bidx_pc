#!/usr/bin/env python3
"""
自动标书撰写系统 - 主程序入口
"""

import argparse
import sys
from pathlib import Path

from .config import Config
from .outline_parser import parse_outline
from .terminal_ui import TerminalUI
from .ai_writer import AIWriter
from .file_saver import FileSaver
from .history import HistoryManager


class BidWriter:
    """标书撰写系统主类"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = Config(config_path)
        self.ui = TerminalUI()
        self.ai_writer = AIWriter(self.config)
        self.file_saver = FileSaver(
            self.config.output_directory,
            self.config.output_prefix
        )
        self.history = HistoryManager(
            self.config.history_file,
            self.config.history_max_records
        ) if self.config.history_enabled else None
        
        self.parser = None
    
    def load_outline(self) -> bool:
        """加载并解析大纲"""
        try:
            content = self.config.get_outline_content()
            self.parser = parse_outline(content)
            return True
        except FileNotFoundError as e:
            self.ui.show_error(str(e))
            return False
    
    def run_expansion(
        self,
        heading,
        additional_requirements: str,
        min_words: int
    ) -> tuple:
        """
        执行单个标题的扩写
        
        Returns:
            (成功标志, 内容, 字数, 文件路径)
        """
        self.ui.show_generating_progress(heading.title)
        
        # 收集流式输出的内容
        content_parts = []
        try:
            for chunk in self.ai_writer.expand(
                heading,
                additional_requirements,
                min_words,
                stream=True
            ):
                content_parts.append(chunk)
                self.ui.show_streaming_content(chunk)
        except Exception as e:
            self.ui.show_error(f"生成失败: {e}")
            return False, "", 0, ""
        
        content = "".join(content_parts)
        word_count = self.ai_writer.count_chinese_words(content)
        
        return True, content, word_count, ""
    
    def expand_with_preview(
        self,
        heading,
        additional_requirements: str,
        min_words: int
    ) -> bool:
        """
        执行扩写（带预览和确认）
        
        Returns:
            是否成功完成
        """
        while True:
            success, content, word_count, _ = self.run_expansion(
                heading, additional_requirements, min_words
            )
            
            if not success:
                return False
            
            # 预览并询问用户操作
            modification = self.ui.ask_for_modification()
            
            if modification == "DISCARD":
                self.ui.show_info("已放弃此内容")
                return False
            elif modification is not None:
                # 用户要求修改，追加修改要求后重新生成
                additional_requirements = f"{additional_requirements}\n\n用户修改要求：{modification}"
                continue
            else:
                # 用户确认保存
                break
        
        # 保存文件
        filepath = self.file_saver.save(heading.title, content)
        self.ui.show_generation_complete(word_count, str(filepath))
        
        # 记录历史
        if self.history:
            self.history.add_record(
                heading_title=heading.title,
                heading_path=heading.full_path,
                additional_requirements=additional_requirements,
                min_words=min_words,
                actual_words=word_count,
                output_file=str(filepath),
                status="success"
            )
        
        return True
    
    def batch_expand(self, expansion_params: list) -> int:
        """
        批量扩写
        
        Args:
            expansion_params: [(heading, requirements, min_words), ...]
            
        Returns:
            成功扩写的数量
        """
        success_count = 0
        total = len(expansion_params)
        
        for i, (heading, requirements, min_words) in enumerate(expansion_params, 1):
            self.ui.console.print(f"\n[bold cyan]━━━ 扩写进度 {i}/{total} ━━━[/bold cyan]")
            
            if self.expand_with_preview(heading, requirements, min_words):
                success_count += 1
        
        self.ui.console.print(f"\n[bold green]批量扩写完成！成功 {success_count}/{total}[/bold green]")
        return success_count
    
    def start_expansion_flow(self) -> None:
        """开始扩写流程"""
        if not self.load_outline():
            return
        
        # 显示大纲树
        self.ui.show_outline_tree(self.parser)
        
        # 使用层级导航选择标题
        selected = self.ui.select_heading_hierarchical(self.parser)
        
        if not selected:
            self.ui.show_info("未选择任何标题")
            return
        
        # 获取扩写参数
        if len(selected) == 1:
            requirements, min_words = self.ui.get_expansion_params()
            expansion_params = [(selected[0], requirements, min_words)]
        else:
            expansion_params = self.ui.get_batch_expansion_params(selected)
        
        # 执行批量扩写
        self.batch_expand(expansion_params)
    
    def show_history(self) -> None:
        """显示历史记录"""
        if not self.history:
            self.ui.show_info("历史记录功能未启用")
            return
        
        records = self.history.get_recent_records(20)
        self.ui.show_history(records)
    
    def show_statistics(self) -> None:
        """显示统计信息"""
        if not self.history:
            self.ui.show_info("历史记录功能未启用")
            return
        
        stats = self.history.get_statistics()
        self.ui.show_statistics(stats)
    
    def reload_config(self) -> None:
        """重新加载配置"""
        try:
            self.config.reload()
            self.ai_writer = AIWriter(self.config)
            self.file_saver = FileSaver(
                self.config.output_directory,
                self.config.output_prefix
            )
            self.ui.show_success("配置已重新加载")
        except Exception as e:
            self.ui.show_error(f"重新加载配置失败: {e}")
    
    def run(self) -> None:
        """运行主程序"""
        self.ui.show_welcome()
        
        while True:
            try:
                choice = self.ui.main_menu()
                
                if choice == "开始扩写":
                    self.start_expansion_flow()
                elif choice == "查看历史记录":
                    self.show_history()
                elif choice == "查看统计信息":
                    self.show_statistics()
                elif choice == "重新加载配置":
                    self.reload_config()
                elif choice == "退出":
                    self.ui.show_info("感谢使用，再见！")
                    break
                else:
                    break
            except KeyboardInterrupt:
                self.ui.console.print("\n")
                self.ui.show_info("操作已取消")
            except Exception as e:
                self.ui.show_error(f"发生错误: {e}")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="自动标书撰写系统",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="自动标书撰写系统 v1.0.0"
    )
    
    args = parser.parse_args()
    
    try:
        app = BidWriter(args.config)
        app.run()
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n程序已退出")
        sys.exit(0)


if __name__ == "__main__":
    main()
