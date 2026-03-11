"""
配置管理模块

支持通过环境变量、配置文件或代码配置
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class NotifyConfig:
    """
    通知工具配置
    
    支持多种配置来源:
    1. 代码直接传参
    2. 环境变量 (FEISHU_WEBHOOK, FEISHU_SOURCE 等)
    3. 配置文件
    """
    
    # Webhook 配置
    webhook_url: Optional[str] = None  # 飞书机器人 Webhook URL

    # 飞书应用凭证（用于直发个人通知）
    app_id: Optional[str] = None       # 飞书应用 App ID
    app_secret: Optional[str] = None   # 飞书应用 App Secret
    receive_id_type: str = "open_id"   # 用户 ID 类型: open_id | union_id | user_id | email
    
    # 默认来源
    default_source: str = "default"  # 消息来源标识
    
    # 模板配置
    template_dir: Optional[Path] = None  # 自定义模板目录
    enable_hot_reload: bool = True  # 是否启用模板热加载
    
    # 去重配置
    enable_dedup: bool = True  # 是否启用去重
    dedup_ttl_seconds: int = 300  # 去重 TTL (秒)
    dedup_backend: str = "memory"  # 去重后端: memory | redis
    
    # 限流配置
    enable_rate_limit: bool = True  # 是否启用限流
    rate_limit_window: int = 60  # 限流窗口 (秒)
    rate_limit_max_count: int = 10  # 窗口内最大消息数
    
    # 重试配置
    max_retries: int = 3  # 最大重试次数
    retry_delay: float = 1.0  # 重试延迟 (秒)
    
    # 超时配置
    timeout_seconds: float = 10.0  # HTTP 请求超时
    
    # 日志配置
    enable_logging: bool = True  # 是否启用日志
    log_level: str = "INFO"  # 日志级别
    
    # 默认 @ 配置
    default_mentions: List[str] = field(default_factory=list)  # 默认 @ 的用户
    critical_mention_all: bool = True  # CRITICAL 级别是否默认 @ 所有人
    
    # Redis 配置 (可选)
    redis_url: Optional[str] = None  # Redis URL (用于分布式去重/限流)
    
    def __post_init__(self):
        """从环境变量读取配置"""
        # Webhook URL
        if self.webhook_url is None:
            self.webhook_url = os.environ.get("FEISHU_WEBHOOK")

        # 飞书应用凭证
        if self.app_id is None:
            self.app_id = os.environ.get("FEISHU_APP_ID")
        if self.app_secret is None:
            self.app_secret = os.environ.get("FEISHU_APP_SECRET")
        
        # 默认来源
        if env_source := os.environ.get("FEISHU_SOURCE"):
            self.default_source = env_source
        
        # Redis URL
        if self.redis_url is None:
            self.redis_url = os.environ.get("FEISHU_REDIS_URL")
        
        # 模板目录
        if self.template_dir is None:
            if env_template_dir := os.environ.get("FEISHU_TEMPLATE_DIR"):
                self.template_dir = Path(env_template_dir)
    
    @classmethod
    def from_env(cls) -> "NotifyConfig":
        """从环境变量创建配置"""
        return cls()
    
    @classmethod
    def from_dict(cls, config_dict: Dict) -> "NotifyConfig":
        """从字典创建配置"""
        return cls(**{k: v for k, v in config_dict.items() if hasattr(cls, k)})
    
    def validate(self) -> bool:
        """验证配置有效性"""
        has_webhook = bool(self.webhook_url)
        has_app = bool(self.app_id and self.app_secret)
        if not has_webhook and not has_app:
            raise ValueError(
                "至少需要配置 webhook_url 或 app_id+app_secret。"
                "可通过参数传入或设置环境变量 FEISHU_WEBHOOK / FEISHU_APP_ID+FEISHU_APP_SECRET。"
            )
        return True
