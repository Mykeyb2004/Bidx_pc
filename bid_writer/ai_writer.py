"""
AI扩写引擎
调用Gemini API进行内容扩写
"""

import re
from dataclasses import dataclass, field
from typing import Any, Generator, Optional
from openai import OpenAI

from .config import Config
from .context_pruner import ChapterContext, ChapterContextPruner
from .generation_trace import GenerationTraceLogger, GenerationTraceSession
from .outline_parser import HeadingNode


@dataclass
class PromptBuildResult:
    """提示词拼装结果。"""

    prompt: str
    prompt_sections: list[dict[str, str]] = field(default_factory=list)
    pruned_context: Optional[ChapterContext] = None
    context_mode: str = "full"
    full_context_stats: dict[str, Any] = field(default_factory=dict)


class AIWriter:
    """AI扩写引擎"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(
            base_url=config.api_base_url,
            api_key=config.api_key,
            timeout=config.api_timeout_seconds,
            max_retries=config.api_max_retries
        )
        self.context_pruner = ChapterContextPruner(config)
        self.trace_logger = GenerationTraceLogger(config)

    @staticmethod
    def _heading_chain(heading: HeadingNode) -> list[HeadingNode]:
        chain: list[HeadingNode] = []
        current: Optional[HeadingNode] = heading
        while current is not None:
            chain.insert(0, current)
            current = current.parent
        return chain

    @staticmethod
    def _title_core(text: str) -> str:
        stripped = re.sub(r'^\s*[\d一二三四五六七八九十百千万零]+(?:[.、]\d+)*[.、]?\s*', "", text.strip())
        return re.sub(r'\s+', ' ', stripped).strip()

    def _chapter_focus_terms(self, heading: HeadingNode, pruned_context: Optional[ChapterContext]) -> list[str]:
        title_core = self._title_core(heading.title)
        title_norm = title_core.replace(" ", "")
        focus_terms = list(pruned_context.chapter_focus_terms) if pruned_context and pruned_context.chapter_focus_terms else []

        concise_terms: list[str] = []
        seen: set[str] = set()
        for term in focus_terms:
            normalized = self._title_core(term).replace(" ", "")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned = self._title_core(term)
            if cleaned.endswith("理解") and len(cleaned) > 2:
                cleaned = cleaned[:-2]
            concise_terms.append(cleaned)

        decomposed_terms = [
            term for term in concise_terms
            if term.replace(" ", "") != title_norm and "与" not in term and "、" not in term
        ]
        if decomposed_terms:
            return decomposed_terms[:4]
        short_terms = [term for term in concise_terms if term.replace(" ", "") != title_norm]
        if short_terms:
            return short_terms[:4]
        if concise_terms:
            return concise_terms[:3]
        return [title_core] if title_core else [heading.title]

    def _build_task_card(self, heading: HeadingNode, pruned_context: Optional[ChapterContext], min_words: int) -> str:
        chain = self._heading_chain(heading)
        project_title = chain[0].title if chain else heading.title
        board_title = chain[1].title if len(chain) >= 2 else "（无）"
        bidder_name = self.config.prompt_bidder_name or "当前投标主体"
        focus_terms = self._chapter_focus_terms(heading, pruned_context)
        response_labels = ", ".join(pruned_context.response_labels) if pruned_context and pruned_context.response_labels else "（未命中明确响应板块）"

        lines = [
            "## 章节任务卡",
            f"- 写作场景：为{bidder_name}撰写“{project_title}”投标文件中的当前章节正文。",
            f"- 所属板块：{board_title}",
            f"- 响应板块：{response_labels}",
            f"- 本章重点：{'；'.join(focus_terms)}",
            f"- 字数要求：不少于 {min_words} 字",
            "- 输出方式：直接写投标正文，不重复标题，不写说明性语句，不另设总结。",
            "- 写作依据：优先根据下方评分关注和需求要点组织内容。",
        ]
        return "\n".join(lines)

    def _build_scope_reference(self, heading: HeadingNode) -> str:
        parent_title = heading.parent.title if heading.parent else "（无）"
        current_title = heading.title
        siblings = []
        if heading.parent:
            siblings = [node.title for node in heading.parent.children if node is not heading]
        sibling_text = "；".join(siblings) if siblings else "（无）"

        return "\n".join(
            [
                "## 章节边界参考",
                f"- 上级标题：{parent_title}",
                f"- 当前扩写标题：{current_title}",
                f"- 同级标题：{sibling_text}",
            ]
        )

    def _build_scoring_focus_section(self, pruned_context: ChapterContext) -> str:
        lines = [
            "## 评分关注",
        ]
        unique_subitems = {item.subitem for item in pruned_context.scoring_items if item.subitem}
        response_labels = [label for label in pruned_context.response_labels if label]
        if len(unique_subitems) == 1 and len(response_labels) == 1:
            only_subitem = next(iter(unique_subitems))
            if only_subitem == response_labels[0]:
                lines.append(
                    f"以下评分项主要命中所属板块“{response_labels[0]}”，未单独细分到当前小节；请结合当前章节主题提炼其中与本章直接相关的要求。"
                )
            else:
                lines.append("以下评分项与当前章节最相关，请优先回应其要求：")
        else:
            lines.append("以下评分项与当前章节最相关，请优先回应其要求：")

        lines.append(self._format_scoring_items(pruned_context.scoring_items))
        return "\n".join(lines)

    def _format_first_line(self, heading: HeadingNode) -> str:
        """渲染提示词中的首行模板"""
        template = self.config.prompt_first_line_template
        if not template:
            return ""
        try:
            return template.format(title=heading.title, full_path=heading.full_path)
        except (KeyError, ValueError):
            return template.replace("{title}", heading.title)

    def _build_hard_constraints(self) -> list[str]:
        """构建高优先级输出强约束。"""
        constraints: list[str] = []

        bidder_name = self.config.prompt_bidder_name
        if bidder_name:
            constraints.append(
                f"投标主体统一使用“{bidder_name}”表述；除非用户明确要求，不要替换为其他公司名称、简称或第一人称主体。"
            )

        constraints.extend(self.config.prompt_hard_constraints)

        # 保持顺序去重，避免 system prompt 重复罗列。
        unique_constraints: list[str] = []
        seen: set[str] = set()
        for constraint in constraints:
            normalized = constraint.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_constraints.append(normalized)
        return unique_constraints

    def build_system_prompt(self) -> str:
        """构建 system prompt，将强约束提升到最高优先级。"""
        sections = []
        role = self.config.role.strip()
        if role:
            sections.append(role)

        hard_constraints = self._build_hard_constraints()
        if hard_constraints:
            sections.append(
                "【最高优先级输出强约束】\n"
                "以下规则优先级高于其他风格建议、默认模板和惯常表达；如有冲突，必须以本节规则为准。\n"
                + "\n".join(f"- {rule}" for rule in hard_constraints)
            )

        return "\n\n".join(sections).strip()

    def _build_request_options(self, messages: list, stream: bool) -> dict:
        """构建模型请求参数"""
        options = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream
        }
        if self.config.api_top_p is not None:
            options["top_p"] = self.config.api_top_p
        if self.config.api_seed is not None:
            options["seed"] = self.config.api_seed
        return options

    @staticmethod
    def _format_scoring_items(scoring_items: list) -> str:
        """格式化命中的评分项。"""
        lines = []
        for item in scoring_items:
            title = item.subitem
            if item.weight:
                title = f"{title}（权重：{item.weight}）"
            lines.append(f"- {title}")
            lines.append(f"  {item.standard}")
        return "\n".join(lines)

    @staticmethod
    def _append_prompt_section(
        prompt_parts: list[str],
        prompt_sections: list[dict[str, str]],
        name: str,
        content: str,
    ) -> None:
        if not content:
            return
        prompt_parts.append(content)
        prompt_sections.append({"name": name, "content": content})

    def build_prompt_result(
        self,
        heading: HeadingNode,
        additional_requirements: str = "",
        min_words: int = 500
    ) -> PromptBuildResult:
        """
        构建扩写提示词
        
        Args:
            heading: 要扩写的标题节点
            additional_requirements: 用户的附加要求
            min_words: 最低字数要求
            
        Returns:
            完整的提示词
        """
        prompt_parts: list[str] = []
        prompt_sections: list[dict[str, str]] = []
        pruned_context = None
        context_mode = "full"
        full_context_stats: dict[str, Any] = {
            "outline_chars": 0,
            "bid_requirements_chars": 0,
            "scoring_criteria_chars": 0,
        }
        if self.config.context_pruning_enabled:
            try:
                pruned_context = self.context_pruner.build_context(heading)
            except Exception:
                pruned_context = None

        first_line = self._format_first_line(heading)
        self._append_prompt_section(
            prompt_parts,
            prompt_sections,
            "task_card",
            "\n".join(
                [
                    "请为以下标书章节撰写投标正文。",
                    "",
                    self._build_task_card(heading, pruned_context, min_words),
                ]
            ),
        )

        if first_line:
            self._append_prompt_section(
                prompt_parts,
                prompt_sections,
                "first_line_rule",
                "\n".join(
                    [
                        "## 首行要求",
                        f"- 首行固定输出：{first_line}",
                        "- 除首行外，不要再次重复当前标题。",
                    ]
                ),
            )

        if pruned_context is not None:
            context_mode = "pruned"
            self._append_prompt_section(
                prompt_parts,
                prompt_sections,
                "scope_reference",
                self._build_scope_reference(heading),
            )

            if pruned_context.scoring_items:
                self._append_prompt_section(
                    prompt_parts,
                    prompt_sections,
                    "scoring_focus",
                    self._build_scoring_focus_section(pruned_context),
                )

            if pruned_context.requirement_brief:
                self._append_prompt_section(
                    prompt_parts,
                    prompt_sections,
                    "requirement_brief",
                    f"""
## 需求要点
以下为根据项目需求提炼出的当前章节写作要点，请优先据此组织内容：
{pruned_context.requirement_brief}
""",
                )
            elif pruned_context.requirement_seed:
                self._append_prompt_section(
                    prompt_parts,
                    prompt_sections,
                    "requirement_points",
                    f"""
## 需求要点
以下为从项目采购需求中提炼出的当前章节要点，请优先围绕这些要求写作：
{pruned_context.requirement_seed}
""",
                )
        else:
            outline_content = self.config.get_outline_content().strip()
            full_context_stats["outline_chars"] = len(outline_content)
            if outline_content:
                self._append_prompt_section(
                    prompt_parts,
                    prompt_sections,
                    "full_outline",
                    f"""
## 完整总大纲参考
以下为本项目标书的完整 Markdown 大纲原文。请据此理解当前章节在全稿中的位置、边界和上下文关系。
请仅撰写“当前标题”负责的内容，不要照抄大纲，不要把其他章节应展开的内容提前写入本章节。

```markdown
{outline_content}
```
""",
                )

            # 添加招标需求上下文
            bid_requirements = self.config.bid_requirements.strip()
            full_context_stats["bid_requirements_chars"] = len(bid_requirements)
            if bid_requirements:
                self._append_prompt_section(
                    prompt_parts,
                    prompt_sections,
                    "bid_requirements",
                    f"""
## 招标需求参考
{bid_requirements}
""",
                )

            # 添加评分标准上下文
            scoring_criteria = self.config.scoring_criteria.strip()
            full_context_stats["scoring_criteria_chars"] = len(scoring_criteria)
            if scoring_criteria:
                self._append_prompt_section(
                    prompt_parts,
                    prompt_sections,
                    "scoring_criteria",
                    f"""
## 评分标准参考
{scoring_criteria}
""",
                )

        # 添加用户附加要求
        if additional_requirements:
            self._append_prompt_section(
                prompt_parts,
                prompt_sections,
                "additional_requirements",
                f"""
## 用户附加要求
{additional_requirements}
""",
            )

        prompt = "\n".join(prompt_parts)
        if pruned_context is not None:
            self.context_pruner.dump_debug(heading, pruned_context, prompt)
        return PromptBuildResult(
            prompt=prompt,
            prompt_sections=prompt_sections,
            pruned_context=pruned_context,
            context_mode=context_mode,
            full_context_stats=full_context_stats,
        )

    def build_prompt(
        self,
        heading: HeadingNode,
        additional_requirements: str = "",
        min_words: int = 500
    ) -> str:
        return self.build_prompt_result(heading, additional_requirements, min_words).prompt

    def expand(
        self,
        heading: HeadingNode,
        additional_requirements: str = "",
        min_words: int = 500,
        stream: bool = True
    ) -> Generator[str, None, None] | str:
        """
        扩写指定标题
        
        Args:
            heading: 要扩写的标题节点
            additional_requirements: 用户的附加要求
            min_words: 最低字数要求
            stream: 是否使用流式输出
            
        Yields/Returns:
            扩写的内容（流式或一次性返回）
        """
        prompt_result = self.build_prompt_result(heading, additional_requirements, min_words)
        system_prompt = self.build_system_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_result.prompt}
        ]
        request_options = self._build_request_options(messages, stream=stream)
        trace_session = self.trace_logger.start_session(
            heading=heading,
            additional_requirements=additional_requirements,
            min_words=min_words,
            stream=stream,
            system_prompt=system_prompt,
            user_prompt=prompt_result.prompt,
            prompt_sections=prompt_result.prompt_sections,
            context_mode=prompt_result.context_mode,
            pruned_context=prompt_result.pruned_context,
            full_context_stats=prompt_result.full_context_stats,
            request_options=request_options,
        )

        if stream:
            return self._stream_expand(request_options, trace_session)
        else:
            return self._sync_expand(request_options, trace_session)

    def _stream_expand(
        self,
        request_options: dict,
        trace_session: Optional[GenerationTraceSession] = None,
    ) -> Generator[str, None, None]:
        """流式扩写"""
        chunks: list[str] = []
        completed = False
        try:
            response = self.client.chat.completions.create(**request_options)
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    chunks.append(content)
                    yield content
            completed = True
        except Exception as exc:
            if trace_session is not None:
                trace_session.finalize("".join(chunks), status="failed", error=str(exc))
            raise
        finally:
            if trace_session is not None and not trace_session.finished:
                trace_session.finalize(
                    "".join(chunks),
                    status="completed" if completed else "interrupted",
                )

    def _sync_expand(
        self,
        request_options: dict,
        trace_session: Optional[GenerationTraceSession] = None,
    ) -> str:
        """同步扩写"""
        try:
            response = self.client.chat.completions.create(**request_options)
            content = response.choices[0].message.content or ""
        except Exception as exc:
            if trace_session is not None:
                trace_session.finalize("", status="failed", error=str(exc))
            raise

        if trace_session is not None:
            trace_session.finalize(content, status="completed")
        return content

    def count_chinese_words(self, text: str) -> int:
        """
        统计中文字数（包括标点和英文单词）
        
        Args:
            text: 要统计的文本
            
        Returns:
            字数
        """
        import re

        # 移除Markdown标记
        clean_text = re.sub(r'[#*`\[\]()>-]', '', text)

        # 统计中文字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', clean_text))

        # 统计英文单词
        english_words = len(re.findall(r'[a-zA-Z]+', clean_text))

        # 统计数字
        numbers = len(re.findall(r'\d+', clean_text))

        return chinese_chars + english_words + numbers
