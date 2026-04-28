"""
H2 级项目背景生成与缓存。
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI

from .config import Config
from .embedding_store import EmbeddingStore
from .hybrid_retriever import HybridRetriever
from .llm_verifier import LLMVerifier
from .outline_parser import HeadingNode, OutlineParser
from .retrieval_models import RetrievedUnit
from .source_unit_parser import SourceUnitParser


PROMPT_VERSION = "h2-project-background-v1"


@dataclass
class H2ProjectBackgroundResult:
    """单个 H2 背景摘要及其证据元数据。"""

    h2_title: str
    h2_full_path: str
    summary: str
    evidence_unit_ids: list[str]
    evidence_blocks: list[str]
    source_hash: str
    subtree_hash: str
    cache_status: str
    fallback_reason: str = ""
    model: str = ""
    created_at: str = ""
    prompt_version: str = PROMPT_VERSION
    precomputed: bool = False

    def to_trace_payload(self) -> dict[str, Any]:
        """转换为 trace 中的 project_background payload。"""
        return {
            "scope": "h2",
            "h2_title": self.h2_title,
            "h2_full_path": self.h2_full_path,
            "summary_chars": len(self.summary),
            "evidence_unit_ids": list(self.evidence_unit_ids),
            "evidence_blocks": list(self.evidence_blocks),
            "evidence_count": len(self.evidence_blocks),
            "cache_status": self.cache_status,
            "fallback_reason": self.fallback_reason,
            "precomputed": self.precomputed,
        }


@dataclass
class H2ProjectBackgroundPrecomputeReport:
    """批量预生成报告。"""

    total_h2: int
    generated: int = 0
    cache_hits: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[H2ProjectBackgroundResult] = field(default_factory=list)


class H2ProjectBackgroundGenerator:
    """生成并缓存 auto 模式 H2 级项目背景。"""

    def __init__(self, config: Config):
        self.config = config
        self.source_unit_parser = SourceUnitParser()
        self.hybrid_retriever = HybridRetriever()
        self.embedding_store = EmbeddingStore(config) if config.embedding_is_configured else None
        self.llm_verifier = LLMVerifier(config) if config.pruning_api_is_configured else None
        self._lock = threading.Lock()

    @staticmethod
    def find_h2_ancestor(heading: HeadingNode) -> HeadingNode:
        """找到 heading 所属的 H2；找不到时回退到父节点或自身。"""
        current: Optional[HeadingNode] = heading
        while current is not None:
            if current.level == 2:
                return current
            current = current.parent
        return heading.parent if heading.parent is not None else heading

    @staticmethod
    def collect_h2_nodes(outline: OutlineParser | HeadingNode | list[HeadingNode]) -> list[HeadingNode]:
        """从解析后的大纲中收集所有 H2 节点。"""
        if isinstance(outline, OutlineParser):
            nodes = outline.get_all_headings()
        elif isinstance(outline, HeadingNode):
            nodes = []

            def visit(node: HeadingNode) -> None:
                nodes.append(node)
                for child in node.children:
                    visit(child)

            visit(outline)
        else:
            nodes = list(outline)
        return [node for node in nodes if node.level == 2]

    @staticmethod
    def _sha1(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def source_hash(self) -> str:
        return self._sha1(self.config.bid_requirements.strip())

    def subtree_hash(self, h2: HeadingNode) -> str:
        lines: list[str] = []

        def visit(node: HeadingNode) -> None:
            lines.append(f"{node.level}:{node.full_path}")
            for child in node.children:
                visit(child)

        visit(h2)
        return self._sha1("\n".join(lines))

    def retrieval_fingerprint(self) -> str:
        parts = [
            f"top_k_lexical={self.config.context_pruning_retrieval_top_k_lexical}",
            f"top_k_vector={self.config.context_pruning_retrieval_top_k_vector}",
            f"top_k_fused={self.config.context_pruning_retrieval_top_k_fused}",
            f"min_fused_score={self.config.context_pruning_retrieval_min_fused_score}",
            f"vector={self.config.context_pruning_retrieval_vector_enabled}",
            f"verify={self.config.context_pruning_rerank_or_verify_enabled}",
        ]
        return self._sha1("|".join(parts))[:16]

    def cache_key_for_h2(self, h2: HeadingNode) -> str:
        model = self._model_name()
        key_input = "|".join(
            [
                self.source_hash(),
                h2.full_path,
                self.subtree_hash(h2),
                str(self.config.project_background_max_chars),
                str(self.config.h2_project_background_max_evidence_blocks),
                str(self.config.h2_project_background_max_evidence_chars),
                self.retrieval_fingerprint(),
                PROMPT_VERSION,
                model,
            ]
        )
        return self._sha1(key_input)[:20]

    def cache_path_for_h2(self, h2: HeadingNode) -> Path:
        return Path(self.config.h2_project_background_cache_dir) / f"h2_{self.cache_key_for_h2(h2)}.json"

    def cache_path_for_result(self, result: H2ProjectBackgroundResult) -> Path:
        key_input = "|".join(
            [
                result.source_hash,
                result.h2_full_path,
                result.subtree_hash,
                str(self.config.project_background_max_chars),
                str(self.config.h2_project_background_max_evidence_blocks),
                str(self.config.h2_project_background_max_evidence_chars),
                self.retrieval_fingerprint(),
                result.prompt_version,
                result.model,
            ]
        )
        return Path(self.config.h2_project_background_cache_dir) / f"h2_{self._sha1(key_input)[:20]}.json"

    def build_result(
        self,
        *,
        h2: HeadingNode,
        summary: str,
        evidence_unit_ids: list[str],
        evidence_blocks: list[str],
        cache_status: str,
        fallback_reason: str = "",
        precomputed: bool = False,
    ) -> H2ProjectBackgroundResult:
        return H2ProjectBackgroundResult(
            h2_title=h2.title,
            h2_full_path=h2.full_path,
            summary=summary.strip(),
            evidence_unit_ids=list(evidence_unit_ids),
            evidence_blocks=list(evidence_blocks),
            source_hash=self.source_hash(),
            subtree_hash=self.subtree_hash(h2),
            cache_status=cache_status,
            fallback_reason=fallback_reason,
            model=self._model_name(),
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            precomputed=precomputed,
        )

    def read_cache(self, h2: HeadingNode) -> Optional[H2ProjectBackgroundResult]:
        cache_path = self.cache_path_for_h2(h2)
        try:
            if not cache_path.exists():
                return None
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            result = H2ProjectBackgroundResult(
                h2_title=str(data.get("h2_title") or h2.title),
                h2_full_path=str(data.get("h2_full_path") or h2.full_path),
                summary=str(data.get("summary") or "").strip(),
                evidence_unit_ids=[str(item) for item in data.get("evidence_unit_ids") or []],
                evidence_blocks=[str(item) for item in data.get("evidence_blocks") or []],
                source_hash=str(data.get("source_hash") or ""),
                subtree_hash=str(data.get("subtree_hash") or ""),
                cache_status="hit",
                fallback_reason=str(data.get("fallback_reason") or ""),
                model=str(data.get("model") or ""),
                created_at=str(data.get("created_at") or ""),
                prompt_version=str(data.get("prompt_version") or PROMPT_VERSION),
                precomputed=bool(data.get("precomputed", False)),
            )
            if not result.summary:
                return None
            return result
        except Exception:
            return None

    def write_cache(self, result: H2ProjectBackgroundResult) -> None:
        cache_path = self.cache_path_for_result(result)
        payload = asdict(result)
        payload["version"] = 1
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(cache_path)
        except OSError:
            pass

    def precompute_all(self, outline: OutlineParser | HeadingNode | list[HeadingNode]) -> H2ProjectBackgroundPrecomputeReport:
        """为大纲中全部 H2 预生成或复用项目背景。"""
        h2_nodes = self.collect_h2_nodes(outline)
        report = H2ProjectBackgroundPrecomputeReport(total_h2=len(h2_nodes))
        for h2 in h2_nodes:
            result = self.get_or_generate(h2, precomputed=True)
            report.results.append(result)
            if result.cache_status == "hit":
                report.cache_hits += 1
            elif result.cache_status == "generated":
                report.generated += 1
            elif result.cache_status == "fallback":
                if result.summary:
                    report.skipped += 1
                else:
                    report.failed += 1
            elif result.cache_status == "failed":
                report.failed += 1
        return report

    def get_for_heading(self, heading: HeadingNode) -> H2ProjectBackgroundResult:
        """读取当前章节所属 H2 背景，必要时按配置补生成或回退。"""
        h2 = self.find_h2_ancestor(heading)
        cached = self.read_cache(h2)
        if cached is not None:
            return cached
        if not self.config.h2_project_background_generate_missing_on_single:
            return self._fallback_result(h2, "缓存缺失且未启用单章节补生成")
        return self.get_or_generate(h2)

    def get_or_generate(self, h2: HeadingNode, *, precomputed: bool = False) -> H2ProjectBackgroundResult:
        """返回 H2 背景，缓存未命中时生成。"""
        cached = self.read_cache(h2)
        if cached is not None:
            cached.precomputed = precomputed or cached.precomputed
            return cached

        with self._lock:
            cached = self.read_cache(h2)
            if cached is not None:
                cached.precomputed = precomputed or cached.precomputed
                return cached

            try:
                evidence_hits = self.retrieve_evidence(h2)
                evidence_unit_ids = [hit.unit.unit_id for hit in evidence_hits]
                evidence_blocks = self._trim_evidence_blocks(
                    [hit.unit.source_text_exact or hit.unit.source_text for hit in evidence_hits]
                )
                if len(evidence_blocks) < self.config.h2_project_background_min_evidence_blocks:
                    return self._fallback_result(
                        h2,
                        f"证据片段不足：{len(evidence_blocks)} < {self.config.h2_project_background_min_evidence_blocks}",
                        evidence_unit_ids=evidence_unit_ids,
                        evidence_blocks=evidence_blocks,
                    )

                summary = self._compute_summary(h2, evidence_blocks)
                if not summary.strip():
                    return self._fallback_result(
                        h2,
                        "摘要生成为空",
                        evidence_unit_ids=evidence_unit_ids,
                        evidence_blocks=evidence_blocks,
                    )

                result = self.build_result(
                    h2=h2,
                    summary=summary,
                    evidence_unit_ids=evidence_unit_ids,
                    evidence_blocks=evidence_blocks,
                    cache_status="generated",
                    precomputed=precomputed,
                )
                self.write_cache(result)
                return result
            except Exception as exc:
                return self._fallback_result(h2, f"{type(exc).__name__}: {exc}")

    def retrieve_evidence(self, h2: HeadingNode) -> list[RetrievedUnit]:
        """检索当前 H2 相关的采购需求原文片段。"""
        text = self.config.bid_requirements.strip()
        if not text:
            return []
        units = self.source_unit_parser.parse_requirements(text)
        if not units:
            return []

        query_text = self.build_h2_query(h2)
        focus_terms = self._collect_h2_titles(h2)
        hits = self.hybrid_retriever.retrieve(
            query_text,
            units,
            response_labels=[h2.title],
            keywords=focus_terms,
            focus_terms=focus_terms,
            top_k_lexical=self.config.context_pruning_retrieval_top_k_lexical,
            top_k_vector=self.config.context_pruning_retrieval_top_k_vector,
            top_k_fused=self.config.context_pruning_retrieval_top_k_fused,
            embedding_store=self.embedding_store if self.config.context_pruning_retrieval_vector_enabled else None,
        )
        selected_hits = self.hybrid_retriever.select_final(
            hits,
            top_k_final=self.config.h2_project_background_max_evidence_blocks,
            min_score=self.config.context_pruning_retrieval_min_fused_score,
        )
        selected_hits = self._verify_hits_if_needed(h2, hits, selected_hits)
        if not selected_hits and units:
            selected_hits = [
                RetrievedUnit(unit=unit, lexical_score=0.0, fused_score=0.0)
                for unit in units[:1]
            ]
        return selected_hits

    def _verify_hits_if_needed(
        self,
        h2: HeadingNode,
        hits: list[RetrievedUnit],
        selected_hits: list[RetrievedUnit],
    ) -> list[RetrievedUnit]:
        if not hits or not self.config.context_pruning_rerank_or_verify_enabled:
            return selected_hits
        if self.llm_verifier is None:
            return selected_hits

        verify_candidates = hits[: self.config.context_pruning_extraction_llm_verify_max_candidates]
        result = self.llm_verifier.verify(
            heading_path=h2.full_path,
            heading_title=h2.title,
            response_labels=[h2.title],
            focus_terms=self._collect_h2_titles(h2),
            candidates=verify_candidates,
            limit=self.config.h2_project_background_max_evidence_blocks,
        )
        if not result.selected_ids:
            return selected_hits

        selected_map = {hit.unit.unit_id: hit for hit in verify_candidates}
        verified_hits: list[RetrievedUnit] = []
        for unit_id in result.selected_ids:
            hit = selected_map.get(unit_id)
            if hit is None:
                continue
            hit.rerank_score = max(hit.rerank_score, hit.fused_score)
            verified_hits.append(hit)
        return verified_hits or selected_hits

    def build_h2_query(self, h2: HeadingNode) -> str:
        """构造 H2 检索 query，融合标题路径与子树标题。"""
        child_titles = self._collect_h2_titles(h2, include_self=False)
        parts = [
            f"H2 标题：{h2.title}",
            f"H2 路径：{h2.full_path}",
            f"H2 子树标题：{'；'.join(child_titles)}",
            f"重点词：{'；'.join(self._collect_h2_titles(h2))}",
        ]
        return "\n".join(part for part in parts if part.strip())

    def _collect_h2_titles(self, h2: HeadingNode, *, include_self: bool = True, limit: int = 20) -> list[str]:
        titles: list[str] = []

        def add(title: str) -> None:
            normalized = title.strip()
            if normalized and normalized not in titles:
                titles.append(normalized)

        def visit(node: HeadingNode) -> None:
            if len(titles) >= limit:
                return
            if include_self or node is not h2:
                add(node.title)
            for child in node.children:
                visit(child)

        visit(h2)
        return titles[:limit]

    def _trim_evidence_blocks(self, blocks: list[str]) -> list[str]:
        max_total = max(self.config.h2_project_background_max_evidence_chars, 0)
        trimmed: list[str] = []
        used = 0
        for block in blocks[: self.config.h2_project_background_max_evidence_blocks]:
            text = block.strip()
            if not text:
                continue
            remaining = max_total - used if max_total else len(text)
            if remaining <= 0:
                break
            if len(text) > remaining:
                text = text[:remaining].rstrip()
            trimmed.append(text)
            used += len(text)
        return trimmed

    def _fallback_result(
        self,
        h2: HeadingNode,
        reason: str,
        *,
        evidence_unit_ids: Optional[list[str]] = None,
        evidence_blocks: Optional[list[str]] = None,
    ) -> H2ProjectBackgroundResult:
        fallback = self.config.h2_project_background_fallback
        blocks = evidence_blocks or []
        summary = ""
        if fallback == "raw_evidence" and blocks:
            summary = "\n\n".join(blocks[:3])
        elif fallback == "raw_evidence" and self.config.bid_requirements.strip():
            summary = self.config.bid_requirements.strip()[: self.config.project_background_max_chars]
            blocks = [summary]
        return self.build_result(
            h2=h2,
            summary=summary,
            evidence_unit_ids=evidence_unit_ids or [],
            evidence_blocks=blocks,
            cache_status="fallback",
            fallback_reason=reason,
        )

    def _compute_summary(self, h2: HeadingNode, evidence_blocks: list[str]) -> str:
        prompt = self._build_summary_prompt(h2, evidence_blocks)
        client, model = self._get_client_and_model()
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=self.config.project_background_max_chars * 2,
            messages=[
                {
                    "role": "system",
                    "content": "你是招标文件分析助手，只能依据给定原文片段提炼背景。",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def _build_summary_prompt(self, h2: HeadingNode, evidence_blocks: list[str]) -> str:
        evidence_text = "\n\n".join(f"[证据{i + 1}]\n{block}" for i, block in enumerate(evidence_blocks))
        return (
            "请仅基于给定采购需求原文片段，提炼当前 H2 章节的项目背景。\n\n"
            f"H2 标题：{h2.title}\n"
            f"H2 路径：{h2.full_path}\n"
            f"H2 子树标题：{'；'.join(self._collect_h2_titles(h2, include_self=False))}\n"
            f"输出长度：约 {self.config.project_background_max_chars} 字以内\n\n"
            "必须覆盖：\n"
            "1. 与本 H2 相关的项目目标或问题来源\n"
            "2. 与本 H2 相关的任务范围\n"
            "3. 与本 H2 相关的主要交付物或成果\n"
            "4. 与本 H2 相关的质量、合规、时限或验收要求\n"
            "5. 本 H2 下章节扩写时不可遗漏的关键信息\n\n"
            "限制：\n"
            "- 不得引入原文没有的信息。\n"
            "- 不要写成评分响应清单。\n"
            "- 不要覆盖其他 H2 的职责范围。\n"
            "- 如果证据片段不足以支持某项内容，省略该项，不要编造。\n"
            "- 直接输出摘要正文，不要输出引导语。\n\n"
            "采购需求原文片段：\n"
            f"{evidence_text}"
        )

    def _model_name(self) -> str:
        if self.config.pruning_api_is_configured:
            return self.config.pruning_model
        return self.config.model

    def _get_client_and_model(self) -> tuple[OpenAI, str]:
        if self.config.pruning_api_is_configured:
            client = OpenAI(
                base_url=self.config.pruning_api_base_url,
                api_key=self.config.pruning_api_key,
                timeout=self.config.pruning_timeout_seconds,
                max_retries=self.config.pruning_max_retries,
            )
            return client, self.config.pruning_model
        client = OpenAI(
            base_url=self.config.api_base_url,
            api_key=self.config.api_key,
            timeout=self.config.api_timeout_seconds,
            max_retries=self.config.api_max_retries,
        )
        return client, self.config.model
