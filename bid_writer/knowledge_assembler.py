"""
知识库拼装器
负责读取用户手写知识文档与依赖章节 facts，并渲染为 prompt section
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .chapter_dependency_store import ChapterDependencyStore
from .chapter_fact_store import ChapterFactStore, ExtractedFact
from .config import Config
from .file_saver import FileSaver
from .outline_parser import HeadingNode, parse_outline


@dataclass(frozen=True)
class KnowledgeDocument:
    """单个知识文档。"""

    title: str
    path: Path
    content: str


@dataclass(frozen=True)
class KnowledgeFact:
    scope: str
    category: str
    value: str
    sources: tuple[str, ...]


class KnowledgeAssembler:
    """将用户手写知识拼装为可注入 prompt 的上下文块。"""

    _SECTION_TITLE = "## 投标方知识库"
    _SECTION_INTRO = (
        "以下为投标方提供的知识文档。正文涉及相关内容时，必须与以下信息保持一致，"
        "不得编造相互矛盾的主体信息、团队信息或服务承诺。"
    )

    def __init__(self, config: Config):
        self.config = config
        self.dependency_store = ChapterDependencyStore(config)
        self.fact_store = ChapterFactStore(config)
        self.file_saver = FileSaver(
            config.output_directory,
            config.output_prefix,
            max_filename_length=config.output_filename_max_length,
            empty_filename_fallback=config.output_empty_filename_fallback,
            include_title_header=config.output_include_title_header,
            overwrite_existing=config.output_overwrite_existing,
        )
        self._parser = None

    def load_documents(self) -> list[KnowledgeDocument]:
        """按声明优先、目录补齐的顺序加载知识文档。"""
        if not self.config.knowledge_enabled:
            return []

        documents: list[KnowledgeDocument] = []
        seen: set[Path] = set()

        for path_value in self.config.knowledge_files:
            path = Path(path_value)
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            document = self._load_document(path)
            if document is None:
                continue
            seen.add(resolved)
            documents.append(document)

        directory_value = self.config.knowledge_directory
        if directory_value:
            directory = Path(directory_value)
            if directory.is_dir():
                for path in sorted(directory.glob("*.md"), key=lambda item: item.name):
                    resolved = path.resolve()
                    if resolved in seen or not path.is_file():
                        continue
                    document = self._load_document(path)
                    if document is None:
                        continue
                    seen.add(resolved)
                    documents.append(document)

        return documents

    def build_prompt_section(
        self,
        *,
        heading: Optional[HeadingNode] = None,
        focus_terms: Optional[list[str]] = None,
    ) -> str:
        """构建知识库 prompt section。"""
        documents = self.load_documents()
        facts = self._load_dependency_facts(heading, focus_terms or [])
        if not documents and not facts:
            return ""

        blocks = [self._render_document_block(document) for document in documents]
        if facts:
            blocks.extend(self._render_fact_blocks(facts))
        body = self._truncate_blocks(blocks, self.config.knowledge_max_chars)
        if not body:
            return ""

        return f"{self._SECTION_TITLE}\n{self._SECTION_INTRO}\n\n{body}"

    def _load_document(self, path: Path) -> Optional[KnowledgeDocument]:
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not content:
            return None
        title = path.stem.strip() or path.name
        return KnowledgeDocument(
            title=title,
            path=path,
            content=self._strip_redundant_heading(content, title),
        )

    @staticmethod
    def _strip_redundant_heading(content: str, title: str) -> str:
        lines = content.splitlines()
        if not lines:
            return content
        first_line = lines[0].strip()
        if first_line.startswith("#") and first_line.lstrip("#").strip() == title:
            return "\n".join(lines[1:]).strip()
        return content.strip()

    def _render_document_block(self, document: KnowledgeDocument) -> str:
        source = self._display_path(document.path)
        return (
            f"### {document.title}\n"
            f"{document.content}\n"
            f"（来源：{source}）"
        ).strip()

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.config.project_root_path))
        except ValueError:
            try:
                return str(path.resolve().relative_to(self.config.config_path.parent.resolve()))
            except ValueError:
                return str(path.resolve())

    def _get_parser(self):
        if self._parser is not None:
            return self._parser
        try:
            self._parser = parse_outline(self.config.get_outline_content())
        except Exception:
            self._parser = False
        return self._parser

    def _load_dependency_facts(
        self,
        heading: Optional[HeadingNode],
        focus_terms: list[str],
    ) -> list[KnowledgeFact]:
        if heading is None:
            return []

        parser = self._get_parser()
        if not parser:
            return []

        facts: list[KnowledgeFact] = []
        for dependency_path in self.dependency_store.list_dependency_paths(heading):
            dependency = parser.find_heading_by_full_path(dependency_path)
            if dependency is None:
                continue
            record = self.fact_store.get(dependency)
            if record is None or not record.facts:
                continue
            if record.source_hash != self._current_output_hash(dependency):
                continue
            for fact in record.facts:
                facts.append(
                    KnowledgeFact(
                        scope=fact.scope,
                        category=fact.category,
                        value=fact.value,
                        sources=(record.title or dependency.title,),
                    )
                )
        return self._merge_facts(self._filter_relevant_facts(facts, focus_terms))

    def _current_output_hash(self, heading: HeadingNode) -> str:
        filepath = self.file_saver.find_existing_filepath(heading)
        if filepath is None or not filepath.exists():
            return ""
        content = self.file_saver.load_section_body(filepath, heading.title).strip()
        if not content:
            return ""
        digest = hashlib.sha1(content.encode("utf-8")).hexdigest()
        return f"output:{digest}"

    @staticmethod
    def _normalize_fact_text(text: str) -> str:
        return "".join(text.split()).lower()

    def _filter_relevant_facts(
        self,
        facts: list[KnowledgeFact],
        focus_terms: list[str],
    ) -> list[KnowledgeFact]:
        normalized_terms = [
            self._normalize_fact_text(term)
            for term in focus_terms
            if self._normalize_fact_text(term)
        ]
        result: list[KnowledgeFact] = []
        for fact in facts:
            if fact.scope == "global":
                result.append(fact)
                continue
            haystack = self._normalize_fact_text(f"{fact.category}{fact.value}")
            if any(term in haystack for term in normalized_terms):
                result.append(fact)
        return result

    def _merge_facts(self, facts: list[KnowledgeFact]) -> list[KnowledgeFact]:
        merged: dict[tuple[str, str, str], KnowledgeFact] = {}
        order: list[tuple[str, str, str]] = []
        for fact in facts:
            key = (
                fact.scope,
                self._normalize_fact_text(fact.category),
                self._normalize_fact_text(fact.value),
            )
            if key not in merged:
                merged[key] = fact
                order.append(key)
                continue
            existing = merged[key]
            merged[key] = KnowledgeFact(
                scope=existing.scope,
                category=existing.category,
                value=existing.value,
                sources=tuple(dict.fromkeys([*existing.sources, *fact.sources])),
            )
        return [merged[key] for key in order]

    def _render_fact_blocks(self, facts: list[KnowledgeFact]) -> list[str]:
        blocks = ["### 已确立事实"]
        global_facts = [fact for fact in facts if fact.scope == "global"]
        local_facts = [fact for fact in facts if fact.scope != "global"]
        blocks.extend(self._render_fact_block(fact) for fact in global_facts)
        blocks.extend(self._render_fact_block(fact) for fact in local_facts)
        return blocks

    @staticmethod
    def _render_fact_block(fact: KnowledgeFact) -> str:
        source_label = "、".join(fact.sources)
        return f"- {fact.category}: {fact.value} [来源: {source_label}]"

    @staticmethod
    def _truncate_block(block: str, limit: int) -> str:
        if limit <= 0:
            return ""
        if len(block) <= limit:
            return block

        kept: list[str] = []
        for line in block.splitlines():
            candidate = "\n".join(kept + [line]).strip()
            if len(candidate) <= limit:
                kept.append(line)
                continue
            if not kept:
                return line[:limit].rstrip()
            break
        return "\n".join(kept).strip()

    def _truncate_blocks(self, blocks: list[str], limit: int) -> str:
        if limit <= 0:
            return ""

        kept_blocks: list[str] = []
        remaining = limit

        for block in blocks:
            separator = 0 if not kept_blocks else 2
            required = len(block) + separator
            if required <= remaining:
                kept_blocks.append(block)
                remaining -= required
                continue

            if not kept_blocks:
                truncated = self._truncate_block(block, remaining - separator)
                if truncated:
                    kept_blocks.append(truncated)
            break

        return "\n\n".join(item for item in kept_blocks if item.strip()).strip()
