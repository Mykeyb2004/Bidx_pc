"""
AI扩写引擎
调用Gemini API进行内容扩写
"""

import queue
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generator, Optional
from openai import OpenAI

from .config import Config
from .context_pruner import ChapterContext, ChapterContextPruner
from .generation_trace import GenerationTraceLogger, GenerationTraceSession
from .outline_parser import HeadingNode
from .timing_logger import write_timing_log


@dataclass
class PromptBuildResult:
    """提示词拼装结果。"""

    prompt: str
    prompt_sections: list[dict[str, str]] = field(default_factory=list)
    prompt_contract_blocks: list[dict[str, Any]] = field(default_factory=list)
    pruned_context: Optional[ChapterContext] = None
    context_mode: str = "full"
    full_context_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class FinalizeResult:
    """生成结果后处理。"""

    content: str
    postprocess: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreparedGeneration:
    """一次生成请求的已准备上下文。"""

    request_options: dict[str, Any]
    heading_title: str
    heading_full_path: str
    trace_id: str = ""
    trace_session: Optional[GenerationTraceSession] = None
    stream: bool = True


class AIWriter:
    """AI扩写引擎"""

    _PROMPT_CONTRACT_BLOCKS: tuple[tuple[str, str, str], ...] = (
        ("system_constraints", "System Constraints", "system"),
        ("chapter_task", "Chapter Task", "user"),
        ("structure_rules", "Structure Rules", "user"),
        ("chapter_scope", "Chapter Scope", "user"),
        ("requirement_context", "Requirement Context", "user"),
        ("scoring_context", "Scoring Context", "user"),
    )

    _FORMAL_HEADING_LINE_RE = re.compile(
        r'(?m)^\s*(?:[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[)）]|\d+\.|[（(]\d+[)）])'
    )
    _DISALLOWED_PARAGRAPH_TRANSITION_RE = re.compile(
        r'(?m)(?:^|(?<=\n)\s*|(?<=\n\n)\s*)(首先|其次|再次|最后)[，、,.：:]?'
    )
    _MARKDOWN_HEADING_RE = re.compile(r'(?m)^\s*#{1,6}\s+')
    _MARKDOWN_TABLE_LINE_RE = re.compile(r'^\s*\|?.+\|.+\|?\s*$')
    _MARKDOWN_TABLE_ALIGN_RE = re.compile(r'^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$')
    _SUMMARY_HEADING_RE = re.compile(
        r'(?m)^\s*(?:[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[)）]|\d+\.|[（(]\d+[)）])?\s*(章节小结|小结|总结)\s*$'
    )
    _SECTION_STYLE_SPLIT_RE = re.compile(r'\n\s*\n')
    
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
        bidder_name = self.config.prompt_bidder_name or "当前投标主体"
        focus_terms = self._chapter_focus_terms(heading, pruned_context)

        lines = [
            "## 章节任务卡",
            f"- 写作场景：为{bidder_name}撰写“{project_title}”投标文件中的当前章节正文。",
            f"- 本章重点：{'；'.join(focus_terms)}",
            f"- 字数要求：不少于 {min_words} 字",
            f"- 输出方式：按“{self.config.prompt_output_format}”组织内容，直接写投标正文，不重复标题，不写说明性语句。",
            "- 结构要求：默认使用正式层级序号组织正文，不要写成整篇无序号的长段落。",
            f"- 表格控制：{self._build_table_rule_text()}",
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

        if not self.config.prompt_allow_markdown_headings:
            constraints.append("严禁使用Markdown标题符号（#）。")
        if not self.config.prompt_allow_english_terms:
            constraints.append("除专有名词或用户明确要求外，禁止输出不必要的英文、英文缩写或中英对照。")
        constraints.append("默认使用正式层级序号组织正文；除非用户明确要求只写单段摘要，否则至少出现一个正式层级序号“一、”。")
        constraints.append("只要正文包含多个板块、多个长段落、表格或并列清单，必须继续使用“（一）”“1.”“（1）”展开，不得输出无序号散文式正文。")

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

    @classmethod
    def _formal_heading_count(cls, text: str) -> int:
        return len(cls._FORMAL_HEADING_LINE_RE.findall(text))

    @classmethod
    def _disallowed_paragraph_transition_count(cls, text: str) -> int:
        return len(cls._DISALLOWED_PARAGRAPH_TRANSITION_RE.findall(text))

    @classmethod
    def _markdown_heading_count(cls, text: str) -> int:
        return len(cls._MARKDOWN_HEADING_RE.findall(text))

    @classmethod
    def _markdown_table_count(cls, text: str) -> int:
        lines = text.splitlines()
        count = 0
        index = 0
        while index < len(lines) - 1:
            if not cls._MARKDOWN_TABLE_LINE_RE.match(lines[index]):
                index += 1
                continue
            if not cls._MARKDOWN_TABLE_ALIGN_RE.match(lines[index + 1]):
                index += 1
                continue
            count += 1
            index += 2
            while index < len(lines) and cls._MARKDOWN_TABLE_LINE_RE.match(lines[index]):
                index += 1
        return count

    @classmethod
    def _contains_summary_heading(cls, text: str) -> bool:
        return bool(cls._SUMMARY_HEADING_RE.search(text))

    def _required_min_table_count(self) -> int:
        max_tables = self.config.prompt_max_tables_per_section
        return 1 if max_tables > 0 else 0

    def _requires_formal_hierarchy(self, text: str) -> bool:
        """
        判断正文是否已经形成明显的多段/多块结构，若是则要求使用正式层级序号。

        这不是在要求所有正文都必须编号，而是避免长篇多段正文“看起来已分层，
        但完全没有一、（一）1.（1）”的情况漏过后处理。
        """
        stripped = text.strip()
        if not stripped:
            return False

        paragraph_count = len([part for part in self._SECTION_STYLE_SPLIT_RE.split(stripped) if part.strip()])
        table_count = self._markdown_table_count(stripped)
        line_count = len([line for line in stripped.splitlines() if line.strip()])

        if len(stripped) >= 1800 and paragraph_count >= 4:
            return True
        if len(stripped) >= 1200 and paragraph_count >= 3 and table_count >= 1:
            return True
        return len(stripped) >= 2500 and line_count >= 8

    def _build_summary_rule_text(self) -> str:
        summary_title = self.config.prompt_summary_title.strip()
        if summary_title:
            return f"如需章节收束，文末总结标题统一使用“{summary_title}”，并与前文编号衔接。"
        return "不另设总结或小结。"

    def _build_table_rule_text(self) -> str:
        max_tables = self.config.prompt_max_tables_per_section
        min_tables = self._required_min_table_count()
        if max_tables <= 0:
            return "不输出Markdown表格。"
        if min_tables == max_tables:
            return f"插入 {max_tables} 个Markdown表格，用于概括关键信息，表格标题前不加序号。"
        return f"插入 {min_tables} 至 {max_tables} 个Markdown表格，用于概括关键信息，表格标题前不加序号。"

    def _build_english_rule_text(self) -> str:
        if self.config.prompt_allow_english_terms:
            return "可保留必要英文术语或专有名词，但不要堆砌中英混杂表达。"
        return "除专有名词或用户明确要求外，不要输出不必要的英文、英文缩写或中英对照。"

    def _build_structure_contract_section(self) -> str:
        return "\n".join(
            [
                "## 结构输出硬要求",
                "- 本次正文默认采用显式层级结构，不接受整篇无序号散文式表达。",
                "- 除非用户明确要求只写单段摘要，否则正文至少出现一个正式层级序号“一、”。",
                "- 只要正文存在两个及以上功能板块、三个及以上自然段、表格、清单、流程、机制或并列措施，必须继续使用“（一）”“1.”“（1）”展开。",
                "- 序号后如带标题，该行只写“序号 + 标题”，下一行另起正文。",
                "- 表格前的引导性标题、板块标题或小标题，同样必须纳入正式层级序号体系，不得裸写。",
                "- 段内枚举可使用“第一……、第二……”或“一是……；二是……”，但不能替代章节层级序号。",
            ]
        )

    def _build_extra_rules_section(self) -> str:
        rules = self.config.prompt_extra_rules
        if not rules:
            return ""
        return "\n".join(
            [
                "## 其他写作要求",
                *[f"- {rule}" for rule in rules],
            ]
        )

    def _normalize_bidder_references(self, text: str) -> tuple[str, int]:
        bidder_name = self.config.prompt_bidder_name.strip()
        if not bidder_name or not text.strip():
            return text, 0

        normalized = text
        replacements = 0
        for alias in ("我方", "我司", "本公司", "本单位"):
            normalized, count = re.subn(re.escape(alias), bidder_name, normalized)
            replacements += count
        return normalized, replacements

    def _collect_output_issues(self, text: str) -> list[str]:
        if not text.strip():
            return []

        issues: list[str] = []
        if self._disallowed_paragraph_transition_count(text) >= 1:
            issues.append("numbering_transitions")
        if self._requires_formal_hierarchy(text) and self._formal_heading_count(text) == 0:
            issues.append("missing_formal_hierarchy")
        if not self.config.prompt_allow_markdown_headings and self._markdown_heading_count(text) >= 1:
            issues.append("markdown_headings")

        if not self.config.prompt_summary_title.strip() and self._contains_summary_heading(text):
            issues.append("forbidden_summary")
        return issues

    def _finalize_generated_content(self, heading: HeadingNode, content: str) -> FinalizeResult:
        del heading  # 不再进行二次大模型格式修复，仅保留轻量规范化与问题检测。
        normalized_content, replacement_count = self._normalize_bidder_references(content)
        issues = self._collect_output_issues(normalized_content)

        return FinalizeResult(
            content=normalized_content,
            postprocess={
                "bidder_reference_normalized": replacement_count > 0,
                "bidder_reference_replacements": replacement_count,
                "format_repair_applied": False,
                "format_repair_issues": issues,
            },
        )

    # 流式生成后后处理改变了内容时，通过此标记通知调用方替换显示内容
    STREAM_REPLACE_SENTINEL = "\x00\x01__replaced__\x00\x01"
    STREAM_STATUS_SENTINEL = "\x00\x01__status__\x00\x01"

    @classmethod
    def make_stream_status(cls, message: str) -> str:
        return cls.STREAM_STATUS_SENTINEL + message

    @staticmethod
    def _finalize_trace_session_async(
        trace_session: Optional[GenerationTraceSession],
        output_text: str,
        status: str = "completed",
        error: str = "",
        postprocess: Optional[dict[str, Any]] = None,
    ) -> None:
        if trace_session is None or trace_session.finished:
            return

        def worker() -> None:
            try:
                trace_session.finalize(
                    output_text,
                    status=status,
                    error=error,
                    postprocess=postprocess,
                )
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _iter_text_chunks(text: str, chunk_size: int = 1200) -> Generator[str, None, None]:
        for index in range(0, len(text), chunk_size):
            yield text[index:index + chunk_size]

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

    @staticmethod
    def _dedupe_values(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _build_prompt_contract_block(
        self,
        section_map: dict[str, str],
        block_id: str,
        label: str,
        prompt_kind: str,
        candidate_section_names: list[str],
        source_context: list[str],
        chars_override: Optional[int] = None,
    ) -> dict[str, Any]:
        section_names = [name for name in candidate_section_names if name in section_map]
        chars = chars_override if chars_override is not None else sum(len(section_map[name]) for name in section_names)
        return {
            "id": block_id,
            "label": label,
            "prompt_kind": prompt_kind,
            "section_names": section_names,
            "source_context": self._dedupe_values(source_context),
            "chars": chars,
        }

    def _build_prompt_contract_blocks(
        self,
        prompt_sections: list[dict[str, str]],
        pruned_context: Optional[ChapterContext],
        additional_requirements: str,
    ) -> list[dict[str, Any]]:
        section_map = {section["name"]: section["content"] for section in prompt_sections}
        system_prompt = self.build_system_prompt()

        block_specs: list[dict[str, Any]] = [
            {
                "id": "system_constraints",
                "label": "System Constraints",
                "prompt_kind": "system",
                "section_names": [],
                "source_context": [
                    "Config.role",
                    "prompt_bidder_name",
                    "prompt_allow_markdown_headings",
                    "prompt_allow_english_terms",
                    "prompt_hard_constraints",
                ],
                "chars_override": len(system_prompt),
            },
            {
                "id": "chapter_task",
                "label": "Chapter Task",
                "prompt_kind": "user",
                "section_names": ["task_card", "additional_requirements"],
                "source_context": [
                    "HeadingNode.title",
                    "HeadingNode.full_path",
                    "min_words",
                    "prompt.output_format",
                    "prompt_bidder_name",
                    "pruned_context.chapter_focus_terms" if pruned_context is not None else "HeadingNode.title",
                    "additional_requirements" if additional_requirements.strip() else "",
                ],
            },
            {
                "id": "structure_rules",
                "label": "Structure Rules",
                "prompt_kind": "user",
                "section_names": ["structure_contract", "first_line_rule", "extra_rules"],
                "source_context": [
                    "structure_contract",
                    "prompt.first_line_template" if "first_line_rule" in section_map else "",
                    "prompt.extra_rules" if "extra_rules" in section_map else "",
                ],
            },
            {
                "id": "chapter_scope",
                "label": "Chapter Scope",
                "prompt_kind": "user",
                "section_names": ["scope_reference", "full_outline"],
                "source_context": [
                    "context_mode",
                    "HeadingNode.parent",
                    "HeadingNode.title",
                    "HeadingNode.siblings",
                    "outline_file" if pruned_context is None else "",
                ],
            },
            {
                "id": "requirement_context",
                "label": "Requirement Context",
                "prompt_kind": "user",
                "section_names": ["requirement_brief", "requirement_points", "bid_requirements"],
                "source_context": [
                    "pruned_context.requirement_brief" if "requirement_brief" in section_map else "",
                    "pruned_context.requirement_seed" if "requirement_points" in section_map else "",
                    "Config.bid_requirements" if "bid_requirements" in section_map else "",
                ],
            },
            {
                "id": "scoring_context",
                "label": "Scoring Context",
                "prompt_kind": "user",
                "section_names": ["scoring_focus", "scoring_criteria"],
                "source_context": [
                    "pruned_context.scoring_items" if "scoring_focus" in section_map else "",
                    "pruned_context.response_labels" if "scoring_focus" in section_map else "",
                    "Config.scoring_criteria" if "scoring_criteria" in section_map else "",
                ],
            },
        ]

        blocks: list[dict[str, Any]] = []
        for block_id, label, prompt_kind in self._PROMPT_CONTRACT_BLOCKS:
            spec = next(spec for spec in block_specs if spec["id"] == block_id)
            blocks.append(
                self._build_prompt_contract_block(
                    section_map=section_map,
                    block_id=block_id,
                    label=label,
                    prompt_kind=prompt_kind,
                    candidate_section_names=spec["section_names"],
                    source_context=spec["source_context"],
                    chars_override=spec.get("chars_override"),
                )
            )
        return blocks

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
        self._append_prompt_section(
            prompt_parts,
            prompt_sections,
            "structure_contract",
            self._build_structure_contract_section(),
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
以下为从项目采购需求原文中摘取的当前章节相关内容，请优先围绕这些要求写作，并尽量贴合原文表述，不要把摘录重新概括成“必须覆盖”“硬约束”等元语言：
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

        extra_rules_section = self._build_extra_rules_section()
        if extra_rules_section:
            self._append_prompt_section(
                prompt_parts,
                prompt_sections,
                "extra_rules",
                extra_rules_section,
            )

        prompt = "\n".join(prompt_parts)
        if pruned_context is not None:
            self.context_pruner.dump_debug(heading, pruned_context, prompt)
        return PromptBuildResult(
            prompt=prompt,
            prompt_sections=prompt_sections,
            prompt_contract_blocks=self._build_prompt_contract_blocks(
                prompt_sections=prompt_sections,
                pruned_context=pruned_context,
                additional_requirements=additional_requirements,
            ),
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
        prepared = self.prepare_generation(
            heading,
            additional_requirements=additional_requirements,
            min_words=min_words,
            stream=stream,
        )
        raw_result = self.expand_raw(prepared)

        if stream:
            def wrapped_stream() -> Generator[str, None, None]:
                chunks: list[str] = []
                for token in raw_result:
                    chunks.append(token)
                    yield token

                raw_content = "".join(chunks)
                finalize_result = self.finalize_generation(
                    heading,
                    raw_content,
                    trace_session=prepared.trace_session,
                )
                final_content = finalize_result.content
                if final_content != raw_content:
                    yield self.STREAM_REPLACE_SENTINEL + final_content

            return wrapped_stream()

        raw_content = raw_result
        return self.finalize_generation(
            heading,
            raw_content,
            trace_session=prepared.trace_session,
        ).content

    def prepare_generation(
        self,
        heading: HeadingNode,
        additional_requirements: str = "",
        min_words: int = 500,
        stream: bool = True,
    ) -> PreparedGeneration:
        """准备模型请求和 trace 会话，但不执行正文后处理。"""
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
            prompt_contract_blocks=prompt_result.prompt_contract_blocks,
            context_mode=prompt_result.context_mode,
            pruned_context=prompt_result.pruned_context,
            full_context_stats=prompt_result.full_context_stats,
            request_options=request_options,
        )

        return PreparedGeneration(
            request_options=request_options,
            heading_title=heading.title,
            heading_full_path=heading.full_path,
            trace_id=trace_session.trace_id if trace_session is not None else "",
            trace_session=trace_session,
            stream=stream,
        )

    def expand_raw(self, prepared: PreparedGeneration) -> Generator[str, None, None] | str:
        """只执行模型生成，不做正文后处理。"""
        if prepared.stream:
            return self._stream_expand_raw(
                prepared.request_options,
                prepared.trace_session,
                heading_title=prepared.heading_title,
                heading_full_path=prepared.heading_full_path,
                trace_id=prepared.trace_id,
            )
        return self._sync_expand_raw(prepared.request_options, prepared.trace_session)

    def finalize_generation(
        self,
        heading: HeadingNode,
        raw_content: str,
        trace_session: Optional[GenerationTraceSession] = None,
    ) -> FinalizeResult:
        """对原始正文执行后处理，并异步完成 trace 落盘。"""
        write_timing_log(
            "finalize_generation_started",
            heading_title=heading.title,
            heading_full_path=heading.full_path,
            trace_id=trace_session.trace_id if trace_session is not None else "",
            raw_chars=len(raw_content),
        )
        finalize_result = self._finalize_generated_content(heading, raw_content)
        write_timing_log(
            "finalize_generation_finished",
            heading_title=heading.title,
            heading_full_path=heading.full_path,
            trace_id=trace_session.trace_id if trace_session is not None else "",
            raw_chars=len(raw_content),
            final_chars=len(finalize_result.content),
            format_repair_applied=bool(finalize_result.postprocess.get("format_repair_applied")),
            format_repair_issues=finalize_result.postprocess.get("format_repair_issues") or [],
        )
        if trace_session is not None and not trace_session.finished:
            self._finalize_trace_session_async(
                trace_session,
                finalize_result.content,
                status="completed",
                postprocess=finalize_result.postprocess,
            )
        return finalize_result

    def _stream_expand_raw(
        self,
        request_options: dict,
        trace_session: Optional[GenerationTraceSession] = None,
        heading_title: str = "",
        heading_full_path: str = "",
        trace_id: str = "",
    ) -> Generator[str, None, None]:
        """流式扩写：逐 token 立即 yield，仅返回原始正文。"""
        chunks: list[str] = []
        response = None
        finish_reason = ""
        last_token_at = ""
        idle_timeout_seconds = max(3, self.config.generation_stream_idle_timeout_seconds)
        close_requested = threading.Event()
        event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        def _close_response() -> None:
            close = getattr(response, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

        def _reader() -> None:
            try:
                assert response is not None
                for chunk in response:
                    if close_requested.is_set():
                        return
                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    token = choice.delta.content or ""
                    if token:
                        event_queue.put(("token", token))

                    if choice.finish_reason:
                        event_queue.put(("finish", str(choice.finish_reason)))
                        return

                event_queue.put(("end", "iterator_exhausted"))
            except Exception as exc:
                if close_requested.is_set():
                    event_queue.put(("end", "closed_after_idle_timeout"))
                else:
                    event_queue.put(("error", exc))

        try:
            response = self.client.chat.completions.create(**request_options)
            reader = threading.Thread(target=_reader, name="llm-stream-reader", daemon=True)
            reader.start()

            while True:
                wait_timeout = idle_timeout_seconds if chunks else max(idle_timeout_seconds, self.config.api_timeout_seconds)
                try:
                    event_type, payload = event_queue.get(timeout=wait_timeout)
                except queue.Empty:
                    if chunks:
                        finish_reason = f"idle_timeout_after_last_token_{idle_timeout_seconds}s"
                        write_timing_log(
                            "stream_idle_timeout_close",
                            heading_title=heading_title,
                            heading_full_path=heading_full_path,
                            trace_id=trace_id or (trace_session.trace_id if trace_session is not None else ""),
                            output_chars=len("".join(chunks)),
                            last_token_at=last_token_at,
                            idle_timeout_seconds=idle_timeout_seconds,
                        )
                        close_requested.set()
                        _close_response()
                        break
                    raise TimeoutError(
                        f"流式输出在 {wait_timeout} 秒内未收到任何内容，已中止本次生成。"
                    )

                if event_type == "token":
                    token = str(payload)
                    chunks.append(token)
                    last_token_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
                    yield token
                    continue

                if event_type == "finish":
                    finish_reason = str(payload)
                    break

                if event_type == "end":
                    finish_reason = str(payload)
                    break

                if event_type == "error":
                    raise payload
        except Exception as exc:
            write_timing_log(
                "stream_generation_error",
                heading_title=heading_title,
                heading_full_path=heading_full_path,
                trace_id=trace_id or (trace_session.trace_id if trace_session is not None else ""),
                output_chars=len("".join(chunks)),
                last_token_at=last_token_at,
                finish_reason=finish_reason,
                error=str(exc),
            )
            if trace_session is not None:
                trace_session.finalize("".join(chunks), status="failed", error=str(exc))
            raise
        finally:
            write_timing_log(
                "stream_last_token_received",
                heading_title=heading_title,
                heading_full_path=heading_full_path,
                trace_id=trace_id or (trace_session.trace_id if trace_session is not None else ""),
                output_chars=len("".join(chunks)),
                last_token_at=last_token_at,
                finish_reason=finish_reason,
            )
            close_requested.set()
            _close_response()

    def _sync_expand_raw(
        self,
        request_options: dict,
        trace_session: Optional[GenerationTraceSession] = None,
    ) -> str:
        """同步扩写，仅返回原始正文。"""
        try:
            response = self.client.chat.completions.create(**request_options)
            content = response.choices[0].message.content or ""
        except Exception as exc:
            if trace_session is not None:
                trace_session.finalize("", status="failed", error=str(exc))
            raise

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
