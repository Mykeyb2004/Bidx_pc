#!/usr/bin/env python3
"""
Tkinter GUI 主界面
自动标书撰写系统的桌面版界面
"""

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, filedialog
from typing import List, Optional, Tuple
from pathlib import Path

from .main import BidWriter
from .gui_adapter import GUIAdapter
from .outline_parser import HeadingNode

import threading
import queue
import sys


class MainWindow(tk.Tk):
    """主窗口类"""

    def __init__(self, bid_writer: BidWriter):
        super().__init__()

        self.bid_writer = bid_writer
        self.adapter = GUIAdapter(bid_writer)

        # 树节点到HeadingNode的映射
        self.tree_node_map = {}

        # 窗口配置
        self.title("自动标书撰写系统 - GUI版")
        self.geometry("1000x800")

        # 最小尺寸
        self.minsize(800, 600)

        # 窗口居中
        self.center_window()

        # 图标（如果有的话）
        # self.iconbitmap('assets/icon.ico')

        # 创建组件
        self.create_menu_bar()
        self.create_tool_bar()
        self.create_main_panes()
        self.create_status_bar()

        # 加载大纲
        self.load_outline()

    def center_window(self):
        """居中窗口"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = tk.Menu(self)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="重新加载大纲", command=self.reload_outline)
        file_menu.add_command(label="刷新状态", command=self.refresh_status)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.quit)
        menubar.add_cascade(label="文件", menu=file_menu)

        # 操作菜单
        action_menu = tk.Menu(menubar, tearoff=0)
        action_menu.add_command(label="批量生成选中", command=self.batch_generate)
        action_menu.add_command(label="预览", command=self.preview_selected)
        action_menu.add_separator()
        action_menu.add_command(label="打开输出目录", command=self.open_output_dir)
        menubar.add_cascade(label="操作", menu=action_menu)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="使用说明", command=self.show_help)
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.config(menu=menubar)

    def create_tool_bar(self):
        """创建工具栏"""
        toolbar = ttk.Frame(self)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # 按钮
        btn_reload = ttk.Button(toolbar, text="🔄 重新加载",
                               command=self.reload_outline)
        btn_reload.pack(side=tk.LEFT, padx=2)

        btn_refresh = ttk.Button(toolbar, text="🔄 刷新状态",
                                command=self.refresh_status)
        btn_refresh.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT,
                                                       fill=tk.Y,
                                                       padx=10)

        btn_generate = ttk.Button(toolbar, text="⚡ 批量生成",
                                 command=self.batch_generate)
        btn_generate.pack(side=tk.LEFT, padx=2)

        btn_preview = ttk.Button(toolbar, text="👁️ 预览",
                                command=self.preview_selected)
        btn_preview.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT,
                                                       fill=tk.Y,
                                                       padx=10)

        btn_output = ttk.Button(toolbar, text="📂 输出目录",
                               command=self.open_output_dir)
        btn_output.pack(side=tk.LEFT, padx=2)

    def create_main_panes(self):
        """创建主面板"""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 标题和说明
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=5)

        ttk.Label(header_frame, text="📄 大纲结构（仅四级标题可多选）",
                 font=('TkDefaultFont', 10, 'bold')).pack(side=tk.LEFT)

        # 全选/全不选四级标题
        self.select_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(header_frame, text="全选四级标题",
                       variable=self.select_all_var,
                       command=self.toggle_select_all).pack(side=tk.RIGHT, padx=5)

        # 大纲树（支持多选）
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.outline_tree = ttk.Treeview(tree_frame, columns=("status", "progress"),
                                        height=30, show="tree headings",
                                        selectmode='extended')
        self.outline_tree.heading("#0", text="标题")
        self.outline_tree.heading("status", text="状态")
        self.outline_tree.heading("progress", text="进度")
        self.outline_tree.column("#0", width=600)
        self.outline_tree.column("status", width=80, anchor=tk.CENTER)
        self.outline_tree.column("progress", width=100, anchor=tk.CENTER)

        # 滚动条
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                          command=self.outline_tree.yview)
        self.outline_tree.config(yscrollcommand=sb.set)

        self.outline_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 绑定选择事件
        self.outline_tree.bind("<<TreeviewSelect>>", self.on_tree_select)

    def create_status_bar(self):
        """创建状态栏"""
        status_frame = ttk.Frame(self)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # 状态文本
        self.status_text = tk.StringVar()
        self.status_text.set("就绪")
        status_label = ttk.Label(status_frame, textvariable=self.status_text)
        status_label.pack(side=tk.LEFT, padx=5)

        # 进度条
        self.progress_bar = ttk.Progressbar(status_frame, mode='indeterminate')
        self.progress_bar.pack(side=tk.RIGHT, padx=5)

        # 统计信息
        self.stats_text = tk.StringVar()
        self.stats_text.set("已生成: 0 / 总计: 0")
        stats_label = ttk.Label(status_frame, textvariable=self.stats_text)
        stats_label.pack(side=tk.RIGHT, padx=10)

    def load_outline(self):
        """加载大纲到树形视图"""
        # 清空现有内容
        for item in self.outline_tree.get_children():
            self.outline_tree.delete(item)

        # 清空节点映射
        self.tree_node_map.clear()

        # 加载大纲
        if not self.bid_writer.load_outline():
            messagebox.showerror("错误", "加载大纲失败")
            return

        # 加载到树
        root_headings = self.adapter.get_outline_tree()
        for heading in root_headings:
            self._add_tree_node("", heading)

        self.update_stats()
        self.status_text.set("大纲加载完成")

    def _add_tree_node(self, parent: str, heading: HeadingNode):
        """递归添加树节点"""
        # 获取状态
        status = self.adapter.get_status_icon(heading)
        progress_info = ""

        if heading.children:
            generated, total = self.adapter.get_progress(heading)
            if total > 0:
                progress_info = f"{generated}/{total}"

        # 插入节点
        node_id = self.outline_tree.insert(
            parent, 'end',
            text=f" {heading.title}",
            values=(status, progress_info)
        )

        # 保存节点映射
        self.tree_node_map[node_id] = heading

        # 递归添加子节点
        for child in heading.children:
            self._add_tree_node(node_id, child)

    def on_tree_select(self, event):
        """当选择树节点时 - 只允许选择四级标题（叶子节点）"""
        selection = self.outline_tree.selection()
        if not selection:
            self.status_text.set("未选择任何标题")
            return

        # 过滤掉非叶子节点
        valid_selection = []
        invalid_count = 0

        for item_id in selection:
            heading = self.tree_node_map.get(item_id)
            if heading and not heading.children:
                # 这是叶子节点（四级标题），保留选择
                valid_selection.append(item_id)
            else:
                # 这不是叶子节点，取消选择
                invalid_count += 1

        # 如果有无效选择，重新设置选择
        if invalid_count > 0:
            # 清空当前选择
            for item_id in selection:
                self.outline_tree.selection_remove(item_id)
            # 只选择有效的
            for item_id in valid_selection:
                self.outline_tree.selection_add(item_id)

        # 更新状态栏
        count = len(valid_selection)
        if count == 0:
            self.status_text.set("请选择四级标题（叶子节点）")
        elif count == 1:
            heading = self.tree_node_map.get(valid_selection[0])
            self.status_text.set(f"已选择: {heading.title if heading else ''}")
        else:
            self.status_text.set(f"已选择 {count} 个四级标题")

    def on_title_select(self, event):
        """当选择标题时（已废弃，保留兼容性）"""
        pass

    def reload_outline(self):
        """重新加载大纲"""
        self.status_text.set("正在重新加载大纲...")
        self.load_outline()

    def refresh_status(self):
        """刷新状态"""
        self.status_text.set("正在刷新状态...")
        self.adapter.refresh_generated_titles()
        self.load_outline()
        self.status_text.set("状态刷新完成")

    def batch_generate(self):
        """批量生成选中的标题"""
        selection = self.outline_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要生成的四级标题")
            return

        # 获取选中的HeadingNode列表
        selected_headings = []
        for item_id in selection:
            heading = self.tree_node_map.get(item_id)
            if heading and not heading.children:
                selected_headings.append(heading)

        if not selected_headings:
            messagebox.showwarning("警告", "请选择四级标题（叶子节点）")
            return

        # 获取生成参数
        params = self._get_generation_params()
        if params is None:
            return  # 用户取消了

        additional_requirements, min_words = params

        # 确认对话框
        if not messagebox.askyesno("确认",
            f"确定要生成 {len(selected_headings)} 个标题吗？\n\n" +
            f"附加要求：{additional_requirements or '（无）'}\n" +
            f"最低字数：{min_words}"):
            return

        # 在主线程执行生成（避免线程安全问题）
        self._do_batch_generate(selected_headings, additional_requirements, min_words)

    def _do_batch_generate(self, headings: List[HeadingNode],
                           additional_requirements: str, min_words: int):
        """执行批量生成（主线程）"""
        # 开始进度条
        self.progress_bar.start()

        total = len(headings)
        success_count = 0
        skip_count = 0
        fail_count = 0

        for i, heading in enumerate(headings, 1):
            self.status_text.set(f"[{i}/{total}] 正在生成: {heading.title}")
            self.update_idletasks()  # 保持界面响应

            # 生成内容（可能需要多次修改）
            result = self._generate_with_preview(heading, additional_requirements, min_words)

            if result == "success":
                success_count += 1
            elif result == "skip":
                skip_count += 1
            else:
                fail_count += 1

        # 停止进度条
        self.progress_bar.stop()

        # 显示结果
        result_msg = f"批量生成完成\n\n成功: {success_count}\n跳过: {skip_count}\n失败: {fail_count}"
        if success_count > 0:
            messagebox.showinfo("完成", result_msg)
        else:
            messagebox.showwarning("完成", result_msg)

        # 刷新状态
        self.refresh_status()
        self.status_text.set(f"批量生成完成 - 成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}")

    def preview_selected(self):
        """预览选中的标题"""
        selection = self.outline_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要预览的标题")
            return

        if len(selection) > 1:
            messagebox.showwarning("警告", "只能预览单个标题")
            return

        item_id = selection[0]
        heading = self.tree_node_map.get(item_id)

        if not heading or heading.children:
            messagebox.showwarning("警告", "请选择四级标题（叶子节点）")
            return

        # 检查文件是否存在
        from .file_saver import FileSaver
        import re

        # 提取纯标题
        match = re.match(r'^\d+([.]\d+)*[_\s]+(.+)$', heading.title)
        title_text = match.group(2) if match else heading.title

        # 查找文件
        output_dir = Path(self.bid_writer.config.output_directory)
        sanitized = FileSaver(str(output_dir))._sanitize_filename(title_text)
        filepath = output_dir / f"{sanitized}.md"

        if filepath.exists():
            # 读取并预览
            content = filepath.read_text(encoding='utf-8')
            preview_window = tk.Toplevel(self)
            preview_window.title(f"预览 - {heading.title}")
            preview_window.geometry("800x600")

            text_widget = tk.Text(preview_window, wrap=tk.WORD, font=('Consolas', 10))
            scrollbar = ttk.Scrollbar(preview_window, command=text_widget.yview)
            text_widget.config(yscrollcommand=scrollbar.set)

            text_widget.insert('1.0', content)
            text_widget.config(state=tk.DISABLED)

            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            messagebox.showinfo("预览", f"文件未生成\n标题：{heading.title}")

    def toggle_select_all(self):
        """全选/全不选四级标题（叶子节点）"""
        # 清空当前选择
        for item_id in self.outline_tree.selection():
            self.outline_tree.selection_remove(item_id)

        if self.select_all_var.get():
            # 全选所有叶子节点
            self._select_all_leaf_nodes("")

    def _select_all_leaf_nodes(self, parent):
        """递归选择所有叶子节点"""
        children = self.outline_tree.get_children(parent)
        for child_id in children:
            heading = self.tree_node_map.get(child_id)
            if heading:
                if not heading.children:
                    # 这是叶子节点，选择它
                    self.outline_tree.selection_add(child_id)
                else:
                    # 递归处理子节点
                    self._select_all_leaf_nodes(child_id)

    def _get_generation_params(self):
        """
        获取生成参数对话框

        Returns:
            (additional_requirements, min_words) 或 None（用户取消）
        """
        dialog = tk.Toplevel(self)
        dialog.title("生成参数设置")
        dialog.geometry("500x250")
        dialog.transient(self)
        dialog.grab_set()

        # 居中对话框
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        result = {"cancelled": True}

        # 附加要求
        ttk.Label(dialog, text="附加扩写要求：",
                 font=('TkDefaultFont', 10)).pack(pady=(20, 5), padx=20, anchor=tk.W)

        req_text = tk.Text(dialog, height=5, width=60, font=('Consolas', 10))
        req_text.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)
        req_text.insert('1.0', "")

        # 最低字数
        words_frame = ttk.Frame(dialog)
        words_frame.pack(pady=10, padx=20, fill=tk.X)

        ttk.Label(words_frame, text="最低字数：",
                 font=('TkDefaultFont', 10)).pack(side=tk.LEFT)

        words_var = tk.StringVar(value="500")
        words_entry = ttk.Entry(words_frame, textvariable=words_var, width=10)
        words_entry.pack(side=tk.LEFT, padx=10)

        # 按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)

        def on_ok():
            try:
                min_words = int(words_var.get())
                if min_words < 0:
                    messagebox.showwarning("警告", "字数不能为负数")
                    return

                additional_req = req_text.get('1.0', tk.END).strip()
                result["cancelled"] = False
                result["requirements"] = additional_req
                result["min_words"] = min_words
                dialog.destroy()
            except ValueError:
                messagebox.showwarning("警告", "请输入有效的字数")

        def on_cancel():
            dialog.destroy()

        ttk.Button(button_frame, text="确定", command=on_ok,
                  width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel,
                  width=10).pack(side=tk.LEFT, padx=5)

        # 等待对话框关闭
        self.wait_window(dialog)

        if result["cancelled"]:
            return None
        return (result["requirements"], result["min_words"])

    class GenerationWindow:
        """生成进度窗口 - 异步流式显示"""

        def __init__(self, parent, heading_title: str):
            self.window = tk.Toplevel(parent)
            self.window.title(f"正在生成 - {heading_title}")
            self.window.geometry("800x600")
            self.window.transient(parent)

            # 不使用 grab_set()，允许用户查看其他窗口

            # 标题
            title_frame = ttk.Frame(self.window)
            title_frame.pack(fill=tk.X, padx=10, pady=10)

            ttk.Label(title_frame, text=f"正在生成：{heading_title}",
                     font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W)

            self.status_label = ttk.Label(title_frame, text="准备中...",
                                         font=('TkDefaultFont', 9))
            self.status_label.pack(anchor=tk.W)

            # 文本显示区域
            text_frame = ttk.Frame(self.window)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

            self.text_widget = tk.Text(text_frame, wrap=tk.WORD,
                                      font=('Consolas', 10), state=tk.DISABLED)
            scrollbar = ttk.Scrollbar(text_frame, command=self.text_widget.yview)
            self.text_widget.config(yscrollcommand=scrollbar.set)

            self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # 进度条
            self.progress = ttk.Progressbar(self.window, mode='indeterminate')
            self.progress.pack(fill=tk.X, padx=10, pady=5)
            self.progress.start()

            # 居中窗口
            self.window.update_idletasks()
            x = (self.window.winfo_screenwidth() // 2) - (self.window.winfo_width() // 2)
            y = (self.window.winfo_screenheight() // 2) - (self.window.winfo_height() // 2)
            self.window.geometry(f"+{x}+{y}")

            # 队列和状态
            self.text_queue = queue.Queue()
            self.is_generating = False
            self.error = None
            self.result_data = None

            # 注意：不在这里启动定时检查
            # 定时器将在 start_generation() 中启动

        def _check_queue(self):
            """定时检查队列并更新UI（主线程）"""
            try:
                while True:
                    msg_type, data = self.text_queue.get_nowait()

                    if msg_type == "text":
                        # 追加文本
                        self.text_widget.config(state=tk.NORMAL)
                        self.text_widget.insert(tk.END, data)
                        self.text_widget.see(tk.END)
                        self.text_widget.config(state=tk.DISABLED)

                    elif msg_type == "status":
                        # 更新状态
                        self.status_label.config(text=data)

                    elif msg_type == "done":
                        # 生成完成
                        self.is_generating = False
                        self.result_data = data
                        self.progress.stop()
                        return

                    elif msg_type == "error":
                        # 发生错误
                        self.error = data
                        self.is_generating = False
                        self.progress.stop()
                        return

            except queue.Empty:
                pass

            # 如果还在生成，继续定时检查（50ms）
            if self.is_generating:
                self.window.after(50, self._check_queue)

        def start_generation(self, heading, ai_writer, requirements, min_words):
            """启动后台生成线程"""
            self.is_generating = True
            self.progress.start()

            def _background_generate():
                """后台线程执行生成"""
                try:
                    self.text_queue.put(("status", "正在生成内容..."))

                    content_parts = []
                    for chunk in ai_writer.expand(heading, requirements, min_words, stream=True):
                        content_parts.append(chunk)
                        # 将文本块放入队列
                        self.text_queue.put(("text", chunk))

                    content = "".join(content_parts)
                    word_count = ai_writer.count_chinese_words(content)

                    self.text_queue.put(("status", f"生成完成 - {word_count} 字"))
                    self.text_queue.put(("done", (content, word_count)))

                except Exception as e:
                    self.text_queue.put(("error", str(e)))

            # 启动后台线程
            thread = threading.Thread(target=_background_generate, daemon=True)
            thread.start()

            # 启动定时检查队列（在主线程中）
            self._check_queue()

        def wait_completion(self):
            """等待生成完成并返回结果"""
            while self.is_generating:
                self.window.update()
                self.window.after(100)

            if self.error:
                raise Exception(self.error)

            return self.result_data  # (content, word_count)

        def close(self):
            """关闭窗口"""
            self.progress.stop()
            self.window.destroy()

    def _generate_with_preview(self, heading: HeadingNode,
                               additional_requirements: str,
                               min_words: int) -> str:
        """
        生成内容并预览确认（支持修改重新生成）- 完全异步

        Returns:
            "success" / "skip" / "failed"
        """
        current_requirements = additional_requirements

        while True:
            # 创建生成窗口
            gen_window = self.GenerationWindow(self, heading.title)

            # 启动后台生成
            gen_window.start_generation(
                heading,
                self.bid_writer.ai_writer,
                current_requirements,
                min_words
            )

            # 等待完成（不阻塞，窗口可交互）
            try:
                content, word_count = gen_window.wait_completion()
            except Exception as e:
                gen_window.close()
                messagebox.showerror("错误", f"生成失败: {str(e)}")
                return "failed"

            # 关闭生成窗口
            gen_window.close()

            # 显示预览对话框并获取用户操作
            action, modification = self._show_preview_dialog(heading, content, word_count)

            if action == "save":
                # 保存文件
                filepath = self.bid_writer.file_saver.save(heading.title, content)
                return "success"

            elif action == "modify":
                # 追加修改要求，重新生成
                if modification:
                    current_requirements = f"{current_requirements}\n\n用户修改要求：{modification}"
                continue

            else:  # action == "skip"
                return "skip"

    def _show_preview_dialog(self, heading: HeadingNode, content: str, word_count: int):
        """
        显示预览对话框

        Returns:
            (action, modification) where action is "save"/"modify"/"skip"
        """
        dialog = tk.Toplevel(self)
        dialog.title(f"预览 - {heading.title}")
        dialog.geometry("900x700")
        dialog.transient(self)
        dialog.grab_set()

        result = {"action": "skip", "modification": None}

        # 标题和字数信息
        info_frame = ttk.Frame(dialog)
        info_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(info_frame, text=f"标题：{heading.title}",
                 font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"字数：{word_count} 字",
                 font=('TkDefaultFont', 9)).pack(anchor=tk.W)

        # 内容预览
        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(text_frame, command=text_widget.yview)
        text_widget.config(yscrollcommand=scrollbar.set)

        text_widget.insert('1.0', content)
        text_widget.config(state=tk.DISABLED)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)

        def on_save():
            result["action"] = "save"
            dialog.destroy()

        def on_modify():
            # 弹出修改要求输入框
            mod_dialog = tk.Toplevel(dialog)
            mod_dialog.title("输入修改要求")
            mod_dialog.geometry("500x200")
            mod_dialog.transient(dialog)
            mod_dialog.grab_set()

            ttk.Label(mod_dialog, text="请输入修改要求：",
                     font=('TkDefaultFont', 10)).pack(pady=10, padx=20, anchor=tk.W)

            mod_text = tk.Text(mod_dialog, height=5, width=60, font=('Consolas', 10))
            mod_text.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)

            def submit_modification():
                modification = mod_text.get('1.0', tk.END).strip()
                if not modification:
                    messagebox.showwarning("警告", "请输入修改要求")
                    return
                result["action"] = "modify"
                result["modification"] = modification
                mod_dialog.destroy()
                dialog.destroy()

            ttk.Button(mod_dialog, text="确定", command=submit_modification).pack(pady=10)

            self.wait_window(mod_dialog)

        def on_skip():
            result["action"] = "skip"
            dialog.destroy()

        ttk.Button(button_frame, text="✅ 保存", command=on_save,
                  width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="✏️ 修改后重新生成", command=on_modify,
                  width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="⏭️ 跳过", command=on_skip,
                  width=15).pack(side=tk.LEFT, padx=5)

        # 等待对话框关闭
        self.wait_window(dialog)

        return result["action"], result["modification"]

    def open_output_dir(self):
        """打开输出目录"""
        output_dir = Path(self.bid_writer.config.output_directory)
        if output_dir.exists():
            import subprocess
            if sys.platform == "win32":
                subprocess.Popen(f'explorer "{output_dir}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(output_dir)])
            else:
                subprocess.Popen(["xdg-open", str(output_dir)])
        else:
            messagebox.showerror("错误", "输出目录不存在")

    def update_stats(self):
        """更新统计信息"""
        all_headings = self.adapter.get_all_headings()
        leaf_nodes = [h for h in all_headings if not h.children]

        generated = 0
        for node in leaf_nodes:
            if self.adapter.is_heading_generated(node):
                generated += 1

        total = len(leaf_nodes)
        self.stats_text.set(f"已生成: {generated} / 总计: {total}")

    def show_help(self):
        """显示帮助"""
        help_text = """使用说明：

1. 在左侧大纲树中选择节点
2. 右侧会显示该节点下的四级标题
3. 使用 Ctrl+点击 多选标题
4. 点击"批量生成"按钮开始生成
5. 生成完成后状态会自动更新

快捷键：
- Ctrl+A: 全选
- Delete: 删除选中
- F5: 刷新状态
"""
        messagebox.showinfo("使用说明", help_text)

    def show_about(self):
        """显示关于"""
        about_text = """自动标书撰写系统（GUI版）

版本：1.0.0
基于：Python + Tkinter
功能：AI辅助标书撰写

功能特点：
- 大纲导航
- 批量生成
- 状态跟踪
- 进度显示
"""
        messagebox.showinfo("关于", about_text)


def run_gui(config_path: str = "config.yaml"):
    """运行GUI应用"""
    # 创建BidWriter实例
    bid_writer = BidWriter(config_path)

    # 检查大纲加载
    if not bid_writer.load_outline():
        print("加载大纲失败，请检查配置文件")
        return

    # 创建并运行GUI
    app = MainWindow(bid_writer)
    app.mainloop()


if __name__ == "__main__":
    run_gui()
