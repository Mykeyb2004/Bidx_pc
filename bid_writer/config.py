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

    def load(self) -> None:
        """加载配置文件"""
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
        return self._get_first_defined(('output', 'directory'), default='./output')

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
    def prompt_output_format(self) -> str:
        """输出格式说明"""
        return self._get_first_defined(('prompt', 'output_format'), default='Markdown格式')

    @property
    def prompt_first_line_template(self) -> str:
        """首行模板"""
        return self._get_first_defined(('prompt', 'first_line_template'), default='#### {title}')

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
    def prompt_extra_rules(self) -> list[str]:
        """额外提示规则"""
        value = self._get_first_defined(('prompt', 'extra_rules'), default=[])
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def get_outline_content(self) -> str:
        """获取大纲内容"""
        outline_path = self._resolve_path(self.outline_file)
        if not outline_path.exists():
            raise FileNotFoundError(f"大纲文件不存在: {outline_path}")
        return outline_path.read_text(encoding='utf-8')
