"""
配置管理模块
负责加载和管理系统配置
"""

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
import yaml


@dataclass(frozen=True)
class TargetWordRange:
    """章节目标篇幅区间。"""

    baseline: int
    lower: int
    upper: int

    @property
    def display_text(self) -> str:
        return f"{self.lower}-{self.upper}"

    def to_dict(self) -> dict[str, int]:
        return {
            "baseline": self.baseline,
            "lower": self.lower,
            "upper": self.upper,
        }


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

    def _resolve_with_base(self, path_value: str, base_dir: Path) -> Path:
        """将相对路径解析为相对于给定基目录的路径。"""
        path = Path(path_value).expanduser()
        if not path.is_absolute():
            path = base_dir / path
        return path

    def _resolve_path(self, path_value: str) -> Path:
        """将相对路径解析为相对于配置文件目录的路径。"""
        return self._resolve_with_base(path_value, self.config_path.parent.resolve())

    @property
    def project_root_path(self) -> Path:
        """项目根目录；未配置时回退到配置文件所在目录。"""
        value = self._get_first_defined(('project', 'root_dir'), default="")
        if isinstance(value, str) and value.strip():
            return self._resolve_path(value.strip())
        return self.config_path.parent.resolve()

    def _resolve_project_path(self, path_value: str) -> Path:
        """将相对路径解析为相对于项目根目录的路径。"""
        return self._resolve_with_base(path_value, self.project_root_path)

    def _read_text_file(
        self,
        path_value: str,
        *,
        resolver: Optional[Callable[[str], Path]] = None,
    ) -> str:
        path = (resolver or self._resolve_path)(path_value)
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

    def _extract_inline_file_path(
        self,
        inline_value: str,
        *,
        resolver: Optional[Callable[[str], Path]] = None,
    ) -> Optional[str]:
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

        path = (resolver or self._resolve_path)(candidate)
        if path.exists() and path.is_file():
            return candidate
        return None

    def _get_text_or_file(
        self,
        inline_paths: list[tuple[str, ...] | str],
        file_paths: list[tuple[str, ...] | str],
        *,
        resolver: Optional[Callable[[str], Path]] = None,
    ) -> str:
        """优先从文件路径读取文本，否则直接返回配置中的文本"""
        file_value = self._get_first_defined(*file_paths, default="")
        if isinstance(file_value, str) and file_value.strip():
            text = self._read_text_file(file_value.strip(), resolver=resolver)
            if text:
                return text

        inline_value = self._get_first_defined(*inline_paths, default="")
        if not inline_value:
            return ""

        if not isinstance(inline_value, str):
            return str(inline_value)

        # 兼容旧配置：内容字段中直接填文件路径，或多行块中仅保留“注释 + 路径”。
        inline_path = self._extract_inline_file_path(inline_value, resolver=resolver)
        if inline_path:
            text = self._read_text_file(inline_path, resolver=resolver)
            if text:
                return text

        return inline_value

    def _resolve_declared_path(
        self,
        value: Any,
        *,
        resolver: Optional[Callable[[str], Path]] = None,
        default: str = "",
    ) -> str:
        """把声明式路径字段解析成绝对路径字符串。"""
        resolve = resolver or self._resolve_path
        if value is None:
            return default
        if isinstance(value, str):
            inline_path = self._extract_inline_file_path(value, resolver=resolve)
            candidate = inline_path or value.strip()
            if not candidate:
                return default
            return str(resolve(candidate))
        normalized = str(value).strip()
        if not normalized:
            return default
        return str(resolve(normalized))

    @staticmethod
    def _normalize_mode(value: Any, *, default: str = 'legacy_rule') -> str:
        normalized = str(value).strip().lower() if value is not None else default
        return normalized if normalized in {'legacy_rule', 'hybrid_extract'} else default

    @staticmethod
    def _normalize_processing_path_value(value: Any, *, default: str = 'full_context') -> str:
        normalized = str(value).strip().lower() if value is not None else default
        return normalized if normalized in {'full_context', 'legacy_rule', 'hybrid_extract', 'auto'} else default

    def _legacy_context_pruning_enabled(self) -> bool:
        return self._get_bool(('context_pruning', 'enabled'), default=False)

    def _legacy_context_pruning_base_mode(self) -> str:
        value = self._get_first_defined(('context_pruning', 'mode'), default='legacy_rule')
        return self._normalize_mode(value)

    def _legacy_context_pruning_scoring_mode(self) -> str:
        value = self._get_first_defined(
            ('context_pruning', 'scoring', 'mode'),
            default=self._legacy_context_pruning_base_mode(),
        )
        return self._normalize_mode(value, default=self._legacy_context_pruning_base_mode())

    def _legacy_context_pruning_requirements_mode(self) -> str:
        value = self._get_first_defined(
            ('context_pruning', 'requirements', 'mode'),
            default=self._legacy_context_pruning_base_mode(),
        )
        return self._normalize_mode(value, default=self._legacy_context_pruning_base_mode())

    def _using_new_processing_schema(self) -> bool:
        return self._get_value('processing', 'path', default=self._MISSING) is not self._MISSING

    @property
    def processing_path(self) -> str:
        """当前项目的章节处理路径。"""
        configured = self._get_value('processing', 'path', default=self._MISSING)
        if configured is not self._MISSING:
            return self._normalize_processing_path_value(configured)

        if not self._legacy_context_pruning_enabled():
            return 'full_context'

        scoring_mode = self._legacy_context_pruning_scoring_mode()
        requirements_mode = self._legacy_context_pruning_requirements_mode()
        if scoring_mode == requirements_mode:
            return scoring_mode
        return 'mixed'

    def _get_processing_branch_value(self, *path: str, default: Any = _MISSING) -> Any:
        """按当前 processing.path 优先读取对应链路参数。"""
        processing_path = self.processing_path
        candidates: list[tuple[str, ...]] = []
        if processing_path in {'legacy_rule', 'hybrid_extract'}:
            candidates.append(('processing', processing_path, *path))
        for branch in ('legacy_rule', 'hybrid_extract'):
            branch_path = ('processing', branch, *path)
            if branch_path not in candidates:
                candidates.append(branch_path)
        return self._get_first_defined(*candidates, default=default)

    @property
    def api_base_url(self) -> str:
        """API基础URL"""
        env_value = os.environ.get('BID_WRITER_API_BASE_URL')
        if env_value:
            return env_value
        return self._get_first_defined(
            ('models', 'generation', 'base_url'),
            ('api', 'base_url'),
            default='https://api.openai.com/v1',
        )

    @property
    def api_key(self) -> str:
        """API密钥"""
        env_key = os.environ.get('BID_WRITER_API_KEY')
        if env_key:
            return env_key
        return self._get_first_defined(
            ('models', 'generation', 'api_key'),
            ('api', 'api_key'),
            default='',
        )

    @property
    def model(self) -> str:
        """模型名称"""
        env_value = os.environ.get('BID_WRITER_MODEL')
        if env_value:
            return env_value
        return self._get_first_defined(
            ('models', 'generation', 'model'),
            ('api', 'model'),
            default='gpt-4',
        )

    @property
    def temperature(self) -> float:
        """生成温度"""
        env_value = os.environ.get('BID_WRITER_TEMPERATURE')
        if env_value:
            try:
                return float(env_value)
            except ValueError:
                pass
        return self._get_float(
            ('models', 'generation', 'temperature'),
            ('api', 'temperature'),
            default=0.7,
        )

    @property
    def max_tokens(self) -> int:
        """最大token数"""
        env_value = os.environ.get('BID_WRITER_MAX_TOKENS')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        return self._get_int(
            ('models', 'generation', 'max_tokens'),
            ('api', 'max_tokens'),
            default=8000,
        )

    @property
    def api_timeout_seconds(self) -> int:
        """API超时时间（秒）"""
        env_value = os.environ.get('BID_WRITER_TIMEOUT_SECONDS')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        return self._get_int(
            ('models', 'generation', 'timeout_seconds'),
            ('api', 'timeout_seconds'),
            default=120,
        )

    @property
    def api_max_retries(self) -> int:
        """API最大重试次数"""
        env_value = os.environ.get('BID_WRITER_MAX_RETRIES')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        return self._get_int(
            ('models', 'generation', 'max_retries'),
            ('api', 'max_retries'),
            default=3,
        )

    @property
    def api_top_p(self) -> Optional[float]:
        """采样 top_p，可选"""
        env_value = os.environ.get('BID_WRITER_TOP_P')
        if env_value:
            try:
                return float(env_value)
            except ValueError:
                return None
        return self._get_optional_float(('models', 'generation', 'top_p'), ('api', 'top_p'))

    @property
    def api_seed(self) -> Optional[int]:
        """随机种子，可选"""
        env_value = os.environ.get('BID_WRITER_SEED')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                return None
        return self._get_optional_int(('models', 'generation', 'seed'), ('api', 'seed'))

    @property
    def role(self) -> str:
        """角色设定"""
        role_file = self._get_first_defined(('writing', 'role_file'), 'role_file', default='')
        if isinstance(role_file, str) and role_file.strip():
            text = self._read_text_file(role_file.strip())
            if text:
                return text
        return self._get_first_defined(
            ('writing', 'role'),
            'role',
            default='你是一位专业的标书撰写专家。',
        )

    @property
    def bid_requirements(self) -> str:
        """招标需求"""
        text = self._get_text_or_file(
            inline_paths=[('project', 'inputs', 'bid_requirements')],
            file_paths=[('project', 'inputs', 'bid_requirements_file')],
            resolver=self._resolve_project_path,
        )
        if text:
            return text
        return self._get_text_or_file(
            inline_paths=[('inputs', 'bid_requirements'), 'bid_requirements'],
            file_paths=[('inputs', 'bid_requirements_file'), 'bid_requirements_file'],
        )

    @property
    def scoring_criteria(self) -> str:
        """评分标准"""
        text = self._get_text_or_file(
            inline_paths=[('project', 'inputs', 'scoring_criteria')],
            file_paths=[('project', 'inputs', 'scoring_criteria_file')],
            resolver=self._resolve_project_path,
        )
        if text:
            return text
        return self._get_text_or_file(
            inline_paths=[('inputs', 'scoring_criteria'), 'scoring_criteria'],
            file_paths=[('inputs', 'scoring_criteria_file'), 'scoring_criteria_file'],
        )

    @property
    def outline_file(self) -> str:
        """大纲文件路径"""
        project_value = self._get_value('project', 'inputs', 'outline_file', default=self._MISSING)
        if project_value is not self._MISSING:
            return self._resolve_declared_path(
                project_value,
                resolver=self._resolve_project_path,
                default=str(self._resolve_project_path('./outline.md')),
            )
        value = self._get_first_defined(('inputs', 'outline_file'), 'outline_file', default='./outline.md')
        return self._resolve_declared_path(
            value,
            resolver=self._resolve_path,
            default=str(self._resolve_path('./outline.md')),
        )

    @property
    def output_directory(self) -> str:
        """输出目录"""
        value = self._get_first_defined(
            ('project', 'output_dir'),
            ('runtime', 'output', 'directory'),
            default=self._MISSING,
        )
        if value is not self._MISSING:
            return self._resolve_declared_path(
                value,
                resolver=self._resolve_project_path,
                default=str(self._resolve_project_path('./output')),
            )
        legacy_value = self._get_first_defined(('output', 'directory'), default='./output')
        return self._resolve_declared_path(
            legacy_value,
            resolver=self._resolve_path,
            default=str(self._resolve_path('./output')),
        )

    @property
    def output_prefix(self) -> str:
        """输出文件名前缀"""
        return self._get_first_defined(('runtime', 'output', 'prefix'), ('output', 'prefix'), default='')

    @property
    def output_include_title_header(self) -> bool:
        """保存文件时是否添加标题头"""
        return self._get_bool(('runtime', 'output', 'include_title_header'), ('output', 'include_title_header'), default=True)

    @property
    def output_overwrite_existing(self) -> bool:
        """保存文件时是否覆盖已有文件"""
        return self._get_bool(
            ('runtime', 'output', 'overwrite_existing'),
            ('output', 'overwrite_existing'),
            ('generation', 'overwrite_existing'),
            default=True
        )

    @property
    def output_normalize_soft_line_breaks_on_merge(self) -> bool:
        """整合标书时是否归一化正文中的软回车"""
        return self._get_bool(
            ('runtime', 'merge', 'normalize_soft_line_breaks'),
            ('output', 'normalize_soft_line_breaks_on_merge'),
            default=False
        )

    @property
    def output_filename_max_length(self) -> int:
        """输出文件名最大长度"""
        return self._get_int(('runtime', 'output', 'filename_max_length'), ('output', 'filename_max_length'), default=100)

    @property
    def output_empty_filename_fallback(self) -> str:
        """空文件名时的占位名称"""
        return self._get_first_defined(
            ('runtime', 'output', 'empty_filename_fallback'),
            ('output', 'empty_filename_fallback'),
            default='untitled',
        )

    @property
    def generation_default_target_words(self) -> int:
        """默认目标篇幅基准值。"""
        return self._get_int(
            ('writing', 'target_words', 'default'),
            ('writing', 'min_words', 'default'),
            ('generation', 'default_min_words'),
            'default_min_words',
            default=500,
        )

    @property
    def generation_target_words_min(self) -> int:
        """目标篇幅基准值下限。"""
        return self._get_int(
            ('writing', 'target_words', 'min'),
            ('writing', 'min_words', 'min'),
            ('generation', 'min_words_min'),
            default=100,
        )

    @property
    def generation_target_words_max(self) -> int:
        """目标篇幅基准值上限。"""
        return self._get_int(
            ('writing', 'target_words', 'max'),
            ('writing', 'min_words', 'max'),
            ('generation', 'min_words_max'),
            default=15000,
        )

    @property
    def generation_target_words_step(self) -> int:
        """目标篇幅基准值步长。"""
        return self._get_int(
            ('writing', 'target_words', 'step'),
            ('writing', 'min_words', 'step'),
            ('generation', 'min_words_step'),
            default=100,
        )

    @property
    def generation_target_words_upper_ratio(self) -> float:
        """目标篇幅区间上沿相对基准值的放宽比例。"""
        return self._get_float(('writing', 'target_words', 'upper_ratio'), default=1.15)

    def build_target_word_range(self, baseline: int) -> TargetWordRange:
        """根据基准值推导章节目标篇幅区间。"""
        lower = max(int(baseline), 0)
        step = max(int(self.generation_target_words_step), 1)
        ratio = max(float(self.generation_target_words_upper_ratio), 1.0)
        raw_upper = lower * ratio
        rounded_upper = int(math.ceil(raw_upper / step) * step)
        upper_cap = max(int(self.generation_target_words_max), lower)
        upper = min(max(rounded_upper, lower), upper_cap)
        return TargetWordRange(baseline=lower, lower=lower, upper=upper)

    @property
    def generation_default_min_words(self) -> int:
        """兼容旧调用：默认目标篇幅基准值。"""
        return self.generation_default_target_words

    @property
    def generation_min_words_min(self) -> int:
        """兼容旧调用：目标篇幅基准值下限。"""
        return self.generation_target_words_min

    @property
    def generation_min_words_max(self) -> int:
        """兼容旧调用：目标篇幅基准值上限。"""
        return self.generation_target_words_max

    @property
    def generation_min_words_step(self) -> int:
        """兼容旧调用：目标篇幅基准值步长。"""
        return self.generation_target_words_step

    @property
    def generation_stream(self) -> bool:
        """是否使用流式输出"""
        return self._get_bool(('runtime', 'stream', 'enabled'), ('generation', 'stream'), default=True)

    @property
    def generation_stream_idle_timeout_seconds(self) -> int:
        """流式输出在最后一个 token 后的静默收尾超时时间（秒）"""
        env_value = os.environ.get('BID_WRITER_STREAM_IDLE_TIMEOUT_SECONDS')
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        return self._get_int(
            ('runtime', 'stream', 'idle_timeout_seconds'),
            ('generation', 'stream_idle_timeout_seconds'),
            default=12,
        )

    @property
    def prompt_output_format(self) -> str:
        """输出格式说明"""
        return self._get_first_defined(('writing', 'output_format'), ('prompt', 'output_format'), default='Markdown格式')

    @property
    def prompt_first_line_template(self) -> str:
        """首行模板"""
        value = self._get_first_defined(('writing', 'first_line_template'), ('prompt', 'first_line_template'), default='')
        return str(value).strip() if value is not None else ''

    @property
    def prompt_allow_markdown_headings(self) -> bool:
        """是否允许输出 Markdown 标题符号"""
        return self._get_bool(('writing', 'allow_markdown_headings'), ('prompt', 'allow_markdown_headings'), default=False)

    @property
    def prompt_allow_english_terms(self) -> bool:
        """是否允许必要的英文术语"""
        return self._get_bool(('writing', 'allow_english_terms'), ('prompt', 'allow_english_terms'), default=False)

    @property
    def prompt_max_tables_per_section(self) -> int:
        """单节最大表格数"""
        return self._get_int(('writing', 'max_tables_per_section'), ('prompt', 'max_tables_per_section'), default=4)

    @property
    def prompt_max_mermaid_flowcharts_per_section(self) -> int:
        """单节最大 Mermaid 图示数"""
        return self._get_int(
            ('writing', 'max_mermaid_flowcharts_per_section'),
            ('prompt', 'max_mermaid_flowcharts_per_section'),
            default=0,
        )

    @property
    def prompt_summary_title(self) -> str:
        """章节总结标题名称"""
        return self._get_first_defined(('writing', 'summary_title'), ('prompt', 'summary_title'), default='章节小结')

    @property
    def prompt_bidder_name(self) -> str:
        """投标主体名称"""
        value = self._get_first_defined(('project', 'bidder_name'), ('writing', 'bidder_name'), ('prompt', 'bidder_name'), default='')
        return str(value).strip() if value is not None else ''

    @property
    def prompt_hard_constraints(self) -> list[str]:
        """高优先级强约束"""
        return self._get_string_list(('writing', 'hard_constraints'), ('prompt', 'hard_constraints'), default=[])

    @property
    def prompt_extra_rules(self) -> list[str]:
        """额外提示规则"""
        return self._get_string_list(('writing', 'extra_rules'), ('prompt', 'extra_rules'), default=[])

    @property
    def context_pruning_enabled(self) -> bool:
        """是否启用章节级上下文裁剪。"""
        if self._using_new_processing_schema():
            return self.processing_path != 'full_context'
        return self._legacy_context_pruning_enabled()

    @property
    def context_pruning_debug_dump(self) -> bool:
        """是否输出裁剪调试信息。"""
        return self._get_bool(
            ('runtime', 'debug', 'context_pruning_dump'),
            ('context_pruning', 'debug_dump'),
            default=False,
        )

    @property
    def context_pruning_mode(self) -> str:
        """章节裁剪模式。"""
        if self._using_new_processing_schema():
            if self.processing_path == 'hybrid_extract':
                return 'hybrid_extract'
            return 'legacy_rule'
        return self._legacy_context_pruning_base_mode()

    @property
    def context_pruning_unavailable_policy(self) -> str:
        """新模式不可用时的处理策略。"""
        value = self._get_first_defined(
            ('processing', 'hybrid_extract', 'unavailable_policy'),
            ('context_pruning', 'unavailable_policy'),
            default='fallback_legacy',
        )
        normalized = str(value).strip().lower() if value is not None else 'fallback_legacy'
        return normalized if normalized in {'fallback_legacy', 'fail_fast'} else 'fallback_legacy'

    @property
    def context_pruning_local_outline_include_ancestors(self) -> bool:
        """局部大纲是否保留祖先链。"""
        return self._get_bool(
            ('processing', 'context_view', 'include_ancestors'),
            ('context_pruning', 'local_outline', 'include_ancestors'),
            default=True,
        )

    @property
    def context_pruning_local_outline_include_siblings(self) -> bool:
        """局部大纲是否保留同级标题。"""
        return self._get_bool(
            ('processing', 'context_view', 'include_siblings'),
            ('context_pruning', 'local_outline', 'include_siblings'),
            default=True,
        )

    @property
    def context_pruning_local_outline_max_siblings(self) -> int:
        """局部大纲最多保留的同级标题数。"""
        return self._get_int(
            ('processing', 'context_view', 'max_siblings'),
            ('context_pruning', 'local_outline', 'max_siblings'),
            default=8,
        )

    @property
    def context_pruning_scoring_enabled(self) -> bool:
        """是否启用评分项路由。"""
        if self._using_new_processing_schema():
            return self.context_pruning_enabled
        return self._get_bool(('context_pruning', 'scoring', 'enabled'), default=True)

    @property
    def context_pruning_scoring_mode(self) -> str:
        """评分标准提炼模式。"""
        if self._using_new_processing_schema():
            if self.processing_path == 'hybrid_extract':
                return 'hybrid_extract'
            if self.processing_path in {'full_context', 'legacy_rule'}:
                return 'legacy_rule'
        return self._legacy_context_pruning_scoring_mode()

    @property
    def context_pruning_scoring_parse_mode(self) -> str:
        """评分标准解析模式。"""
        value = self._get_first_defined(
            ('processing', 'hybrid_extract', 'scoring_parse_mode'),
            ('context_pruning', 'scoring', 'parse_mode'),
            default='auto',
        )
        normalized = str(value).strip().lower() if value is not None else 'auto'
        return normalized if normalized in {'auto', 'table_only', 'text_only'} else 'auto'

    @property
    def context_pruning_scoring_max_rows(self) -> int:
        """评分项路由最多保留的评分行数。"""
        return self._get_int(
            ('processing', self.processing_path, 'scoring_max_rows'),
            ('processing', 'legacy_rule', 'scoring_max_rows'),
            ('processing', 'hybrid_extract', 'scoring_max_rows'),
            ('context_pruning', 'scoring', 'max_rows'),
            default=4,
        )

    @property
    def context_pruning_requirements_mode(self) -> str:
        """采购需求提炼模式。"""
        if self._using_new_processing_schema():
            if self.processing_path == 'hybrid_extract':
                return 'hybrid_extract'
            if self.processing_path in {'full_context', 'legacy_rule'}:
                return 'legacy_rule'
        return self._legacy_context_pruning_requirements_mode()

    @property
    def context_pruning_requirements_max_quotes(self) -> int:
        """采购需求摘录最多保留条数。"""
        return self._get_int(
            ('processing', self.processing_path, 'requirements_max_quotes'),
            ('processing', 'legacy_rule', 'requirements_max_quotes'),
            ('processing', 'hybrid_extract', 'requirements_max_quotes'),
            ('context_pruning', 'requirements', 'max_quotes'),
            default=4,
        )

    @property
    def context_pruning_requirements_max_quote_chars(self) -> int:
        """采购需求单条摘录最大字符数。"""
        return self._get_int(
            ('processing', self.processing_path, 'requirements_max_quote_chars'),
            ('processing', 'legacy_rule', 'requirements_max_quote_chars'),
            ('processing', 'hybrid_extract', 'requirements_max_quote_chars'),
            ('context_pruning', 'requirements', 'max_quote_chars'),
            default=220,
        )

    @property
    def context_pruning_requirements_brief_enabled(self) -> bool:
        """是否启用需求摘要。"""
        return self._get_bool(
            ('processing', self.processing_path, 'requirement_brief_enabled'),
            ('processing', 'legacy_rule', 'requirement_brief_enabled'),
            ('processing', 'hybrid_extract', 'requirement_brief_enabled'),
            ('context_pruning', 'requirements_brief', 'enabled'),
            default=False,
        )

    @property
    def context_pruning_requirements_brief_fallback(self) -> str:
        """需求摘要失败时的回退策略。"""
        value = self._get_first_defined(
            ('processing', self.processing_path, 'requirement_brief_fallback'),
            ('processing', 'legacy_rule', 'requirement_brief_fallback'),
            ('processing', 'hybrid_extract', 'requirement_brief_fallback'),
            ('context_pruning', 'requirements_brief', 'fallback'),
            default='rule_only',
        )
        return str(value).strip() if value is not None else 'rule_only'

    @property
    def context_pruning_retrieval_lexical_enabled(self) -> bool:
        """是否启用 lexical retrieval。"""
        return self._get_bool(
            ('processing', 'hybrid_extract', 'retrieval', 'lexical_enabled'),
            ('context_pruning', 'retrieval', 'lexical_enabled'),
            default=True,
        )

    @property
    def context_pruning_retrieval_vector_enabled(self) -> bool:
        """是否启用向量召回。"""
        return self._get_bool(
            ('processing', 'hybrid_extract', 'retrieval', 'vector_enabled'),
            ('context_pruning', 'retrieval', 'vector_enabled'),
            default=False,
        )

    @property
    def context_pruning_retrieval_rerank_enabled(self) -> bool:
        """是否启用二次重排或校验。"""
        return self._get_bool(
            ('processing', 'hybrid_extract', 'retrieval', 'verify_enabled'),
            ('context_pruning', 'retrieval', 'rerank_enabled'),
            default=False,
        )

    @property
    def context_pruning_rerank_or_verify_enabled(self) -> bool:
        """统一判断是否启用候选精排 / 校验。"""
        return bool(
            self.context_pruning_retrieval_rerank_enabled
            or self.context_pruning_extraction_llm_verify_enabled
        )

    @property
    def context_pruning_retrieval_top_k_lexical(self) -> int:
        """lexical retrieval 候选数。"""
        return self._get_int(
            ('processing', 'hybrid_extract', 'retrieval', 'top_k_lexical'),
            ('context_pruning', 'retrieval', 'top_k_lexical'),
            default=20,
        )

    @property
    def context_pruning_retrieval_top_k_vector(self) -> int:
        """vector retrieval 候选数。"""
        return self._get_int(
            ('processing', 'hybrid_extract', 'retrieval', 'top_k_vector'),
            ('context_pruning', 'retrieval', 'top_k_vector'),
            default=20,
        )

    @property
    def context_pruning_retrieval_top_k_fused(self) -> int:
        """融合排序候选数。"""
        return self._get_int(
            ('processing', 'hybrid_extract', 'retrieval', 'top_k_fused'),
            ('context_pruning', 'retrieval', 'top_k_fused'),
            default=30,
        )

    @property
    def context_pruning_retrieval_top_k_final(self) -> int:
        """最终进入摘录阶段的候选数。"""
        return self._get_int(
            ('processing', 'hybrid_extract', 'retrieval', 'top_k_final'),
            ('context_pruning', 'retrieval', 'top_k_final'),
            default=6,
        )

    @property
    def context_pruning_retrieval_min_fused_score(self) -> float:
        """最终候选最小得分。"""
        return self._get_float(
            ('processing', 'hybrid_extract', 'retrieval', 'min_fused_score'),
            ('context_pruning', 'retrieval', 'min_fused_score'),
            default=0.0,
        )

    @property
    def context_pruning_extraction_quote_only(self) -> bool:
        """是否只允许原文摘录。"""
        return self._get_bool(
            ('processing', 'hybrid_extract', 'quote_only'),
            ('context_pruning', 'extraction', 'quote_only'),
            default=True,
        )

    @property
    def context_pruning_extraction_return_ids_only(self) -> bool:
        """辅助模型是否只返回片段 ID。"""
        return self._get_bool(
            ('processing', 'hybrid_extract', 'return_ids_only'),
            ('context_pruning', 'extraction', 'return_ids_only'),
            default=True,
        )

    @property
    def context_pruning_extraction_llm_verify_enabled(self) -> bool:
        """是否启用候选校验。"""
        return self._get_bool(
            ('processing', 'hybrid_extract', 'retrieval', 'verify_enabled'),
            ('context_pruning', 'extraction', 'llm_verify_enabled'),
            default=False,
        )

    @property
    def context_pruning_extraction_llm_verify_max_candidates(self) -> int:
        """辅助校验最多接收候选数。"""
        return self._get_int(
            ('processing', 'hybrid_extract', 'verify_max_candidates'),
            ('context_pruning', 'extraction', 'llm_verify_max_candidates'),
            default=8,
        )

    @property
    def embedding_api_base_url(self) -> str:
        """embedding 服务地址，只从环境变量读取。"""
        return (
            self._get_env_str('BID_WRITER_EMBEDDING_API_BASE_URL')
            or str(self._get_first_defined(('models', 'embedding', 'base_url'), default='')).strip()
        )

    @property
    def embedding_api_key(self) -> str:
        """embedding 服务密钥，只从环境变量读取。"""
        return (
            self._get_env_str('BID_WRITER_EMBEDDING_API_KEY')
            or str(self._get_first_defined(('models', 'embedding', 'api_key'), default='')).strip()
        )

    @property
    def embedding_model(self) -> str:
        """embedding 模型名称。"""
        value = self._get_first_defined(
            ('models', 'embedding', 'model'),
            ('context_pruning', 'retrieval', 'embedding', 'model'),
            default='text-embedding-3-small',
        )
        return str(value).strip() if value is not None else 'text-embedding-3-small'

    @property
    def embedding_batch_size(self) -> int:
        """embedding 批大小。"""
        return self._get_int(
            ('models', 'embedding', 'batch_size'),
            ('context_pruning', 'retrieval', 'embedding', 'batch_size'),
            default=64,
        )

    @property
    def embedding_cache_dir(self) -> str:
        """embedding 本地缓存目录。"""
        value = self._get_value('models', 'embedding', 'cache_dir', default=self._MISSING)
        if value is not self._MISSING:
            return self._resolve_declared_path(
                value,
                resolver=self._resolve_path,
                default=str(self._resolve_path('./output/_embedding_cache')),
            )
        legacy_value = self._get_first_defined(('context_pruning', 'retrieval', 'embedding', 'cache_dir'), default='./output/_embedding_cache')
        return self._resolve_declared_path(
            legacy_value,
            resolver=self._resolve_path,
            default=str(self._resolve_path('./output/_embedding_cache')),
        )

    @property
    def embedding_rebuild_on_source_change(self) -> bool:
        """源文变化时是否重建 embedding 缓存。"""
        return self._get_bool(
            ('models', 'embedding', 'rebuild_on_source_change'),
            ('context_pruning', 'retrieval', 'embedding', 'rebuild_on_source_change'),
            default=True,
        )

    @property
    def embedding_query_prefix(self) -> str:
        """查询文本 embedding 前缀。"""
        value = self._get_first_defined(
            ('models', 'embedding', 'query_prefix'),
            ('context_pruning', 'retrieval', 'embedding', 'query_prefix'),
            default='',
        )
        return str(value).strip() if value is not None else ''

    @property
    def embedding_document_prefix(self) -> str:
        """文档文本 embedding 前缀。"""
        value = self._get_first_defined(
            ('models', 'embedding', 'document_prefix'),
            ('context_pruning', 'retrieval', 'embedding', 'document_prefix'),
            default='',
        )
        return str(value).strip() if value is not None else ''

    @property
    def embedding_is_configured(self) -> bool:
        """embedding 服务连接参数是否齐全。"""
        return bool(self.embedding_api_base_url and self.embedding_api_key)

    def validate_context_pruning_runtime(self, raise_on_error: bool = True) -> list[str]:
        """校验当前 hybrid_extract v1 / auto 模式是否具备运行条件。"""
        errors: list[str] = []
        processing_path = self.processing_path

        if processing_path == 'auto':
            if not self.pruning_api_is_configured:
                errors.append(
                    'auto 模式需要配置辅助模型：BID_WRITER_PRUNING_API_BASE_URL、'
                    'BID_WRITER_PRUNING_API_KEY、BID_WRITER_PRUNING_MODEL'
                )
            if not self.context_pruning_retrieval_lexical_enabled:
                errors.append('auto 模式要求 lexical_enabled=true')
            if raise_on_error and errors:
                raise ValueError('；'.join(errors))
            return errors

        hybrid_requested = (
            self.context_pruning_enabled
            and (
                processing_path == 'hybrid_extract'
                or (
                    processing_path == 'mixed'
                    and (
                        self._legacy_context_pruning_scoring_mode() == 'hybrid_extract'
                        or self._legacy_context_pruning_requirements_mode() == 'hybrid_extract'
                    )
                )
            )
        )
        if not hybrid_requested:
            return errors

        if not self.context_pruning_retrieval_lexical_enabled:
            errors.append('hybrid_extract v1 要求 lexical_enabled=true')
        if self.context_pruning_retrieval_vector_enabled:
            if not self.embedding_is_configured:
                errors.append('启用 vector_enabled=true 时，必须在 .env.local 中配置 BID_WRITER_EMBEDDING_API_BASE_URL 和 BID_WRITER_EMBEDDING_API_KEY')
        if self.context_pruning_rerank_or_verify_enabled:
            if not self.pruning_api_is_configured:
                errors.append('启用 rerank/verify 时，必须先配置章节裁剪辅助模型 BID_WRITER_PRUNING_*')
            if not self.context_pruning_extraction_return_ids_only:
                errors.append('启用 rerank/verify 时，当前要求 return_ids_only=true 以保证原文回填')

        if raise_on_error and errors:
            raise ValueError('；'.join(errors))
        return errors

    @property
    def pruning_api_base_url(self) -> str:
        """章节裁剪辅助模型 API 地址，只从环境变量读取。"""
        return (
            self._get_env_str('BID_WRITER_PRUNING_API_BASE_URL')
            or str(self._get_first_defined(('models', 'pruning', 'base_url'), default='')).strip()
        )

    @property
    def pruning_api_key(self) -> str:
        """章节裁剪辅助模型 API Key，只从环境变量读取。"""
        return (
            self._get_env_str('BID_WRITER_PRUNING_API_KEY')
            or str(self._get_first_defined(('models', 'pruning', 'api_key'), default='')).strip()
        )

    @property
    def pruning_model(self) -> str:
        """章节裁剪辅助模型名称。"""
        return (
            self._get_env_str('BID_WRITER_PRUNING_MODEL')
            or str(self._get_first_defined(('models', 'pruning', 'model'), ('context_pruning', 'api', 'model'), default='')).strip()
        )

    @property
    def pruning_temperature(self) -> float:
        """章节裁剪辅助模型温度。"""
        env_value = self._get_env_float('BID_WRITER_PRUNING_TEMPERATURE')
        if env_value is not None:
            return env_value
        return self._get_float(('models', 'pruning', 'temperature'), ('context_pruning', 'api', 'temperature'), default=0.2)

    @property
    def pruning_max_tokens(self) -> int:
        """章节裁剪辅助模型最大 token 数。"""
        env_value = self._get_env_int('BID_WRITER_PRUNING_MAX_TOKENS')
        if env_value is not None:
            return env_value
        return self._get_int(('models', 'pruning', 'max_tokens'), ('context_pruning', 'api', 'max_tokens'), default=1200)

    @property
    def pruning_timeout_seconds(self) -> int:
        """章节裁剪辅助模型超时时间。"""
        env_value = self._get_env_int('BID_WRITER_PRUNING_TIMEOUT_SECONDS')
        if env_value is not None:
            return env_value
        return self._get_int(('models', 'pruning', 'timeout_seconds'), ('context_pruning', 'api', 'timeout_seconds'), default=60)

    @property
    def pruning_max_retries(self) -> int:
        """章节裁剪辅助模型最大重试次数。"""
        env_value = self._get_env_int('BID_WRITER_PRUNING_MAX_RETRIES')
        if env_value is not None:
            return env_value
        return self._get_int(('models', 'pruning', 'max_retries'), ('context_pruning', 'api', 'max_retries'), default=2)

    @property
    def pruning_top_p(self) -> Optional[float]:
        """章节裁剪辅助模型采样 top_p。"""
        env_value = self._get_env_float('BID_WRITER_PRUNING_TOP_P')
        if env_value is not None:
            return env_value
        return self._get_optional_float(('models', 'pruning', 'top_p'), ('context_pruning', 'api', 'top_p'))

    @property
    def pruning_seed(self) -> Optional[int]:
        """章节裁剪辅助模型随机种子。"""
        env_value = self._get_env_int('BID_WRITER_PRUNING_SEED')
        if env_value is not None:
            return env_value
        return self._get_optional_int(('models', 'pruning', 'seed'), ('context_pruning', 'api', 'seed'))

    @property
    def pruning_api_is_configured(self) -> bool:
        """辅助模型调用所需关键配置是否齐全。"""
        return bool(self.pruning_api_base_url and self.pruning_api_key and self.pruning_model)

    # ── auto 模式专属属性 ──

    @property
    def project_background_enabled(self) -> bool:
        """是否启用项目背景生成。"""
        return self._get_bool(
            ('processing', 'project_background', 'enabled'),
            default=True,
        )

    @property
    def project_background_cache_dir(self) -> str:
        """项目背景缓存目录。"""
        value = self._get_value('processing', 'project_background', 'cache_dir', default=self._MISSING)
        if value is not self._MISSING:
            return self._resolve_declared_path(
                value,
                resolver=self._resolve_project_path,
                default=str(self._resolve_project_path('./caches/project_background')),
            )
        return str(self._resolve_project_path('./caches/project_background'))

    @property
    def project_background_max_chars(self) -> int:
        """项目背景最大字符数。"""
        return self._get_int(
            ('processing', 'project_background', 'max_chars'),
            default=800,
        )

    @property
    def scoring_classify_cache_dir(self) -> str:
        """评分分类缓存目录。"""
        value = self._get_value('processing', 'scoring_classify', 'cache_dir', default=self._MISSING)
        if value is not self._MISSING:
            return self._resolve_declared_path(
                value,
                resolver=self._resolve_project_path,
                default=str(self._resolve_project_path('./caches/scoring_classify')),
            )
        return str(self._resolve_project_path('./caches/scoring_classify'))

    @property
    def auto_requirements_top_k(self) -> int:
        """auto 模式下需求检索的 top-K 数量。"""
        return self._get_int(
            ('processing', 'auto', 'requirements_top_k'),
            default=8,
        )

    @property
    def chapter_writing_plan_enabled(self) -> bool:
        """是否启用 full_context 下的章节写作计划。"""
        if self.processing_path != 'full_context':
            return False
        return self._get_bool(
            ('processing', 'full_context', 'chapter_writing_plan', 'enabled'),
            default=False,
        )

    @property
    def chapter_writing_plan_max_chars(self) -> int:
        """章节写作计划最大字符数。"""
        return self._get_int(
            ('processing', 'full_context', 'chapter_writing_plan', 'max_chars'),
            default=320,
        )

    @property
    def chapter_writing_plan_cache_dir(self) -> str:
        """章节写作计划缓存目录。"""
        value = self._get_value(
            'processing',
            'full_context',
            'chapter_writing_plan',
            'cache_dir',
            default=self._MISSING,
        )
        if value is not self._MISSING:
            return self._resolve_declared_path(
                value,
                resolver=self._resolve_project_path,
                default=str(self._resolve_project_path('./caches/chapter_writing_plan')),
            )
        return str(self._resolve_project_path('./caches/chapter_writing_plan'))

    @property
    def generation_trace_enabled(self) -> bool:
        """是否启用章节生成 trace。"""
        return self._get_bool(('runtime', 'trace', 'enabled'), ('generation_trace', 'enabled'), default=False)

    @property
    def generation_trace_mode(self) -> str:
        """章节生成 trace 模式。"""
        value = self._get_first_defined(('runtime', 'trace', 'mode'), ('generation_trace', 'mode'), default='full')
        normalized = str(value).strip().lower() if value is not None else 'full'
        return normalized if normalized in {'basic', 'full'} else 'full'

    @property
    def generation_trace_directory(self) -> str:
        """章节生成 trace 输出目录。"""
        value = self._get_value('runtime', 'trace', 'directory', default=self._MISSING)
        if value is not self._MISSING:
            return self._resolve_declared_path(
                value,
                resolver=self._resolve_path,
                default=str(self._resolve_path('./log/generation_traces')),
            )
        legacy_value = self._get_first_defined(('generation_trace', 'directory'), default='')
        if isinstance(legacy_value, str) and legacy_value.strip():
            return str(self._resolve_path(legacy_value.strip()))
        return str((Path(__file__).resolve().parent.parent / 'log' / 'generation_traces'))

    @property
    def generation_trace_write_prompt(self) -> bool:
        """是否写入 system/user prompt 原文。"""
        default = True
        return self._get_bool(('runtime', 'trace', 'write_prompt'), ('generation_trace', 'write_prompt'), default=default)

    @property
    def generation_trace_write_output(self) -> bool:
        """是否写入最终生成正文。"""
        default = True
        return self._get_bool(('runtime', 'trace', 'write_output'), ('generation_trace', 'write_output'), default=default)

    @property
    def generation_trace_write_context(self) -> bool:
        """是否写入上下文拼接和裁剪详情。"""
        default = self.generation_trace_mode == 'full'
        return self._get_bool(('runtime', 'trace', 'write_context'), ('generation_trace', 'write_context'), default=default)

    @property
    def generation_trace_write_summary(self) -> bool:
        """是否写入摘要文件。"""
        default = True
        return self._get_bool(('runtime', 'trace', 'write_summary'), ('generation_trace', 'write_summary'), default=default)

    @property
    def generation_trace_redact_sensitive(self) -> bool:
        """是否脱敏敏感字段。"""
        return self._get_bool(('runtime', 'trace', 'redact_sensitive'), ('generation_trace', 'redact_sensitive'), default=True)

    def get_outline_content(self) -> str:
        """获取大纲内容"""
        outline_path = self._resolve_path(self.outline_file)
        if not outline_path.exists():
            raise FileNotFoundError(f"大纲文件不存在: {outline_path}")
        return outline_path.read_text(encoding='utf-8')
