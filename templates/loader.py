"""
模板加载器

支持:
- 级别配置自动加载（颜色、emoji 等）
- 默认模板 + 自定义模板分离
- 模板热加载
- Jinja2 变量渲染
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, BaseLoader, TemplateNotFound

from core.types import NotifyLevel, NotifyMessage


# 目录路径
TEMPLATES_DIR = Path(__file__).parent
BASE_TEMPLATES_DIR = TEMPLATES_DIR / "base"
CUSTOM_TEMPLATES_DIR = TEMPLATES_DIR / "custom"
# 兼容旧版本
LEGACY_CARDS_DIR = TEMPLATES_DIR / "cards"


class DictLoader(BaseLoader):
    """从字典加载模板的 Jinja2 Loader"""
    
    def __init__(self, templates: Dict[str, str]):
        self.templates = templates
    
    def get_source(self, environment, template):
        if template in self.templates:
            source = self.templates[template]
            return source, template, lambda: True
        raise TemplateNotFound(template)


class TemplateLoader:
    """
    模板加载器
    
    架构:
    - templates/base/     : 6 个级别的默认模板（可自定义修改）
    - templates/custom/   : 用户自定义模板
    - config/levels.json  : 级别配置（颜色、emoji、前缀）
    """
    
    def __init__(
        self,
        template_dir: Optional[Path] = None,
        enable_hot_reload: bool = True,
        reload_interval: float = 5.0,
    ):
        self.base_dir = BASE_TEMPLATES_DIR
        self.custom_dir = template_dir or CUSTOM_TEMPLATES_DIR
        self.enable_hot_reload = enable_hot_reload
        self.reload_interval = reload_interval
        
        self._base_templates: Dict[str, Dict[str, Any]] = {}
        self._custom_templates: Dict[str, Dict[str, Any]] = {}
        self._template_mtimes: Dict[str, float] = {}
        self._lock = threading.RLock()
        
        # 初始加载
        self._load_all_templates()
        
        # 启动热重载监控
        if enable_hot_reload:
            self._start_reload_watcher()
    
    def _load_all_templates(self):
        """加载所有模板"""
        with self._lock:
            # 加载默认模板
            for level in NotifyLevel:
                self._load_base_template(level.name.lower())
            
            # 加载自定义模板
            self._scan_custom_templates()
    
    def _load_base_template(self, name: str):
        """加载默认模板"""
        template_path = self.base_dir / f"{name}.json"
        
        if template_path.exists():
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data.pop("_comment", None)
                    self._base_templates[name] = data
                self._template_mtimes[f"base:{name}"] = template_path.stat().st_mtime
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to load base template {name}: {e}")
    
    def _scan_custom_templates(self):
        """扫描并加载所有自定义模板"""
        # 扫描 custom 目录
        if self.custom_dir.exists():
            for template_file in self.custom_dir.glob("*.json"):
                name = template_file.stem
                self._load_custom_template(name, template_file)
        
        # 兼容旧版本：扫描 cards 目录
        if LEGACY_CARDS_DIR.exists():
            for template_file in LEGACY_CARDS_DIR.glob("*.json"):
                name = template_file.stem
                # 跳过 6 个默认级别的模板（已迁移到 base/）
                if name.lower() not in [l.name.lower() for l in NotifyLevel]:
                    self._load_custom_template(name, template_file)
    
    def _load_custom_template(self, name: str, path: Path):
        """加载单个自定义模板"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.pop("_comment", None)
                self._custom_templates[name] = data
            self._template_mtimes[f"custom:{name}"] = path.stat().st_mtime
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load custom template {name}: {e}")
    
    def _start_reload_watcher(self):
        """启动热重载监控线程"""
        def watcher():
            while True:
                time.sleep(self.reload_interval)
                self._check_and_reload()
        
        thread = threading.Thread(target=watcher, daemon=True)
        thread.start()
    
    def _check_and_reload(self):
        """检查文件变更并重载"""
        with self._lock:
            # 检查默认模板
            for name in list(self._base_templates.keys()):
                template_path = self.base_dir / f"{name}.json"
                if template_path.exists():
                    current_mtime = template_path.stat().st_mtime
                    key = f"base:{name}"
                    if current_mtime > self._template_mtimes.get(key, 0):
                        self._load_base_template(name)
            
            # 检查自定义模板
            self._scan_custom_templates()
    
    def has_template(self, name: str) -> bool:
        """检查模板是否存在"""
        # 检查是否是默认级别
        if name.upper() in [l.name for l in NotifyLevel]:
            return True
        
        # 检查自定义模板
        with self._lock:
            if name in self._custom_templates:
                return True
        
        # 检查文件是否存在
        custom_path = self.custom_dir / f"{name}.json"
        if custom_path.exists():
            self._load_custom_template(name, custom_path)
            return True
        
        # 兼容旧版本
        legacy_path = LEGACY_CARDS_DIR / f"{name}.json"
        if legacy_path.exists():
            self._load_custom_template(name, legacy_path)
            return True
        
        return False
    
    def get_base_template(self, level: NotifyLevel) -> Dict[str, Any]:
        """获取默认模板"""
        name = level.name.lower()
        with self._lock:
            return self._base_templates.get(name, {}).copy()
    
    def get_custom_template(self, name: str) -> Optional[Dict[str, Any]]:
        """获取自定义模板"""
        if not self.has_template(name):
            return None
        
        with self._lock:
            return self._custom_templates.get(name, {}).copy()
    
    def get_custom_template_level(self, name: str) -> NotifyLevel:
        """获取自定义模板的默认级别"""
        template = self.get_custom_template(name)
        if template:
            default_level = template.get("default_level", "INFO")
            try:
                return NotifyLevel.from_string(default_level)
            except ValueError:
                pass
        return NotifyLevel.INFO
    
    def render(self, message: NotifyMessage, template_name: Optional[str] = None) -> Dict[str, Any]:
        """
        渲染消息为飞书卡片
        
        Args:
            message: 消息对象
            template_name: 自定义模板名称，None 则使用级别默认模板
        """
        level = message.level
        context = self._build_context(message)
        
        # 获取模板
        if template_name:
            template = self.get_custom_template(template_name)
            if not template:
                template = self.get_base_template(level)
        else:
            template = self.get_base_template(level)
        
        # 构建卡片
        return self._build_card(template, context, level)
    
    def render_custom(self, template_name: str, message: NotifyMessage) -> Optional[Dict[str, Any]]:
        """使用自定义模板渲染"""
        template = self.get_custom_template(template_name)
        if not template:
            return None
        
        context = self._build_context(message)
        return self._build_card(template, context, message.level)
    
    def _build_context(self, message: NotifyMessage) -> Dict[str, Any]:
        """构建模板渲染上下文"""
        return {
            "level": message.level.name,
            "level_color": message.level.color,
            "level_emoji": message.level.emoji,
            "level_prefix": message.level.prefix,
            "title": message.title,
            "formatted_title": message.formatted_title,
            "content": message.content or "",
            "source": message.source or "",
            "task_name": message.task_name or "",
            "task_id": message.task_id or "",
            "timestamp": message.formatted_timestamp,
            "start_time": message.start_time or "",
            "end_time": message.end_time or "",
            "duration": message.duration or "",
            "error_msg": message.error_msg or "",
            "error_code": message.error_code or "",
            "metrics": message.metrics or {},
            "links": [link.to_dict() for link in message.links],
            "mentions": message.mentions,
            "mention_all": message.mention_all,
            "extra": message.extra or {},
        }
    
    def _build_card(
        self, 
        template: Dict[str, Any], 
        context: Dict[str, Any],
        level: NotifyLevel
    ) -> Dict[str, Any]:
        """根据模板构建飞书卡片"""
        
        # 获取自定义标题前缀
        title_prefix = template.get("title_prefix")
        if title_prefix:
            title_content = self._render_string(f"{title_prefix} {{{{ title }}}}", context)
        else:
            title_content = f"{level.emoji} {level.prefix} {context['title']}"
        
        # 构建 header
        card = {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True,
            },
            "header": {
                "template": level.color,
                "title": {
                    "tag": "plain_text",
                    "content": title_content,
                },
            },
            "elements": [],
        }
        
        # 构建 elements
        elements = template.get("elements", [])
        for element in elements:
            built = self._build_element(element, context)
            if built:
                if isinstance(built, list):
                    card["elements"].extend(built)
                else:
                    card["elements"].append(built)
        
        # 添加分割线
        if card["elements"]:
            card["elements"].append({"tag": "hr"})
        
        # 添加 footer
        footer_note = template.get("footer_note")
        if footer_note:
            rendered_note = self._render_string(footer_note, context)
            card["elements"].append({
                "tag": "note",
                "elements": [
                    {"tag": "lark_md", "content": f"{rendered_note} | 来自 {context['source']}"}
                ],
            })
        else:
            card["elements"].append({
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": f"来自 {context['source']}"}
                ],
            })
        
        return card
    
    def _build_element(self, element: Dict[str, Any], context: Dict[str, Any]) -> Optional[Any]:
        """构建单个元素"""
        tag = element.get("tag")
        
        # 检查条件
        condition = element.get("condition")
        if condition:
            rendered = self._render_string(condition, context)
            if not rendered or rendered in ("", "[]", "{}", "None", "False"):
                return None
        
        if tag == "markdown":
            content = self._render_string(element.get("content", ""), context)
            if content:
                return {"tag": "markdown", "content": content}
        
        elif tag == "div":
            fields = element.get("fields", [])
            built_fields = []
            for field in fields:
                key = field.get("key", "")
                value = self._render_string(field.get("value", ""), context)
                if value and value != "-":
                    built_fields.append({
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{key}**\n{value}",
                        },
                    })
            if built_fields:
                return {"tag": "div", "fields": built_fields}
        
        elif tag == "error_block":
            error_msg = context.get("error_msg", "")
            error_code = context.get("error_code", "")
            if error_msg:
                content = ""
                if error_code:
                    content += f"**错误代码** `{error_code}`\n\n"
                content += f"**错误信息**\n```\n{error_msg}\n```"
                return {"tag": "markdown", "content": content}
        
        elif tag == "metrics_block":
            metrics = context.get("metrics", {})
            if metrics:
                lines = ["**指标数据**"]
                for key, value in metrics.items():
                    if isinstance(value, int) and value >= 1000:
                        formatted_value = f"{value:,}"
                    else:
                        formatted_value = str(value)
                    lines.append(f"• {key}: {formatted_value}")
                return {"tag": "markdown", "content": "\n".join(lines)}
        
        elif tag == "extra_fields":
            extra = context.get("extra", {})
            if extra:
                fields = []
                for key, value in extra.items():
                    fields.append({
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{key}**\n{value}",
                        },
                    })
                if fields:
                    return {"tag": "div", "fields": fields}
        
        elif tag == "actions":
            links = context.get("links", [])
            if links:
                actions = []
                for i, link in enumerate(links):
                    button_type = "danger" if link.get("is_danger") else ("primary" if i == 0 else "default")
                    actions.append({
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": link.get("text", "查看详情")},
                        "type": button_type,
                        "url": link.get("url", ""),
                    })
                return {"tag": "action", "actions": actions}
        
        return None
    
    def _render_string(self, template_str: str, context: Dict[str, Any]) -> str:
        """渲染字符串中的 Jinja2 变量"""
        if "{{" not in template_str:
            return template_str
        
        try:
            env = Environment(loader=DictLoader({"t": template_str}))
            return env.get_template("t").render(context)
        except Exception:
            return template_str
    
    def list_templates(self) -> Dict[str, List[str]]:
        """列出所有可用模板"""
        result = {
            "base": [l.name.lower() for l in NotifyLevel],
            "custom": [],
        }
        
        with self._lock:
            result["custom"] = list(self._custom_templates.keys())
        
        return result
    
    def reload(self):
        """手动重载所有模板"""
        self._load_all_templates()


# 全局默认模板加载器
_default_loader: Optional[TemplateLoader] = None


def get_default_loader() -> TemplateLoader:
    """获取默认模板加载器"""
    global _default_loader
    if _default_loader is None:
        _default_loader = TemplateLoader()
    return _default_loader


def set_default_loader(loader: TemplateLoader):
    """设置默认模板加载器"""
    global _default_loader
    _default_loader = loader
