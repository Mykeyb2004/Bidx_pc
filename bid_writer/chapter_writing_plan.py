"""
章节写作计划生成模块
在 full_context 模式下，为当前章节生成一个简短的写作计划并缓存到本地。
"""

import hashlib
import threading
from pathlib import Path

from openai import OpenAI

from .config import Config
from .outline_parser import HeadingNode


class ChapterWritingPlanGenerator:
    """生成并缓存章节写作计划。"""

    def __init__(self, config: Config):
        self.config = config
        self._lock = threading.Lock()
        self.client = OpenAI(
            base_url=config.api_base_url,
            api_key=config.api_key,
            timeout=config.api_timeout_seconds,
            max_retries=config.api_max_retries,
        )

    def get_or_generate(
        self,
        heading: HeadingNode,
        *,
        system_prompt: str,
        shared_prompt_prefix: str,
    ) -> str:
        """返回缓存的章节写作计划，若缓存未命中则调用 LLM 生成。"""
        if not shared_prompt_prefix.strip():
            return ""

        cache_path = self._cache_path(
            heading,
            system_prompt=system_prompt,
            shared_prompt_prefix=shared_prompt_prefix,
        )
        if cache_path.exists():
            try:
                return cache_path.read_text(encoding="utf-8").strip()
            except OSError:
                pass

        with self._lock:
            if cache_path.exists():
                try:
                    return cache_path.read_text(encoding="utf-8").strip()
                except OSError:
                    pass

            plan = self._compute_plan(
                heading,
                system_prompt=system_prompt,
                shared_prompt_prefix=shared_prompt_prefix,
            )
            if plan:
                self._write_cache(cache_path, plan)
            return plan

    def _cache_path(
        self,
        heading: HeadingNode,
        *,
        system_prompt: str,
        shared_prompt_prefix: str,
    ) -> Path:
        max_chars = self.config.chapter_writing_plan_max_chars
        hash_input = (
            f"{self.config.model}\n"
            f"{heading.full_path}\n"
            f"{system_prompt}\n"
            f"{shared_prompt_prefix}\n"
            f"{max_chars}"
        )
        hash_key = hashlib.sha1(hash_input.encode("utf-8")).hexdigest()[:16]
        return Path(self.config.chapter_writing_plan_cache_dir) / f"plan_{hash_key}.txt"

    @staticmethod
    def _write_cache(cache_path: Path, content: str) -> None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_suffix(".tmp")
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(cache_path)
        except OSError:
            pass

    def _compute_plan(
        self,
        heading: HeadingNode,
        *,
        system_prompt: str,
        shared_prompt_prefix: str,
    ) -> str:
        max_chars = self.config.chapter_writing_plan_max_chars
        prompt = self._build_prompt(
            heading,
            shared_prompt_prefix=shared_prompt_prefix,
            max_chars=max_chars,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                temperature=0,
                max_tokens=max_chars * 2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            content = (response.choices[0].message.content or "").strip()
            if len(content) > max_chars:
                content = content[:max_chars].rstrip()
            return content
        except Exception as exc:
            import sys

            print(
                f"[chapter_writing_plan] 章节写作计划生成失败（{type(exc).__name__}: {exc}）",
                file=sys.stderr,
            )
            return ""

    @staticmethod
    def _build_prompt(
        heading: HeadingNode,
        *,
        shared_prompt_prefix: str,
        max_chars: int,
    ) -> str:
        return (
            f"{shared_prompt_prefix}\n\n"
            "## 当前任务\n"
            "请先不要写正文，只输出当前章节的“章节写作计划”。\n"
            f"- 当前章节：{heading.title}\n"
            f"- 当前章节路径：{heading.full_path}\n\n"
            "输出要求：\n"
            "1. 只输出“章节写作计划”内容，不要输出正文\n"
            "2. 用 4-6 条编号列出本章建议写作结构\n"
            "3. 每条说明应写清本段要回应的需求或评分关注\n"
            "4. 重点服务于对应评分标准、项目采购背景与本章边界\n"
            "5. 不写“根据以上内容”“综上所述”等说明性话术\n"
            f"6. 总长度控制在 {max_chars} 字以内"
        )
