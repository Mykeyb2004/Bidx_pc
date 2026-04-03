"""
向量召回所需的 embedding 缓存与查询。
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

from openai import OpenAI

from .config import Config
from .retrieval_models import SourceUnit


class EmbeddingStore:
    """管理 embedding 生成、缓存和相似度检索。"""

    def __init__(self, config: Config):
        self.config = config
        self.cache_dir = Path(config.embedding_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.client = OpenAI(
            base_url=self._normalize_base_url(config.embedding_api_base_url),
            api_key=config.embedding_api_key,
            timeout=config.api_timeout_seconds,
            max_retries=config.api_max_retries,
        )

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/embeddings"):
            normalized = normalized[: -len("/embeddings")]
        return normalized

    def build_document_embeddings(self, units: list[SourceUnit]) -> dict[str, list[float]]:
        payload = [
            {
                "unit_id": unit.unit_id,
                "text": self._document_text(unit),
            }
            for unit in units
        ]
        cache_path = self._cache_path(payload)
        if cache_path.exists():
            return self._read_cache(cache_path)

        vectors = self._embed_texts([item["text"] for item in payload])
        data = {item["unit_id"]: vector for item, vector in zip(payload, vectors)}
        self._write_cache(cache_path, data)
        return data

    def embed_query(self, query_text: str) -> list[float]:
        prefixed = f"{self.config.embedding_query_prefix}{query_text}".strip()
        return self._embed_texts([prefixed])[0]

    def search(
        self,
        query_embedding: list[float],
        document_embeddings: dict[str, list[float]],
        *,
        top_k: int,
    ) -> list[tuple[str, float]]:
        scored = [
            (unit_id, self._cosine_similarity(query_embedding, embedding))
            for unit_id, embedding in document_embeddings.items()
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:top_k]

    def _cache_path(self, payload: list[dict[str, str]]) -> Path:
        digest_source = json.dumps(
            {
                "model": self.config.embedding_model,
                "document_prefix": self.config.embedding_document_prefix,
                "items": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path) -> dict[str, list[float]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {key: [float(value) for value in vector] for key, vector in payload.items()}

    def _write_cache(self, path: Path, data: dict[str, list[float]]) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )

    def _embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        values = [text.strip() for text in texts if text and text.strip()]
        if not values:
            return []

        vectors: list[list[float]] = []
        batch_size = max(self.config.embedding_batch_size, 1)
        for start in range(0, len(values), batch_size):
            batch = values[start:start + batch_size]
            response = self.client.embeddings.create(
                model=self.config.embedding_model,
                input=batch,
            )
            vectors.extend([list(item.embedding) for item in response.data])
        return vectors

    def _document_text(self, unit: SourceUnit) -> str:
        parts = [
            self.config.embedding_document_prefix.strip(),
            unit.section_path.strip(),
            unit.title.strip(),
            unit.weight_text.strip(),
            unit.source_text.strip(),
        ]
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(l * r for l, r in zip(left, right))
        left_norm = math.sqrt(sum(l * l for l in left))
        right_norm = math.sqrt(sum(r * r for r in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)
