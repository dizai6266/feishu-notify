"""
飞书通知器主入口

提供简洁易用的 API，支持快捷方法和高级配置
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from feishu_notify.config import NotifyConfig
from feishu_notify.core.dedup import DedupManager, MessageFilter, RateLimiter
from feishu_notify.core.sender import FeishuSender, SendResult
from feishu_notify.core.types import LinkButton, NotifyLevel, NotifyMessage
from feishu_notify.templates.loader import TemplateLoader


logger = logging.getLogger(__name__)


class Notifier:
    """
    飞书通知器

    集成消息构建、去重、限流、发送等全部功能
    提供简洁的快捷方法，支持同步和异步发送

    Usage:
        notifier = Notifier(webhook="https://...")
        notifier.error("任务失败", error_msg="...")
        await notifier.success_async("任务完成", metrics={"rows": 1000})
    """

    def __init__(
        self,
        webhook: Optional[str] = None,
        source: str = "default",
        config: Optional[NotifyConfig] = None,
        enable_dedup: bool = True,
        enable_rate_limit: bool = True,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        # 配置
        self.config = config or NotifyConfig()
        if webhook:
            self.config.webhook_url = webhook
        if app_id:
            self.config.app_id = app_id
        if app_secret:
            self.config.app_secret = app_secret
        self.config.default_source = source
        self.config.validate()

        # 模板加载器
        self._template_loader = TemplateLoader(
            template_dir=self.config.template_dir,
            enable_hot_reload=self.config.enable_hot_reload,
        )

        # 发送器（传入 template_loader 实现统一构建）
        self._sender = FeishuSender(
            webhook_url=self.config.webhook_url or "",
            app_id=self.config.app_id,
            app_secret=self.config.app_secret,
            receive_id_type=self.config.receive_id_type,
            timeout=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
            retry_delay=self.config.retry_delay,
            template_loader=self._template_loader,
        )

        # 消息过滤器（去重+限流）
        dedup_manager = (
            DedupManager(ttl_seconds=self.config.dedup_ttl_seconds)
            if enable_dedup else None
        )
        rate_limiter = (
            RateLimiter(
                window_seconds=self.config.rate_limit_window,
                max_count=self.config.rate_limit_max_count,
            )
            if enable_rate_limit else None
        )
        self._filter = MessageFilter(
            dedup_manager=dedup_manager,
            rate_limiter=rate_limiter,
            enable_dedup=enable_dedup,
            enable_rate_limit=enable_rate_limit,
        )

        self._source = source

    # ==================== 内部：消息构建 ====================

    # NotifyMessage 已知字段集合（排除 level/title/content/source/links，这些单独处理）
    _MSG_FIELDS = frozenset({
        "task_name", "task_id", "timestamp", "start_time", "end_time",
        "duration", "error_msg", "error_code", "metrics", "mentions",
        "mention_all", "dedupe_key", "extra", "to_user", "to_users",
    })

    def _create_message(
        self,
        level: NotifyLevel,
        title: str,
        content: str = "",
        **kwargs
    ) -> NotifyMessage:
        """创建消息对象，未知参数自动收集到 extra 字典"""
        # 处理 links 参数
        links = kwargs.pop("links", None)
        if links:
            if isinstance(links[0], dict):
                links = [
                    LinkButton(
                        text=link.get("text", "查看详情"),
                        url=link.get("url", ""),
                        is_danger=link.get("is_danger", False),
                    )
                    for link in links
                ]
        else:
            links = []

        # 处理单个 link 快捷参数
        if "link_url" in kwargs:
            link_url = kwargs.pop("link_url")
            link_text = kwargs.pop("link_text", "查看详情")
            links.append(LinkButton(text=link_text, url=link_url))

        source = kwargs.pop("source", self._source)

        # 分离已知字段和未知字段，未知字段放入 extra
        msg_kwargs = {}
        extra_kwargs = kwargs.pop("extra", None) or {}
        for key in list(kwargs):
            if key in self._MSG_FIELDS:
                msg_kwargs[key] = kwargs.pop(key)
            else:
                extra_kwargs[key] = kwargs.pop(key)

        if extra_kwargs:
            msg_kwargs["extra"] = extra_kwargs

        return NotifyMessage(
            level=level,
            title=title,
            content=content,
            source=source,
            links=links,
            **msg_kwargs
        )

    # ==================== 内部：发送前后处理 ====================

    def _prepare_send(
        self, message: NotifyMessage, force: bool
    ) -> Tuple[bool, Optional[SendResult]]:
        """发送前检查（过滤 + CRITICAL @all）。返回 (是否继续, 提前返回结果)"""
        if not force:
            should_send, reason = self._filter.should_send(message)
            if not should_send:
                logger.info(f"消息被过滤: {reason}")
                return False, SendResult(success=False, message=reason)

        if message.level == NotifyLevel.CRITICAL and self.config.critical_mention_all:
            if not message.mention_all and not message.mentions:
                message.mention_all = True

        return True, None

    def _route_send(self, message: NotifyMessage) -> SendResult:
        """同步路由发送"""
        if message.to_users:
            results = self._sender.send_to_users(message, message.to_users)
            all_success = all(r.success for r in results)
            return SendResult(
                success=all_success,
                message="; ".join(r.message for r in results),
            )
        elif message.to_user:
            return self._sender.send_to_user(message, message.to_user)
        else:
            return self._sender.send(message)

    async def _route_send_async(self, message: NotifyMessage) -> SendResult:
        """异步路由发送"""
        if message.to_users:
            results = await self._sender.send_to_users_async(message, message.to_users)
            all_success = all(r.success for r in results)
            return SendResult(
                success=all_success,
                message="; ".join(r.message for r in results),
            )
        elif message.to_user:
            return await self._sender.send_to_user_async(message, message.to_user)
        else:
            return await self._sender.send_async(message)

    def _finalize_send(self, message: NotifyMessage, result: SendResult) -> SendResult:
        """发送后处理"""
        if result.success:
            self._filter.mark_sent(message)
        return result

    # ==================== 公开：发送 ====================

    def send(self, message: NotifyMessage, force: bool = False) -> SendResult:
        """同步发送消息"""
        proceed, early = self._prepare_send(message, force)
        if not proceed:
            return early  # type: ignore[return-value]
        return self._finalize_send(message, self._route_send(message))

    async def send_async(self, message: NotifyMessage, force: bool = False) -> SendResult:
        """异步发送消息"""
        proceed, early = self._prepare_send(message, force)
        if not proceed:
            return early  # type: ignore[return-value]
        return self._finalize_send(message, await self._route_send_async(message))

    # ==================== 快捷方法 ====================

    def _quick_send(
        self, level: NotifyLevel, title: str, content: str = "",
        force: bool = False, **kwargs
    ) -> SendResult:
        message = self._create_message(level, title, content, **kwargs)
        return self.send(message, force=force)

    async def _quick_send_async(
        self, level: NotifyLevel, title: str, content: str = "",
        force: bool = False, **kwargs
    ) -> SendResult:
        message = self._create_message(level, title, content, **kwargs)
        return await self.send_async(message, force=force)

    def critical(self, title: str, content: str = "", **kwargs) -> SendResult:
        """同步发送紧急告警 (CRITICAL)，强制发送"""
        return self._quick_send(NotifyLevel.CRITICAL, title, content, force=True, **kwargs)

    async def critical_async(self, title: str, content: str = "", **kwargs) -> SendResult:
        """异步发送紧急告警 (CRITICAL)，强制发送"""
        return await self._quick_send_async(
            NotifyLevel.CRITICAL, title, content, force=True, **kwargs
        )

    def error(self, title: str, error_msg: str = "", **kwargs) -> SendResult:
        """同步发送错误通知 (ERROR)"""
        kwargs["error_msg"] = error_msg
        content = kwargs.pop("content", error_msg or "")
        return self._quick_send(NotifyLevel.ERROR, title, content, **kwargs)

    async def error_async(self, title: str, error_msg: str = "", **kwargs) -> SendResult:
        """异步发送错误通知 (ERROR)"""
        kwargs["error_msg"] = error_msg
        content = kwargs.pop("content", error_msg or "")
        return await self._quick_send_async(NotifyLevel.ERROR, title, content, **kwargs)

    def warning(self, title: str, content: str = "", **kwargs) -> SendResult:
        """同步发送警告 (WARNING)"""
        return self._quick_send(NotifyLevel.WARNING, title, content, **kwargs)

    async def warning_async(self, title: str, content: str = "", **kwargs) -> SendResult:
        """异步发送警告 (WARNING)"""
        return await self._quick_send_async(NotifyLevel.WARNING, title, content, **kwargs)

    def success(self, title: str, content: str = "", **kwargs) -> SendResult:
        """同步发送成功通知 (SUCCESS)"""
        return self._quick_send(NotifyLevel.SUCCESS, title, content, **kwargs)

    async def success_async(self, title: str, content: str = "", **kwargs) -> SendResult:
        """异步发送成功通知 (SUCCESS)"""
        return await self._quick_send_async(NotifyLevel.SUCCESS, title, content, **kwargs)

    def info(self, title: str, content: str = "", **kwargs) -> SendResult:
        """同步发送信息通知 (INFO)"""
        return self._quick_send(NotifyLevel.INFO, title, content, **kwargs)

    async def info_async(self, title: str, content: str = "", **kwargs) -> SendResult:
        """异步发送信息通知 (INFO)"""
        return await self._quick_send_async(NotifyLevel.INFO, title, content, **kwargs)

    def pending(self, title: str, content: str = "", **kwargs) -> SendResult:
        """同步发送待办通知 (PENDING)"""
        return self._quick_send(NotifyLevel.PENDING, title, content, **kwargs)

    async def pending_async(self, title: str, content: str = "", **kwargs) -> SendResult:
        """异步发送待办通知 (PENDING)"""
        return await self._quick_send_async(NotifyLevel.PENDING, title, content, **kwargs)

    # ==================== 自定义模板方法 ====================

    def _send_custom_card(
        self, card: Dict[str, Any], message: NotifyMessage
    ) -> SendResult:
        """同步发送自定义模板卡片，根据 to_user/to_users 路由"""
        if message.to_users:
            results = [
                self._sender._send_card_to_user(card, uid)
                for uid in message.to_users
            ]
            all_ok = all(r.success for r in results)
            return SendResult(success=all_ok, message="; ".join(r.message for r in results))
        elif message.to_user:
            return self._sender._send_card_to_user(card, message.to_user)
        else:
            return self._sender.send_raw({"msg_type": "interactive", "card": card})

    async def _send_custom_card_async(
        self, card: Dict[str, Any], message: NotifyMessage
    ) -> SendResult:
        """异步发送自定义模板卡片，根据 to_user/to_users 路由"""
        if message.to_users:
            results = await asyncio.gather(*[
                self._sender._send_card_to_user_async(card, uid)
                for uid in message.to_users
            ])
            all_ok = all(r.success for r in results)
            return SendResult(success=all_ok, message="; ".join(r.message for r in results))
        elif message.to_user:
            return await self._sender._send_card_to_user_async(card, message.to_user)
        else:
            return await self._sender.send_raw_async({"msg_type": "interactive", "card": card})

    def custom(
        self,
        template_name: str,
        title: str,
        content: str = "",
        level: Optional[NotifyLevel] = None,
        **kwargs
    ) -> SendResult:
        """使用自定义模板发送消息"""
        if level is None:
            level = self._template_loader.get_custom_template_level(template_name)

        message = self._create_message(level, title, content, **kwargs)

        card = self._template_loader.render_custom(template_name, message)
        if card:
            return self._send_custom_card(card, message)
        else:
            return self.send(message)

    async def custom_async(
        self,
        template_name: str,
        title: str,
        content: str = "",
        level: Optional[NotifyLevel] = None,
        **kwargs
    ) -> SendResult:
        """异步使用自定义模板发送消息"""
        if level is None:
            level = self._template_loader.get_custom_template_level(template_name)

        message = self._create_message(level, title, content, **kwargs)

        card = self._template_loader.render_custom(template_name, message)
        if card:
            return await self._send_custom_card_async(card, message)
        else:
            return await self.send_async(message)

    def __getattr__(self, name: str):
        """动态方法调用 - 支持自定义模板热插拔"""
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        is_async = name.endswith("_async")
        template_name = name[:-6] if is_async else name

        if self._template_loader.has_template(template_name):
            if is_async:
                async def async_method(
                    title: str, content: str = "",
                    level: Optional[NotifyLevel] = None, **kwargs
                ):
                    return await self.custom_async(template_name, title, content, level, **kwargs)
                return async_method
            else:
                def sync_method(
                    title: str, content: str = "",
                    level: Optional[NotifyLevel] = None, **kwargs
                ):
                    return self.custom(template_name, title, content, level, **kwargs)
                return sync_method

        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    # ==================== 工具方法 ====================

    def reload_templates(self):
        """重新加载模板"""
        self._template_loader.reload()

    def close(self):
        """关闭资源"""
        self._sender.close()

    async def close_async(self):
        """异步关闭资源"""
        await self._sender.close_async()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_async()


# ==================== 便捷函数 ====================

_default_notifier: Optional[Notifier] = None


def get_notifier(
    webhook: Optional[str] = None,
    source: str = "default",
) -> Notifier:
    """获取默认通知器实例（首次调用时创建）"""
    global _default_notifier
    if _default_notifier is None:
        _default_notifier = Notifier(webhook=webhook, source=source)
    return _default_notifier


def set_default_notifier(notifier: Notifier):
    """设置默认通知器"""
    global _default_notifier
    _default_notifier = notifier
