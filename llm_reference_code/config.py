"""
配置管理模块
负责加载和管理系统配置

使用方法：
    from config import Config
    
    config = Config("config.yaml")
    print(config.api_base_url)
    print(config.model)
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
        return self._config.get('role', '你是一位专业的AI助手。')
    
    def get_text_from_file_or_config(self, config_key: str, file_key: str = None) -> str:
        """
        从文件或配置中获取文本内容
        
        Args:
            config_key: 配置项的键名
            file_key: 文件路径配置项的键名（如果为None，则使用 config_key + '_file'）
            
        Returns:
            文本内容
        """
        if file_key is None:
            file_key = f"{config_key}_file"
        
        # 优先从文件加载
        file_path = self._config.get(file_key)
        if file_path:
            path = Path(file_path)
            if path.exists():
                return path.read_text(encoding='utf-8')
        
        # 否则从配置中直接获取
        return self._config.get(config_key, '')


if __name__ == "__main__":
    # 测试代码
    config = Config("config.yaml")
    print(f"API Base URL: {config.api_base_url}")
    print(f"Model: {config.model}")
    print(f"Temperature: {config.temperature}")
    print(f"Max Tokens: {config.max_tokens}")
