"""
项目背景生成模块
对招标需求做一次性 LLM 摘要，缓存到本地文件。
"""

import hashlib
import threading
from pathlib import Path

from openai import OpenAI

from .config import Config


class ProjectBackgroundGenerator:
    """生成并缓存项目背景摘要。"""

    def __init__(self, config: Config):
        self.config = config
        self._lock = threading.Lock()

    def get_or_generate(self) -> str:
        """返回缓存的项目背景，若缓存未命中则调用 LLM 生成。"""
        requirements = self.config.bid_requirements.strip()
        if not requirements:
            return ""

        cache_path = self._cache_path(requirements)
        if cache_path.exists():
            try:
                return cache_path.read_text(encoding="utf-8").strip()
            except OSError:
                pass

        with self._lock:
            # double-check after acquiring lock
            if cache_path.exists():
                try:
                    return cache_path.read_text(encoding="utf-8").strip()
                except OSError:
                    pass

            background = self._compute_background(requirements)
            if background:
                self._write_cache(cache_path, background)
            return background

    def _cache_path(self, requirements: str) -> Path:
        max_chars = self.config.project_background_max_chars
        hash_input = f"{requirements}{max_chars}"
        hash_key = hashlib.sha1(hash_input.encode("utf-8")).hexdigest()[:16]
        return Path(self.config.project_background_cache_dir) / f"bg_{hash_key}.txt"

    @staticmethod
    def _write_cache(cache_path: Path, content: str) -> None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_suffix(".tmp")
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(cache_path)
        except OSError:
            pass

    def _compute_background(self, requirements: str) -> str:
        max_chars = self.config.project_background_max_chars
        prompt = self._build_prompt(requirements, max_chars)

        try:
            client, model = self._get_client_and_model()
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                max_tokens=max_chars * 2,
                messages=[
                    {
                        "role": "system",
                        "content": "你是招标文件分析助手，擅长提炼项目核心信息。",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            import sys
            print(f"[project_background] 项目背景生成失败（{type(exc).__name__}: {exc}）", file=sys.stderr)
            return ""

    def _get_client_and_model(self) -> tuple[OpenAI, str]:
        config = self.config
        if config.pruning_api_is_configured:
            client = OpenAI(
                base_url=config.pruning_api_base_url,
                api_key=config.pruning_api_key,
                timeout=config.pruning_timeout_seconds,
                max_retries=config.pruning_max_retries,
            )
            return client, config.pruning_model
        client = OpenAI(
            base_url=config.api_base_url,
            api_key=config.api_key,
            timeout=config.api_timeout_seconds,
            max_retries=config.api_max_retries,
        )
        return client, config.model

    @staticmethod
    def _build_prompt(requirements: str, max_chars: int) -> str:
        return (
            "请从以下招标文件采购需求中提炼项目背景摘要。\n"
            "要求：\n"
            f"- 结构化摘要，约 {max_chars} 字\n"
            "- 必须涵盖：项目核心目标、任务范围、主要交付物、关键质量要求\n"
            "- 不要添加原文之外的内容；直接输出摘要，不要引导语\n"
            "\n"
            "招标采购需求：\n"
            f"{requirements}"
        )
