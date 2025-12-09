"""
历史记录模块
记录扩写历史，支持查询和恢复
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class HistoryRecord:
    """扩写历史记录"""
    id: str  # 唯一ID
    timestamp: str  # ISO格式时间戳
    heading_title: str  # 扩写的标题
    heading_path: str  # 标题完整路径
    additional_requirements: str  # 附加要求
    min_words: int  # 最低字数要求
    actual_words: int  # 实际生成字数
    output_file: str  # 输出文件路径
    status: str  # 状态: success, failed, modified
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'HistoryRecord':
        return cls(**data)


class HistoryManager:
    """历史记录管理器"""
    
    def __init__(self, history_file: str = "./history.json", max_records: int = 100):
        self.history_file = Path(history_file)
        self.max_records = max_records
        self.records: List[HistoryRecord] = []
        self.load()
    
    def load(self) -> None:
        """加载历史记录"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.records = [HistoryRecord.from_dict(r) for r in data]
            except (json.JSONDecodeError, KeyError) as e:
                print(f"警告: 历史记录文件损坏，将创建新文件: {e}")
                self.records = []
    
    def save(self) -> None:
        """保存历史记录"""
        # 确保目录存在
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 限制记录数量
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records:]
        
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump([r.to_dict() for r in self.records], f, ensure_ascii=False, indent=2)
    
    def add_record(
        self,
        heading_title: str,
        heading_path: str,
        additional_requirements: str,
        min_words: int,
        actual_words: int,
        output_file: str,
        status: str = "success"
    ) -> HistoryRecord:
        """添加新记录"""
        record = HistoryRecord(
            id=self._generate_id(),
            timestamp=datetime.now().isoformat(),
            heading_title=heading_title,
            heading_path=heading_path,
            additional_requirements=additional_requirements,
            min_words=min_words,
            actual_words=actual_words,
            output_file=output_file,
            status=status
        )
        self.records.append(record)
        self.save()
        return record
    
    def _generate_id(self) -> str:
        """生成唯一ID"""
        return datetime.now().strftime("%Y%m%d%H%M%S%f")
    
    def get_recent_records(self, count: int = 10) -> List[HistoryRecord]:
        """获取最近的记录"""
        return self.records[-count:][::-1]  # 最新的在前
    
    def get_records_by_title(self, title: str) -> List[HistoryRecord]:
        """根据标题查找记录"""
        return [r for r in self.records if title in r.heading_title]
    
    def get_record_by_id(self, record_id: str) -> Optional[HistoryRecord]:
        """根据ID查找记录"""
        for record in self.records:
            if record.id == record_id:
                return record
        return None
    
    def update_status(self, record_id: str, status: str) -> bool:
        """更新记录状态"""
        record = self.get_record_by_id(record_id)
        if record:
            record.status = status
            self.save()
            return True
        return False
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        if not self.records:
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "modified": 0,
                "total_words": 0
            }
        
        return {
            "total": len(self.records),
            "success": sum(1 for r in self.records if r.status == "success"),
            "failed": sum(1 for r in self.records if r.status == "failed"),
            "modified": sum(1 for r in self.records if r.status == "modified"),
            "total_words": sum(r.actual_words for r in self.records)
        }
    
    def clear(self) -> None:
        """清空所有记录"""
        self.records = []
        self.save()
