"""
飞书卡片构建器

将 NotifyMessage 转换为飞书卡片 JSON 格式
支持模板渲染和自定义布局
"""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from feishu_card_notify.core.types import NotifyLevel, NotifyMessage

if TYPE_CHECKING:
    from feishu_card_notify.templates.loader import TemplateLoader


class FeishuCardBuilder:
    """
    飞书卡片构建器

    将统一消息模型转换为飞书卡片 JSON
    优先使用 TemplateLoader 渲染，无模板时走内置 fallback
    """

    def __init__(
        self,
        message: NotifyMessage,
        template_loader: Optional["TemplateLoader"] = None,
    ):
        self.message = message
        self.level = message.level
        self._loader = template_loader

    def build(self) -> Dict[str, Any]:
        """构建完整的飞书卡片 JSON"""
        # 优先委托 TemplateLoader
        if self._loader:
            card = self._loader.render(self.message)
            if card:
                return card
        # Fallback: 内置构建逻辑
        return self._build_fallback()

    def _build_fallback(self) -> Dict[str, Any]:
        """内置卡片构建（无模板时的 fallback）"""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True,
            },
            "header": self._build_header(),
            "elements": self._build_elements(),
        }

    def _build_header(self) -> Dict[str, Any]:
        return {
            "template": self.level.color,
            "title": {
                "tag": "plain_text",
                "content": self.message.formatted_title,
            },
        }

    def _build_elements(self) -> List[Dict[str, Any]]:
        elements = []

        if self.message.content:
            elements.append({
                "tag": "markdown",
                "content": self.message.content,
            })

        context_fields = self._build_context_fields()
        if context_fields:
            elements.append({
                "tag": "div",
                "fields": context_fields,
            })

        if self.message.error_msg:
            elements.append({"tag": "hr"})
            error_content = f"**错误信息**\n```\n{self.message.error_msg}\n```"
            if self.message.error_code:
                error_content = f"**错误代码** `{self.message.error_code}`\n\n" + error_content
            elements.append({
                "tag": "markdown",
                "content": error_content,
            })

        if self.message.metrics:
            metrics_content = self._format_metrics()
            if metrics_content:
                elements.append({
                    "tag": "markdown",
                    "content": metrics_content,
                })

        if self.message.extra:
            extra_fields = self._build_extra_fields()
            if extra_fields:
                elements.append({
                    "tag": "div",
                    "fields": extra_fields,
                })

        if self.message.links or self.message.mentions or self.message.mention_all:
            elements.append({"tag": "hr"})

        if self.message.links:
            elements.append(self._build_actions())

        at_content = self._build_at_content()
        if at_content:
            elements.append({
                "tag": "markdown",
                "content": at_content,
            })

        elements.append(self._build_note())

        return elements

    def _build_context_fields(self) -> List[Dict[str, Any]]:
        fields = []
        field_mapping = [
            ("来源系统", self.message.source),
            ("任务名称", self.message.task_name),
            ("任务ID", self.message.task_id),
            ("开始时间", self.message.start_time),
            ("结束时间", self.message.end_time),
            ("耗时", self.message.duration),
            ("时间", self.message.formatted_timestamp if not self.message.start_time else None),
        ]
        for label, value in field_mapping:
            if value:
                fields.append({
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{label}**\n{value}",
                    },
                })
        return fields

    def _format_metrics(self) -> Optional[str]:
        if not self.message.metrics:
            return None
        lines = ["**指标数据**"]
        for key, value in self.message.metrics.items():
            if isinstance(value, int) and value >= 1000:
                formatted_value = f"{value:,}"
            else:
                formatted_value = str(value)
            lines.append(f"• {key}: {formatted_value}")
        return "\n".join(lines)

    def _build_extra_fields(self) -> List[Dict[str, Any]]:
        fields = []
        if self.message.extra:
            for key, value in self.message.extra.items():
                fields.append({
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{key}**\n{value}",
                    },
                })
        return fields

    def _build_actions(self) -> Dict[str, Any]:
        actions = []
        for link in self.message.links:
            button_type = "danger" if link.is_danger else "default"
            if not link.is_danger and not any(
                a.get("type") == "primary" for a in actions
            ):
                button_type = "primary"
            actions.append({
                "tag": "button",
                "text": {
                    "tag": "plain_text",
                    "content": link.text,
                },
                "type": button_type,
                "url": link.url,
            })
        return {
            "tag": "action",
            "actions": actions,
        }

    def _build_at_content(self) -> Optional[str]:
        at_parts = []
        if self.message.mention_all:
            at_parts.append("<at id=all></at>")
        for user_id in self.message.mentions:
            at_parts.append(f"<at id={user_id}></at>")
        if at_parts:
            return " ".join(at_parts)
        return None

    def _build_note(self) -> Dict[str, Any]:
        note_text = f"来自 {self.message.source}"
        if self.message.dedupe_key:
            note_text += f" | ID: {self.message.dedupe_key}"
        return {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": note_text,
                },
            ],
        }

    def to_webhook_payload(self) -> Dict[str, Any]:
        return {
            "msg_type": "interactive",
            "card": self.build(),
        }


def build_card(message: NotifyMessage) -> Dict[str, Any]:
    """便捷函数：构建飞书卡片"""
    return FeishuCardBuilder(message).build()


def build_webhook_payload(message: NotifyMessage) -> Dict[str, Any]:
    """便捷函数：构建 Webhook payload"""
    return FeishuCardBuilder(message).to_webhook_payload()
