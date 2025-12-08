"""
飞书卡片构建器

将 NotifyMessage 转换为飞书卡片 JSON 格式
支持模板渲染和自定义布局
"""

from typing import Any, Dict, List, Optional

from core.types import NotifyLevel, NotifyMessage


class FeishuCardBuilder:
    """
    飞书卡片构建器
    
    将统一消息模型转换为飞书卡片 JSON
    自动根据消息级别选择颜色、Emoji、布局
    """
    
    def __init__(self, message: NotifyMessage):
        """
        初始化构建器
        
        Args:
            message: 消息对象
        """
        self.message = message
        self.level = message.level
    
    def build(self) -> Dict[str, Any]:
        """
        构建完整的飞书卡片 JSON
        
        Returns:
            飞书卡片 JSON 字典
        """
        card = {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True,
            },
            "header": self._build_header(),
            "elements": self._build_elements(),
        }
        return card
    
    def _build_header(self) -> Dict[str, Any]:
        """构建卡片头部"""
        return {
            "template": self.level.color,
            "title": {
                "tag": "plain_text",
                "content": self.message.formatted_title,
            },
        }
    
    def _build_elements(self) -> List[Dict[str, Any]]:
        """构建卡片主体元素"""
        elements = []
        
        # 1. 主要内容
        if self.message.content:
            elements.append({
                "tag": "markdown",
                "content": self.message.content,
            })
        
        # 2. 上下文信息字段
        context_fields = self._build_context_fields()
        if context_fields:
            elements.append({
                "tag": "div",
                "fields": context_fields,
            })
        
        # 3. 错误信息
        if self.message.error_msg:
            elements.append({"tag": "hr"})
            error_content = f"**错误信息**\n```\n{self.message.error_msg}\n```"
            if self.message.error_code:
                error_content = f"**错误代码** `{self.message.error_code}`\n\n" + error_content
            elements.append({
                "tag": "markdown",
                "content": error_content,
            })
        
        # 4. 指标数据
        if self.message.metrics:
            metrics_content = self._format_metrics()
            if metrics_content:
                elements.append({
                    "tag": "markdown",
                    "content": metrics_content,
                })
        
        # 5. 扩展字段
        if self.message.extra:
            extra_fields = self._build_extra_fields()
            if extra_fields:
                elements.append({
                    "tag": "div",
                    "fields": extra_fields,
                })
        
        # 6. 分割线
        if self.message.links or self.message.mentions or self.message.mention_all:
            elements.append({"tag": "hr"})
        
        # 7. 操作按钮
        if self.message.links:
            elements.append(self._build_actions())
        
        # 8. @ 提醒
        at_content = self._build_at_content()
        if at_content:
            elements.append({
                "tag": "markdown",
                "content": at_content,
            })
        
        # 9. 底部备注
        elements.append(self._build_note())
        
        return elements
    
    def _build_context_fields(self) -> List[Dict[str, Any]]:
        """构建上下文字段"""
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
        """格式化指标数据"""
        if not self.message.metrics:
            return None
        
        lines = ["**指标数据**"]
        for key, value in self.message.metrics.items():
            # 格式化常见指标
            if isinstance(value, int) and value >= 1000:
                formatted_value = f"{value:,}"
            else:
                formatted_value = str(value)
            lines.append(f"• {key}: {formatted_value}")
        
        return "\n".join(lines)
    
    def _build_extra_fields(self) -> List[Dict[str, Any]]:
        """构建扩展字段"""
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
        """构建操作按钮"""
        actions = []
        
        for link in self.message.links:
            button_type = "danger" if link.is_danger else "default"
            # 第一个非危险按钮设为 primary
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
        """构建 @ 提醒内容"""
        at_parts = []
        
        if self.message.mention_all:
            at_parts.append("<at id=all></at>")
        
        for user_id in self.message.mentions:
            at_parts.append(f"<at id={user_id}></at>")
        
        if at_parts:
            return " ".join(at_parts)
        return None
    
    def _build_note(self) -> Dict[str, Any]:
        """构建底部备注"""
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
        """
        生成 Webhook 发送的完整 payload
        
        Returns:
            可直接发送给飞书 Webhook 的 JSON
        """
        return {
            "msg_type": "interactive",
            "card": self.build(),
        }


def build_card(message: NotifyMessage) -> Dict[str, Any]:
    """
    便捷函数：构建飞书卡片
    
    Args:
        message: 消息对象
        
    Returns:
        飞书卡片 JSON
    """
    return FeishuCardBuilder(message).build()


def build_webhook_payload(message: NotifyMessage) -> Dict[str, Any]:
    """
    便捷函数：构建 Webhook payload
    
    Args:
        message: 消息对象
        
    Returns:
        Webhook payload JSON
    """
    return FeishuCardBuilder(message).to_webhook_payload()

