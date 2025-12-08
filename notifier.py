"""
飞书通知器主入口

提供简洁易用的 API，支持快捷方法和高级配置
"""

import logging
from typing import Any, Dict, List, Optional, Union

from config import NotifyConfig
from core.builder import FeishuCardBuilder
from core.dedup import DedupManager, MessageFilter, RateLimiter
from core.sender import FeishuSender, SendResult
from core.types import LinkButton, NotifyLevel, NotifyMessage
from templates.loader import TemplateLoader


logger = logging.getLogger(__name__)


class Notifier:
    """
    飞书通知器
    
    集成消息构建、去重、限流、发送等全部功能
    提供简洁的快捷方法，支持同步和异步发送
    
    Usage:
        # 快捷方式
        notifier = Notifier(webhook="https://...")
        await notifier.error("任务失败", error_msg="...")
        await notifier.success("任务完成", metrics={"rows": 1000})
        
        # 高级用法
        msg = NotifyMessage(level=NotifyLevel.CRITICAL, title="紧急", content="...")
        await notifier.send(msg)
    """
    
    def __init__(
        self,
        webhook: Optional[str] = None,
        source: str = "default",
        config: Optional[NotifyConfig] = None,
        enable_dedup: bool = True,
        enable_rate_limit: bool = True,
    ):
        """
        初始化通知器
        
        Args:
            webhook: 飞书机器人 Webhook URL
            source: 消息来源标识
            config: 配置对象，None 则使用默认配置
            enable_dedup: 是否启用去重
            enable_rate_limit: 是否启用限流
        """
        # 配置
        self.config = config or NotifyConfig()
        if webhook:
            self.config.webhook_url = webhook
        self.config.default_source = source
        
        # 验证配置
        self.config.validate()
        
        # 发送器
        self._sender = FeishuSender(
            webhook_url=self.config.webhook_url,
            timeout=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
            retry_delay=self.config.retry_delay,
        )
        
        # 模板加载器
        self._template_loader = TemplateLoader(
            template_dir=self.config.template_dir,
            enable_hot_reload=self.config.enable_hot_reload,
        )
        
        # 消息过滤器（去重+限流）
        dedup_manager = DedupManager(ttl_seconds=self.config.dedup_ttl_seconds) if enable_dedup else None
        rate_limiter = RateLimiter(
            window_seconds=self.config.rate_limit_window,
            max_count=self.config.rate_limit_max_count,
        ) if enable_rate_limit else None
        
        self._filter = MessageFilter(
            dedup_manager=dedup_manager,
            rate_limiter=rate_limiter,
            enable_dedup=enable_dedup,
            enable_rate_limit=enable_rate_limit,
        )
        
        self._source = source
    
    def _create_message(
        self,
        level: NotifyLevel,
        title: str,
        content: str = "",
        **kwargs
    ) -> NotifyMessage:
        """创建消息对象"""
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
        
        return NotifyMessage(
            level=level,
            title=title,
            content=content,
            source=kwargs.pop("source", self._source),
            links=links,
            **kwargs
        )
    
    def send(self, message: NotifyMessage, force: bool = False) -> SendResult:
        """
        同步发送消息
        
        Args:
            message: 消息对象
            force: 是否强制发送（跳过去重/限流检查）
            
        Returns:
            发送结果
        """
        # 检查是否应该发送
        if not force:
            should_send, reason = self._filter.should_send(message)
            if not should_send:
                logger.info(f"消息被过滤: {reason}")
                return SendResult(success=False, message=reason)
        
        # 处理 CRITICAL 级别的默认 @ 所有人
        if message.level == NotifyLevel.CRITICAL and self.config.critical_mention_all:
            if not message.mention_all and not message.mentions:
                message.mention_all = True
        
        # 发送
        result = self._sender.send(message)
        
        # 标记已发送
        if result.success:
            self._filter.mark_sent(message)
        
        return result
    
    async def send_async(self, message: NotifyMessage, force: bool = False) -> SendResult:
        """
        异步发送消息
        
        Args:
            message: 消息对象
            force: 是否强制发送（跳过去重/限流检查）
            
        Returns:
            发送结果
        """
        # 检查是否应该发送
        if not force:
            should_send, reason = self._filter.should_send(message)
            if not should_send:
                logger.info(f"消息被过滤: {reason}")
                return SendResult(success=False, message=reason)
        
        # 处理 CRITICAL 级别的默认 @ 所有人
        if message.level == NotifyLevel.CRITICAL and self.config.critical_mention_all:
            if not message.mention_all and not message.mentions:
                message.mention_all = True
        
        # 发送
        result = await self._sender.send_async(message)
        
        # 标记已发送
        if result.success:
            self._filter.mark_sent(message)
        
        return result
    
    # ==================== 快捷方法 ====================
    
    def critical(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """
        同步发送紧急告警 (CRITICAL)
        
        Args:
            title: 标题
            content: 内容
            **kwargs: 其他消息参数
        """
        message = self._create_message(NotifyLevel.CRITICAL, title, content, **kwargs)
        return self.send(message, force=True)  # 紧急消息强制发送
    
    async def critical_async(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """异步发送紧急告警 (CRITICAL)"""
        message = self._create_message(NotifyLevel.CRITICAL, title, content, **kwargs)
        return await self.send_async(message, force=True)
    
    def error(
        self,
        title: str,
        error_msg: str = "",
        **kwargs
    ) -> SendResult:
        """
        同步发送错误通知 (ERROR)
        
        Args:
            title: 标题
            error_msg: 错误信息
            **kwargs: 其他消息参数
        """
        kwargs["error_msg"] = error_msg
        content = kwargs.pop("content", error_msg or "")
        message = self._create_message(NotifyLevel.ERROR, title, content, **kwargs)
        return self.send(message)
    
    async def error_async(
        self,
        title: str,
        error_msg: str = "",
        **kwargs
    ) -> SendResult:
        """异步发送错误通知 (ERROR)"""
        kwargs["error_msg"] = error_msg
        content = kwargs.pop("content", error_msg or "")
        message = self._create_message(NotifyLevel.ERROR, title, content, **kwargs)
        return await self.send_async(message)
    
    def warning(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """
        同步发送警告 (WARNING)
        
        Args:
            title: 标题
            content: 内容
            **kwargs: 其他消息参数
        """
        message = self._create_message(NotifyLevel.WARNING, title, content, **kwargs)
        return self.send(message)
    
    async def warning_async(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """异步发送警告 (WARNING)"""
        message = self._create_message(NotifyLevel.WARNING, title, content, **kwargs)
        return await self.send_async(message)
    
    def success(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """
        同步发送成功通知 (SUCCESS)
        
        Args:
            title: 标题
            content: 内容
            **kwargs: 其他消息参数
        """
        message = self._create_message(NotifyLevel.SUCCESS, title, content, **kwargs)
        return self.send(message)
    
    async def success_async(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """异步发送成功通知 (SUCCESS)"""
        message = self._create_message(NotifyLevel.SUCCESS, title, content, **kwargs)
        return await self.send_async(message)
    
    def info(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """
        同步发送信息通知 (INFO)
        
        Args:
            title: 标题
            content: 内容
            **kwargs: 其他消息参数
        """
        message = self._create_message(NotifyLevel.INFO, title, content, **kwargs)
        return self.send(message)
    
    async def info_async(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """异步发送信息通知 (INFO)"""
        message = self._create_message(NotifyLevel.INFO, title, content, **kwargs)
        return await self.send_async(message)
    
    def pending(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """
        同步发送待办通知 (PENDING)
        
        Args:
            title: 标题
            content: 内容
            **kwargs: 其他消息参数
        """
        message = self._create_message(NotifyLevel.PENDING, title, content, **kwargs)
        return self.send(message)
    
    async def pending_async(
        self,
        title: str,
        content: str = "",
        **kwargs
    ) -> SendResult:
        """异步发送待办通知 (PENDING)"""
        message = self._create_message(NotifyLevel.PENDING, title, content, **kwargs)
        return await self.send_async(message)
    
    # ==================== 自定义模板方法 ====================
    
    def custom(
        self,
        template_name: str,
        title: str,
        content: str = "",
        level: Optional[NotifyLevel] = None,
        **kwargs
    ) -> SendResult:
        """
        使用自定义模板发送消息
        
        Args:
            template_name: 模板名称（对应 templates/custom/{template_name}.json）
            title: 标题
            content: 内容
            level: 消息级别，None 则使用模板中的 default_level
            **kwargs: 其他消息参数
        """
        # 如果没有指定级别，从模板获取默认级别
        if level is None:
            level = self._template_loader.get_custom_template_level(template_name)
        
        message = self._create_message(level, title, content, **kwargs)
        
        # 使用自定义模板渲染
        card = self._template_loader.render_custom(template_name, message)
        if card:
            payload = {"msg_type": "interactive", "card": card}
            return self._sender.send_raw(payload)
        else:
            # 模板不存在，回退到默认构建器
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
            payload = {"msg_type": "interactive", "card": card}
            return await self._sender.send_raw_async(payload)
        else:
            return await self.send_async(message)
    
    def __getattr__(self, name: str):
        """
        动态方法调用 - 支持自定义模板热插拔
        
        例如: notifier.timeout_warning("标题") 
        会自动加载 templates/custom/timeout_warning.json 模板
        颜色等样式由模板中的 default_level 决定，也可以调用时覆盖
        """
        # 排除内部属性
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        # 检查是否是异步方法
        is_async = name.endswith("_async")
        template_name = name[:-6] if is_async else name  # 去掉 _async 后缀
        
        # 检查模板是否存在
        if self._template_loader.has_template(template_name):
            if is_async:
                async def async_method(title: str, content: str = "", level: Optional[NotifyLevel] = None, **kwargs):
                    return await self.custom_async(template_name, title, content, level, **kwargs)
                return async_method
            else:
                def sync_method(title: str, content: str = "", level: Optional[NotifyLevel] = None, **kwargs):
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
    """
    获取默认通知器实例
    
    首次调用时创建，后续调用返回同一实例
    """
    global _default_notifier
    
    if _default_notifier is None:
        _default_notifier = Notifier(webhook=webhook, source=source)
    
    return _default_notifier


def set_default_notifier(notifier: Notifier):
    """设置默认通知器"""
    global _default_notifier
    _default_notifier = notifier

