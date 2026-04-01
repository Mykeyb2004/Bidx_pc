"""
配置管理模块
负责加载和管理系统配置
"""

import os
from pathlib import Path
from typing import Any, Optional
import yaml


class Config:
    """系统配置管理器"""

    _MISSING = object()

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._config = {}
        self.load()

    def _parse_dotenv_line(self, line: str) -> Optional[tuple[str, str]]:
        """解析 `.env` 风格的单行配置。"""
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return None

        if stripped.startswith("export "):
            stripped = stripped[len("export "):].strip()

        if "=" not in stripped:
            return None

        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            return None

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        return key, value

    def _load_dotenv_file(self, dotenv_path: Path, protected_keys: set[str]) -> None:
        """从 `.env` 文件加载环境变量，不覆盖外部已显式设置的值。"""
        if not dotenv_path.exists() or not dotenv_path.is_file():
            return

        try:
            lines = dotenv_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return

        for line in lines:
            parsed = self._parse_dotenv_line(line)
            if not parsed:
                continue
            key, value = parsed
            if key in protected_keys:
                continue
            os.environ[key] = value

    def _load_local_env(self) -> None:
        """按项目配置目录优先加载 `.env` / `.env.local`。"""
        env_dir = self.config_path.parent.resolve()
        protected_keys = set(os.environ)
        for name in (".env", ".env.local"):
            self._load_dotenv_file(env_dir / name, protected_keys)

    def load(self) -> None:
        """加载配置文件"""
        self._load_local_env()
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f) or {}

    def reload(self) -> None:
        """重新加载配置"""
        self.load()

    def _get_value(self, *path: str, default: Any = _MISSING) -> Any:
        """获取嵌套配置值"""
        current = self._config
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    def _get_first_defined(self, *paths: tuple[str, ...] | str, default: Any = None) -> Any:
        """按优先级获取第一个已定义的配置值"""
        for path in paths:
            normalized = (path,) if isinstance(path, str) else path
            value = self._get_value(*normalized, default=self._MISSING)
            if value is not self._MISSING:
                return value
        return default

    def _get_bool(self, *paths: tuple[str, ...] | str, default: bool) -> bool:
        value = self._get_first_defined(*paths, default=default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _get_int(self, *paths: tuple[str, ...] | str, default: int) -> int:
        value = self._get_first_defined(*paths, default=default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _get_float(self, *paths: tuple[str, ...] | str, default: float) -> float:
        value = self._get_first_defined(*paths, default=default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _get_optional_int(self, *paths: tuple[str, ...] | str) -> Optional[int]:
        value = self._get_first_defined(*paths, default=None)
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _get_optional_float(self, *paths: tuple[str, ...] | str) -> Optional[float]:
        value = self._get_first_defined(*paths, default=None)
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _get_string_list(self, *paths: tuple[str, ...] | str, default: Optional[list[str]] = None) -> list[str]:
        """读取字符串列表配置，兼容单个字符串。"""
        value = self._get_first_defined(*paths, default=default or [])
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _get_env_str(self, key: str) -> Optional[str]:
        """读取环境变量字符串，空串按未设置处理。"""
        value = os.environ.get(key)
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    def _get_env_int(self, key: str) -> Optional[int]:
        """读取环境变量整数，非法值按未设置处理。"""
        value = self._get_env_str(key)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _get_env_float(self, key: str) -> Optional[float]:
        """读取环境变量浮点数，非法值按未设置处理。"""
        value = self._get_env_str(key)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _resolve_path(self, path_value: str) -> Path:
        """将相对路径解析为相对于配置文件目录的路径"""
        path = Path(path_value).expanduser()
        if not path.is_absolute():
            path = self.config_path.parent / path
        return path

    def _read_text_file(self, path_value: str) -> str:
        path = self._resolve_path(path_value)
        if path.exists():
            return path.read_text(encoding='utf-8')
        return ""

    def _looks_like_path(self, value: str) -> bool:
        """粗略判断字符串是否像文件路径，避免误把普通正文当路径处理。"""
        normalized = value.strip()
        if not normalized:
            return False
        if normalized.startswith(("~", "/", "./", "../")):
            return True
        if "/" in normalized or "\\" in normalized:
            return True
        if len(normalized) >= 2 and normalized[1] == ":":
            return True
        return bool(Path(normalized).suffix)

    def _extract_inline_file_path(self, inline_value: str) -> Optional[str]:
        """从 inline 文本中提取唯一的有效路径行，兼容多行块中的注释和引号。"""
        candidates = []
        for raw_line in inline_value.splitlines():
            trimmed = raw_line.strip()
            if not trimmed or trimmed.startswith('#'):
                continue
            if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {"'", '"'}:
                trimmed = trimmed[1:-1].strip()
            if trimmed:
                candidates.append(trimmed)

        if len(candidates) != 1:
            return None

        candidate = candidates[0]
        if not self._looks_like_path(candidate):
            return None

        path = self._resolve_path(candidate)
        if path.exists() and path.is_file():
            return candidate
        return None

    def _get_text_or_file(
        self,
        inline_paths: list[tuple[str, ...] | str],
        file_paths: list[tuple[str, ...] | str]
    ) -> str:
        """优先从文件路径读取文本，否则直接返回配置中的文本"""
        file_value = self._get_first_defined(*file_paths, default="")
        if isinstance(file_value, str) and file_value.strip():
            text = self._read_text_file(file_value.strip())
            if text:
                return text

        inline_value = self._get_first_defined(*inline_paths, default="")
        if not inline_value:
            return ""

        if not isinstance(inline_value, str):
            return str(inline_value)

        # 兼容旧配置：内容字段中直接填文件路径，或多行块中仅保留“注释 + 路径”。
        inline_path = self._extract_inline_file_path(inline_value)
        if inline_path:
            text = self._read_text_file(inline_path)
            if text:
                return text

        return inline_value

    @property
    def api_base_url(self) -> str:
        """API基础URL"""
        env_value = os.environ.get('BID_WRITER_API_BASE_URL')
        if env_value:
            return env_value
        return self._get_first_defined(('api', 'base_url'), default='https://api.openai.com/v1')

    @property
    def api_key(self) -> str:
        """API密钥"""
        env_key = os.environ.get('BID_WRITER_API_KEY')
        if env_key:
            return env_key
        return self._get_first_defined(('api', 'api_key'), default='')

    @property
    def model(self) -> str:
        """模型名称"""
        env_value = os.environ.get('BID_WRITER_MODEL')
        if env_value:
            return env_value
        return self._get_first_defined(('api', 'model'), default='gpt-4')

    @property
    def temperature(self) -> float:
        """生成温度"""
        env_value = os.environ.get('BID_WRITER_TEMPERATURE')
        if env_value:
            try:
                return float(env_value)
            except ValueError:
                pass
        return self._get_float(('api', 'temperature'), default=0.7)

    @property
    def max_tokens(self) -> int:
        """最大token数"""
        env_value = os.environ.get('BID_WRITER_MAX_TOKENS')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        return self._get_int(('api', 'max_tokens'), default=8000)

    @property
    def api_timeout_seconds(self) -> int:
        """API超时时间（秒）"""
        env_value = os.environ.get('BID_WRITER_TIMEOUT_SECONDS')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        return self._get_int(('api', 'timeout_seconds'), default=120)

    @property
    def api_max_retries(self) -> int:
        """API最大重试次数"""
        env_value = os.environ.get('BID_WRITER_MAX_RETRIES')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        return self._get_int(('api', 'max_retries'), default=3)

    @property
    def api_top_p(self) -> Optional[float]:
        """采样 top_p，可选"""
        env_value = os.environ.get('BID_WRITER_TOP_P')
        if env_value:
            try:
                return float(env_value)
            except ValueError:
                return None
        return self._get_optional_float(('api', 'top_p'))

    @property
    def api_seed(self) -> Optional[int]:
        """随机种子，可选"""
        env_value = os.environ.get('BID_WRITER_SEED')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                return None
        return self._get_optional_int(('api', 'seed'))

    @property
    def role(self) -> str:
        """角色设定"""
        return self._get_first_defined('role', default='你是一位专业的标书撰写专家。')

    @property
    def bid_requirements(self) -> str:
        """招标需求"""
        return self._get_text_or_file(
            inline_paths=[('inputs', 'bid_requirements'), 'bid_requirements'],
            file_paths=[('inputs', 'bid_requirements_file'), 'bid_requirements_file']
        )

    @property
    def scoring_criteria(self) -> str:
        """评分标准"""
        return self._get_text_or_file(
            inline_paths=[('inputs', 'scoring_criteria'), 'scoring_criteria'],
            file_paths=[('inputs', 'scoring_criteria_file'), 'scoring_criteria_file']
        )

    @property
    def outline_file(self) -> str:
        """大纲文件路径"""
        value = self._get_first_defined(('inputs', 'outline_file'), 'outline_file', default='./outline.md')
        if isinstance(value, str):
            inline_path = self._extract_inline_file_path(value)
            if inline_path:
                return inline_path
            return value.strip()
        return str(value)

    @property
    def output_directory(self) -> str:
        """输出目录"""
        value = self._get_first_defined(('output', 'directory'), default='./output')
        return str(self._resolve_path(str(value).strip()))

    @property
    def output_prefix(self) -> str:
        """输出文件名前缀"""
        return self._get_first_defined(('output', 'prefix'), default='')

    @property
    def output_include_title_header(self) -> bool:
        """保存文件时是否添加标题头"""
        return self._get_bool(('output', 'include_title_header'), default=True)

    @property
    def output_overwrite_existing(self) -> bool:
        """保存文件时是否覆盖已有文件"""
        return self._get_bool(
            ('output', 'overwrite_existing'),
            ('generation', 'overwrite_existing'),
            default=True
        )

    @property
    def output_normalize_soft_line_breaks_on_merge(self) -> bool:
        """整合标书时是否归一化正文中的软回车"""
        return self._get_bool(
            ('output', 'normalize_soft_line_breaks_on_merge'),
            default=False
        )

    @property
    def output_filename_max_length(self) -> int:
        """输出文件名最大长度"""
        return self._get_int(('output', 'filename_max_length'), default=100)

    @property
    def output_empty_filename_fallback(self) -> str:
        """空文件名时的占位名称"""
        return self._get_first_defined(('output', 'empty_filename_fallback'), default='untitled')

    @property
    def generation_default_min_words(self) -> int:
        """默认最低字数"""
        return self._get_int(('generation', 'default_min_words'), 'default_min_words', default=500)

    @property
    def generation_min_words_min(self) -> int:
        """最低字数下限"""
        return self._get_int(('generation', 'min_words_min'), default=100)

    @property
    def generation_min_words_max(self) -> int:
        """最低字数上限"""
        return self._get_int(('generation', 'min_words_max'), default=15000)

    @property
    def generation_min_words_step(self) -> int:
        """最低字数步长"""
        return self._get_int(('generation', 'min_words_step'), default=100)

    @property
    def generation_stream(self) -> bool:
        """是否使用流式输出"""
        return self._get_bool(('generation', 'stream'), default=True)

    @property
    def generation_stream_idle_timeout_seconds(self) -> int:
        """流式输出在最后一个 token 后的静默收尾超时时间（秒）"""
        env_value = os.environ.get('BID_WRITER_STREAM_IDLE_TIMEOUT_SECONDS')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        return self._get_int(('generation', 'stream_idle_timeout_seconds'), default=12)

    @property
    def prompt_output_format(self) -> str:
        """输出格式说明"""
        return self._get_first_defined(('prompt', 'output_format'), default='Markdown格式')

    @property
    def prompt_first_line_template(self) -> str:
        """首行模板"""
        value = self._get_first_defined(('prompt', 'first_line_template'), default='')
        return str(value).strip() if value is not None else ''

    @property
    def prompt_allow_markdown_headings(self) -> bool:
        """是否允许输出 Markdown 标题符号"""
        return self._get_bool(('prompt', 'allow_markdown_headings'), default=False)

    @property
    def prompt_allow_english_terms(self) -> bool:
        """是否允许必要的英文术语"""
        return self._get_bool(('prompt', 'allow_english_terms'), default=False)

    @property
    def prompt_max_tables_per_section(self) -> int:
        """单节最大表格数"""
        return self._get_int(('prompt', 'max_tables_per_section'), default=4)

    @property
    def prompt_summary_title(self) -> str:
        """章节总结标题名称"""
        return self._get_first_defined(('prompt', 'summary_title'), default='章节小结')

    @property
    def prompt_bidder_name(self) -> str:
        """投标主体名称"""
        value = self._get_first_defined(('prompt', 'bidder_name'), default='')
        return str(value).strip() if value is not None else ''

    @property
    def prompt_hard_constraints(self) -> list[str]:
        """高优先级强约束"""
        return self._get_string_list(('prompt', 'hard_constraints'), default=[])

    @property
    def prompt_extra_rules(self) -> list[str]:
        """额外提示规则"""
        return self._get_string_list(('prompt', 'extra_rules'), default=[])

    @property
    def context_pruning_enabled(self) -> bool:
        """是否启用章节级上下文裁剪。"""
        return self._get_bool(('context_pruning', 'enabled'), default=False)

    @property
    def context_pruning_debug_dump(self) -> bool:
        """是否输出裁剪调试信息。"""
        return self._get_bool(('context_pruning', 'debug_dump'), default=False)

    @property
    def context_pruning_local_outline_include_ancestors(self) -> bool:
        """局部大纲是否保留祖先链。"""
        return self._get_bool(('context_pruning', 'local_outline', 'include_ancestors'), default=True)

    @property
    def context_pruning_local_outline_include_siblings(self) -> bool:
        """局部大纲是否保留同级标题。"""
        return self._get_bool(('context_pruning', 'local_outline', 'include_siblings'), default=True)

    @property
    def context_pruning_local_outline_max_siblings(self) -> int:
        """局部大纲最多保留的同级标题数。"""
        return self._get_int(('context_pruning', 'local_outline', 'max_siblings'), default=8)

    @property
    def context_pruning_scoring_enabled(self) -> bool:
        """是否启用评分项路由。"""
        return self._get_bool(('context_pruning', 'scoring', 'enabled'), default=True)

    @property
    def context_pruning_scoring_max_rows(self) -> int:
        """评分项路由最多保留的评分行数。"""
        return self._get_int(('context_pruning', 'scoring', 'max_rows'), default=4)

    @property
    def context_pruning_requirements_brief_enabled(self) -> bool:
        """是否启用需求摘要。"""
        return self._get_bool(('context_pruning', 'requirements_brief', 'enabled'), default=False)

    @property
    def context_pruning_requirements_brief_fallback(self) -> str:
        """需求摘要失败时的回退策略。"""
        value = self._get_first_defined(('context_pruning', 'requirements_brief', 'fallback'), default='rule_only')
        return str(value).strip() if value is not None else 'rule_only'

    @property
    def pruning_api_base_url(self) -> str:
        """章节裁剪辅助模型 API 地址，只从环境变量读取。"""
        return self._get_env_str('BID_WRITER_PRUNING_API_BASE_URL') or ''

    @property
    def pruning_api_key(self) -> str:
        """章节裁剪辅助模型 API Key，只从环境变量读取。"""
        return self._get_env_str('BID_WRITER_PRUNING_API_KEY') or ''

    @property
    def pruning_model(self) -> str:
        """章节裁剪辅助模型名称。"""
        return (
            self._get_env_str('BID_WRITER_PRUNING_MODEL')
            or str(self._get_first_defined(('context_pruning', 'api', 'model'), default='')).strip()
        )

    @property
    def pruning_temperature(self) -> float:
        """章节裁剪辅助模型温度。"""
        env_value = self._get_env_float('BID_WRITER_PRUNING_TEMPERATURE')
        if env_value is not None:
            return env_value
        return self._get_float(('context_pruning', 'api', 'temperature'), default=0.2)

    @property
    def pruning_max_tokens(self) -> int:
        """章节裁剪辅助模型最大 token 数。"""
        env_value = self._get_env_int('BID_WRITER_PRUNING_MAX_TOKENS')
        if env_value is not None:
            return env_value
        return self._get_int(('context_pruning', 'api', 'max_tokens'), default=1200)

    @property
    def pruning_timeout_seconds(self) -> int:
        """章节裁剪辅助模型超时时间。"""
        env_value = self._get_env_int('BID_WRITER_PRUNING_TIMEOUT_SECONDS')
        if env_value is not None:
            return env_value
        return self._get_int(('context_pruning', 'api', 'timeout_seconds'), default=60)

    @property
    def pruning_max_retries(self) -> int:
        """章节裁剪辅助模型最大重试次数。"""
        env_value = self._get_env_int('BID_WRITER_PRUNING_MAX_RETRIES')
        if env_value is not None:
            return env_value
        return self._get_int(('context_pruning', 'api', 'max_retries'), default=2)

    @property
    def pruning_top_p(self) -> Optional[float]:
        """章节裁剪辅助模型采样 top_p。"""
        env_value = self._get_env_float('BID_WRITER_PRUNING_TOP_P')
        if env_value is not None:
            return env_value
        return self._get_optional_float(('context_pruning', 'api', 'top_p'))

    @property
    def pruning_seed(self) -> Optional[int]:
        """章节裁剪辅助模型随机种子。"""
        env_value = self._get_env_int('BID_WRITER_PRUNING_SEED')
        if env_value is not None:
            return env_value
        return self._get_optional_int(('context_pruning', 'api', 'seed'))

    @property
    def pruning_api_is_configured(self) -> bool:
        """辅助模型调用所需关键配置是否齐全。"""
        return bool(self.pruning_api_base_url and self.pruning_api_key and self.pruning_model)

    @property
    def generation_trace_enabled(self) -> bool:
        """是否启用章节生成 trace。"""
        return self._get_bool(('generation_trace', 'enabled'), default=False)

    @property
    def generation_trace_mode(self) -> str:
        """章节生成 trace 模式。"""
        value = self._get_first_defined(('generation_trace', 'mode'), default='full')
        normalized = str(value).strip().lower() if value is not None else 'full'
        return normalized if normalized in {'basic', 'full'} else 'full'

    @property
    def generation_trace_directory(self) -> str:
        """章节生成 trace 输出目录。"""
        value = self._get_first_defined(('generation_trace', 'directory'), default='')
        if isinstance(value, str) and value.strip():
            return str(self._resolve_path(value.strip()))
        return str((Path(__file__).resolve().parent.parent / 'log' / 'generation_traces'))

    @property
    def generation_trace_write_prompt(self) -> bool:
        """是否写入 system/user prompt 原文。"""
        default = True
        return self._get_bool(('generation_trace', 'write_prompt'), default=default)

    @property
    def generation_trace_write_output(self) -> bool:
        """是否写入最终生成正文。"""
        default = True
        return self._get_bool(('generation_trace', 'write_output'), default=default)

    @property
    def generation_trace_write_context(self) -> bool:
        """是否写入上下文拼接和裁剪详情。"""
        default = self.generation_trace_mode == 'full'
        return self._get_bool(('generation_trace', 'write_context'), default=default)

    @property
    def generation_trace_write_summary(self) -> bool:
        """是否写入摘要文件。"""
        default = True
        return self._get_bool(('generation_trace', 'write_summary'), default=default)

    @property
    def generation_trace_redact_sensitive(self) -> bool:
        """是否脱敏敏感字段。"""
        return self._get_bool(('generation_trace', 'redact_sensitive'), default=True)

    def get_outline_content(self) -> str:
        """获取大纲内容"""
        outline_path = self._resolve_path(self.outline_file)
        if not outline_path.exists():
            raise FileNotFoundError(f"大纲文件不存在: {outline_path}")
        return outline_path.read_text(encoding='utf-8')
