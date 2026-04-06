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

    def get_or_generate(self, heading: HeadingNode, scope_reference: str) -> str:
        """返回缓存的章节写作计划，若缓存未命中则调用 LLM 生成。"""
        requirements = self.config.bid_requirements.strip()
        scoring = self.config.scoring_criteria.strip()
        if not requirements and not scoring:
            return ""

        cache_path = self._cache_path(heading, requirements, scoring)
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

            plan = self._compute_plan(heading, scope_reference, requirements, scoring)
            if plan:
                self._write_cache(cache_path, plan)
            return plan

    def _cache_path(self, heading: HeadingNode, requirements: str, scoring: str) -> Path:
        max_chars = self.config.chapter_writing_plan_max_chars
        hash_input = f"{heading.full_path}\n{requirements}\n{scoring}\n{max_chars}"
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
        scope_reference: str,
        requirements: str,
        scoring: str,
    ) -> str:
        max_chars = self.config.chapter_writing_plan_max_chars
        prompt = self._build_prompt(heading, scope_reference, requirements, scoring, max_chars)

        try:
            client, model = self._get_client_and_model()
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                max_tokens=max_chars * 2,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是标书章节写作规划助手。你的任务不是直接写正文，而是先为当前章节拟定一个简明、可执行的写作计划。\n"
                            "要求：\n"
                            "- 紧扣当前章节边界，不扩写同级章节内容\n"
                            "- 重点响应与本章相关的评分标准和采购需求\n"
                            "- 只输出章节写作计划，不输出正文\n"
                            "- 不要复述大段原文，不要写解释性套话\n"
                            f"- 控制在 {max_chars} 字以内"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            content = (response.choices[0].message.content or "").strip()
            if len(content) > max_chars:
                content = content[:max_chars].rstrip()
            return content
        except Exception as exc:
            import sys
            print(f"[chapter_writing_plan] 章节写作计划生成失败（{type(exc).__name__}: {exc}）", file=sys.stderr)
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
    def _build_prompt(
        heading: HeadingNode,
        scope_reference: str,
        requirements: str,
        scoring: str,
        max_chars: int,
    ) -> str:
        return (
            "请根据以下信息，为当前章节拟定“章节写作计划”。\n\n"
            f"当前章节：{heading.title}\n"
            f"章节路径：{heading.full_path}\n\n"
            f"{scope_reference}\n\n"
            "项目采购需求全文：\n"
            f"{requirements or '（无）'}\n\n"
            "评分标准全文：\n"
            f"{scoring or '（无）'}\n\n"
            "输出要求：\n"
            "1. 只输出“章节写作计划”内容\n"
            "2. 用 4-6 条编号列出本章建议写作结构\n"
            "3. 每条说明应写清本段要回应的需求或评分关注\n"
            "4. 不写“根据以上内容”“综上所述”等说明性话术\n"
            f"5. 总长度控制在 {max_chars} 字以内"
        )
