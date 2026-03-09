"""
消息类型枚举与数据模型

定义了 6 级消息分类体系和统一的消息数据结构
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class NotifyLevel(Enum):
    """
    通知级别枚举
    
    每个级别包含: (优先级, 颜色模板, Emoji, 标题前缀)
    """
    CRITICAL = ("P0", "red", "🚨", "[紧急]")
    ERROR = ("P1", "orange", "❌", "[失败]")
    WARNING = ("P2", "yellow", "⚠️", "[警告]")
    SUCCESS = ("P3", "green", "✅", "[成功]")
    INFO = ("P4", "blue", "ℹ️", "[通知]")
    PENDING = ("P5", "purple", "⏳", "[待办]")
    
    @property
    def priority(self) -> str:
        """获取优先级标识 (P0-P5)"""
        return self.value[0]
    
    @property
    def color(self) -> str:
        """获取飞书卡片颜色模板"""
        return self.value[1]
    
    @property
    def emoji(self) -> str:
        """获取对应的 Emoji"""
        return self.value[2]
    
    @property
    def prefix(self) -> str:
        """获取标题前缀"""
        return self.value[3]
    
    @classmethod
    def from_string(cls, level_str: str) -> "NotifyLevel":
        """从字符串创建枚举值"""
        level_str = level_str.upper()
        for level in cls:
            if level.name == level_str:
                return level
        raise ValueError(f"Unknown notify level: {level_str}")


@dataclass
class LinkButton:
    """操作按钮/链接"""
    text: str
    url: str
    is_danger: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "text": self.text,
            "url": self.url,
            "is_danger": self.is_danger,
        }


@dataclass
class NotifyMessage:
    """
    统一消息模型
    
    综合了四份提案的设计，支持:
    - 上下文信息 (source, task_name, task_id)
    - 指标数据 (metrics)
    - 链接与按钮 (links)
    - @ 提醒 (mentions)
    - 去重标识 (dedupe_key)
    - 扩展字段 (extra)
    """
    
    # 必填字段
    level: NotifyLevel
    title: str  # 标题，建议 <= 32 字符
    content: str  # 主要内容
    
    # 上下文信息
    source: str = "default"  # 来源系统，如 Airflow/Spark/Flink
    task_name: Optional[str] = None  # 任务名称
    task_id: Optional[str] = None  # 任务 ID
    
    # 时间信息
    timestamp: Optional[datetime] = None  # 消息时间戳
    start_time: Optional[str] = None  # 任务开始时间
    end_time: Optional[str] = None  # 任务结束时间
    duration: Optional[str] = None  # 耗时
    
    # 错误信息
    error_msg: Optional[str] = None  # 错误详情
    error_code: Optional[str] = None  # 错误代码
    
    # 指标数据
    metrics: Optional[Dict[str, Any]] = None  # {"rows": 1000, "duration": "5m"}
    
    # 链接与按钮
    links: List[LinkButton] = field(default_factory=list)
    
    # @ 提醒
    mentions: List[str] = field(default_factory=list)  # user_id 列表
    mention_all: bool = False  # 是否 @ 所有人
    
    # 去重标识
    dedupe_key: Optional[str] = None  # 相同 key 的消息会被合并/更新
    
    # 扩展字段
    extra: Optional[Dict[str, Any]] = None

    # 发送目标（可选，用于直发个人）
    to_user: Optional[str] = None        # 单个用户 ID（open_id / union_id）
    to_users: Optional[List[str]] = None  # 多个用户 ID
    
    def __post_init__(self):
        """初始化后处理"""
        if self.timestamp is None:
            self.timestamp = datetime.now()
        
        # 将 dict 格式的 links 转换为 LinkButton
        if self.links and isinstance(self.links[0], dict):
            self.links = [
                LinkButton(
                    text=link.get("text", "查看详情"),
                    url=link.get("url", ""),
                    is_danger=link.get("is_danger", False),
                )
                for link in self.links
            ]
    
    @property
    def formatted_title(self) -> str:
        """获取格式化的标题（含 Emoji 和前缀）"""
        return f"{self.level.emoji} {self.level.prefix} {self.title}"
    
    @property
    def formatted_timestamp(self) -> str:
        """获取格式化的时间戳"""
        if self.timestamp:
            return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def add_link(self, text: str, url: str, is_danger: bool = False) -> "NotifyMessage":
        """添加链接按钮（链式调用）"""
        self.links.append(LinkButton(text=text, url=url, is_danger=is_danger))
        return self
    
    def add_mention(self, user_id: str) -> "NotifyMessage":
        """添加 @ 用户（链式调用）"""
        if user_id not in self.mentions:
            self.mentions.append(user_id)
        return self
    
    def set_metrics(self, **kwargs) -> "NotifyMessage":
        """设置指标数据（链式调用）"""
        if self.metrics is None:
            self.metrics = {}
        self.metrics.update(kwargs)
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "level": self.level.name,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "task_name": self.task_name,
            "task_id": self.task_id,
            "timestamp": self.formatted_timestamp,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "error_msg": self.error_msg,
            "error_code": self.error_code,
            "metrics": self.metrics,
            "links": [link.to_dict() for link in self.links],
            "mentions": self.mentions,
            "mention_all": self.mention_all,
            "dedupe_key": self.dedupe_key,
            "extra": self.extra,
            "to_user": self.to_user,
            "to_users": self.to_users,
        }

