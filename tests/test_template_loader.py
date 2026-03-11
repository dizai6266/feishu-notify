"""Tests for TemplateLoader"""

from pathlib import Path

from feishu_card_notify.core.types import NotifyLevel, NotifyMessage
from feishu_card_notify.templates.loader import TemplateLoader


def _make_msg(level=NotifyLevel.INFO, **kwargs):
    defaults = dict(title="Test", content="content", source="test")
    defaults.update(kwargs)
    return NotifyMessage(level=level, **defaults)


class TestTemplateLoader:
    def _loader(self, **kwargs):
        defaults = dict(enable_hot_reload=False)
        defaults.update(kwargs)
        return TemplateLoader(**defaults)

    def test_loads_base_templates(self):
        loader = self._loader()
        for level in NotifyLevel:
            assert loader.has_template(level.name.lower()) or loader.has_template(level.name)

    def test_get_base_template(self):
        loader = self._loader()
        tmpl = loader.get_base_template(NotifyLevel.CRITICAL)
        assert "elements" in tmpl

    def test_has_template_custom(self):
        loader = self._loader()
        # built-in custom templates: timeout_warning, data_quality
        assert loader.has_template("timeout_warning")
        assert loader.has_template("data_quality")

    def test_has_template_nonexistent(self):
        loader = self._loader()
        assert loader.has_template("nonexistent_xyz") is False

    def test_get_custom_template(self):
        loader = self._loader()
        tmpl = loader.get_custom_template("timeout_warning")
        assert tmpl is not None
        assert tmpl.get("default_level") == "WARNING"

    def test_get_custom_template_level(self):
        loader = self._loader()
        level = loader.get_custom_template_level("timeout_warning")
        assert level == NotifyLevel.WARNING

    def test_get_custom_template_level_default(self):
        loader = self._loader()
        level = loader.get_custom_template_level("nonexistent")
        assert level == NotifyLevel.INFO

    def test_render_base(self):
        loader = self._loader()
        msg = _make_msg(level=NotifyLevel.ERROR)
        card = loader.render(msg)
        assert "header" in card
        assert card["header"]["template"] == "orange"
        assert "elements" in card

    def test_render_custom(self):
        loader = self._loader()
        msg = _make_msg(level=NotifyLevel.WARNING, task_name="sync_job", duration="45min")
        card = loader.render_custom("timeout_warning", msg)
        assert card is not None
        assert card["header"]["template"] == "yellow"

    def test_render_custom_nonexistent(self):
        loader = self._loader()
        msg = _make_msg()
        card = loader.render_custom("nonexistent_xyz", msg)
        assert card is None

    def test_render_string_no_template(self):
        loader = self._loader()
        result = loader._render_string("plain text", {})
        assert result == "plain text"

    def test_render_string_with_variables(self):
        loader = self._loader()
        result = loader._render_string("Hello {{ name }}", {"name": "World"})
        assert result == "Hello World"

    def test_render_string_invalid_template(self):
        loader = self._loader()
        result = loader._render_string("{{ invalid.", {})
        assert result == "{{ invalid."

    def test_list_templates(self):
        loader = self._loader()
        templates = loader.list_templates()
        assert "base" in templates
        assert "custom" in templates
        assert "critical" in templates["base"]
        assert len(templates["base"]) == 6

    def test_reload(self):
        loader = self._loader()
        # Should not raise
        loader.reload()

    def test_conditional_element_false(self):
        loader = self._loader()
        element = {"tag": "metrics_block", "condition": "{{ metrics }}"}
        context = {"metrics": {}}
        result = loader._build_element(element, context)
        assert result is None

    def test_conditional_element_true(self):
        loader = self._loader()
        element = {"tag": "metrics_block", "condition": "{{ metrics }}"}
        context = {"metrics": {"rows": 100}}
        result = loader._build_element(element, context)
        assert result is not None

    def test_build_element_markdown(self):
        loader = self._loader()
        element = {"tag": "markdown", "content": "Hello {{ name }}"}
        context = {"name": "World"}
        result = loader._build_element(element, context)
        assert result == {"tag": "markdown", "content": "Hello World"}

    def test_build_element_div(self):
        loader = self._loader()
        element = {
            "tag": "div",
            "fields": [
                {"key": "Source", "value": "{{ source }}"},
            ],
        }
        context = {"source": "Airflow"}
        result = loader._build_element(element, context)
        assert result["tag"] == "div"
        assert len(result["fields"]) == 1

    def test_build_element_error_block(self):
        loader = self._loader()
        element = {"tag": "error_block"}
        context = {"error_msg": "NullPointer", "error_code": "E001"}
        result = loader._build_element(element, context)
        assert result["tag"] == "markdown"
        assert "NullPointer" in result["content"]
        assert "E001" in result["content"]

    def test_build_element_actions(self):
        loader = self._loader()
        element = {"tag": "actions"}
        context = {
            "links": [
                {"text": "View", "url": "https://example.com", "is_danger": False},
            ],
        }
        result = loader._build_element(element, context)
        assert result["tag"] == "action"
        assert len(result["actions"]) == 1

    def test_custom_template_dir(self, tmp_path):
        import json
        template_file = tmp_path / "my_alert.json"
        template_file.write_text(json.dumps({
            "default_level": "ERROR",
            "elements": [
                {"tag": "markdown", "content": "Alert: {{ content }}"},
            ],
        }))
        loader = self._loader(template_dir=tmp_path)
        assert loader.has_template("my_alert")
        level = loader.get_custom_template_level("my_alert")
        assert level == NotifyLevel.ERROR
