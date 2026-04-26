"""
知识库拼装器
负责读取用户手写知识文档，并渲染为 prompt section
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import Config
from .outline_parser import HeadingNode


@dataclass(frozen=True)
class KnowledgeDocument:
    """单个知识文档。"""

    title: str
    path: Path
    content: str


class KnowledgeAssembler:
    """将用户手写知识拼装为可注入 prompt 的上下文块。"""

    _SECTION_TITLE = "## 投标方知识库"
    _SECTION_INTRO = (
        "以下为投标方提供的知识文档。正文涉及相关内容时，必须与以下信息保持一致，"
        "不得编造相互矛盾的主体信息、团队信息或服务承诺。"
    )

    def __init__(self, config: Config):
        self.config = config

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
        if not documents:
            return ""

        blocks = [self._render_document_block(document) for document in documents]
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
