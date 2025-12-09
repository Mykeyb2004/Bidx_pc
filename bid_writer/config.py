"""
配置管理模块
负责加载和管理系统配置
"""

import os
from pathlib import Path
from typing import Optional
import yaml


class Config:
    """系统配置管理器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._config = {}
        self.load()
    
    def load(self) -> None:
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
    
    def reload(self) -> None:
        """重新加载配置"""
        self.load()
    
    @property
    def api_base_url(self) -> str:
        """API基础URL"""
        return self._config.get('api', {}).get('base_url', 'https://api.openai.com/v1')
    
    @property
    def api_key(self) -> str:
        """API密钥"""
        # 优先从环境变量获取
        env_key = os.environ.get('BID_WRITER_API_KEY')
        if env_key:
            return env_key
        return self._config.get('api', {}).get('api_key', '')
    
    @property
    def model(self) -> str:
        """模型名称"""
        return self._config.get('api', {}).get('model', 'gpt-4')
    
    @property
    def temperature(self) -> float:
        """生成温度"""
        return self._config.get('api', {}).get('temperature', 0.7)
    
    @property
    def max_tokens(self) -> int:
        """最大token数"""
        return self._config.get('api', {}).get('max_tokens', 8000)
    
    @property
    def role(self) -> str:
        """角色设定"""
        return self._config.get('role', '你是一位专业的标书撰写专家。')
    
    @property
    def bid_requirements(self) -> str:
        """招标需求"""
        # 优先从文件加载
        file_path = self._config.get('bid_requirements_file')
        if file_path:
            path = Path(file_path)
            if path.exists():
                return path.read_text(encoding='utf-8')
        return self._config.get('bid_requirements', '')
    
    @property
    def scoring_criteria(self) -> str:
        """评分标准"""
        # 优先从文件加载
        file_path = self._config.get('scoring_criteria_file')
        if file_path:
            path = Path(file_path)
            if path.exists():
                return path.read_text(encoding='utf-8')
        return self._config.get('scoring_criteria', '')
    
    @property
    def outline_file(self) -> str:
        """大纲文件路径"""
        return self._config.get('outline_file', './outline.md')
    
    @property
    def output_directory(self) -> str:
        """输出目录"""
        return self._config.get('output', {}).get('directory', './output')
    
    @property
    def output_prefix(self) -> str:
        """输出文件名前缀"""
        return self._config.get('output', {}).get('prefix', '')
    
    @property
    def history_enabled(self) -> bool:
        """是否启用历史记录"""
        return self._config.get('history', {}).get('enabled', True)
    
    @property
    def history_file(self) -> str:
        """历史记录文件路径"""
        return self._config.get('history', {}).get('file', './history.json')
    
    @property
    def history_max_records(self) -> int:
        """最大历史记录数"""
        return self._config.get('history', {}).get('max_records', 100)
    
    def get_outline_content(self) -> str:
        """获取大纲内容"""
        outline_path = Path(self.outline_file)
        if not outline_path.exists():
            raise FileNotFoundError(f"大纲文件不存在: {outline_path}")
        return outline_path.read_text(encoding='utf-8')
