"""
飞书通知工具 - 一个热插拔、灵活、易用的飞书卡片通知库

Usage:
    from notifier import Notifier
    from core.types import NotifyLevel, NotifyMessage

    # 快捷方式
    notifier = Notifier(webhook="https://...")
    await notifier.error("任务失败", error_msg="...")
    await notifier.success("任务完成")

    # 高级用法
    msg = NotifyMessage(level=NotifyLevel.CRITICAL, title="紧急", content="...")
    await notifier.send(msg)
"""

from core.types import NotifyLevel, NotifyMessage, LinkButton
from core.builder import FeishuCardBuilder
from core.sender import FeishuSender
from core.dedup import DedupManager, RateLimiter
from templates.loader import TemplateLoader
from config import NotifyConfig
from notifier import Notifier

__version__ = "1.0.0"
__all__ = [
    "Notifier",
    "NotifyLevel",
    "NotifyMessage",
    "LinkButton",
    "FeishuCardBuilder",
    "FeishuSender",
    "DedupManager",
    "RateLimiter",
    "TemplateLoader",
    "NotifyConfig",
]
