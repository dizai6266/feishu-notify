"""
飞书通知工具 - 一个热插拔、灵活、易用的飞书卡片通知库

Usage:
    from feishu_notify import Notifier
    from feishu_notify.core.types import NotifyLevel, NotifyMessage

    # 快捷方式
    notifier = Notifier(webhook="https://...")
    await notifier.error("任务失败", error_msg="...")
    await notifier.success("任务完成")

    # 高级用法
    msg = NotifyMessage(level=NotifyLevel.CRITICAL, title="紧急", content="...")
    await notifier.send(msg)
"""

from importlib.metadata import version, PackageNotFoundError

from feishu_notify.core.types import NotifyLevel, NotifyMessage, LinkButton
from feishu_notify.core.builder import FeishuCardBuilder
from feishu_notify.core.sender import FeishuSender
from feishu_notify.core.dedup import DedupManager, RateLimiter
from feishu_notify.templates.loader import TemplateLoader
from feishu_notify.config import NotifyConfig
from feishu_notify.notifier import Notifier

try:
    __version__ = version("feishu-notify")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
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
