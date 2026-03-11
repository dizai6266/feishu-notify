"""Tests for FeishuCardBuilder"""

from feishu_card_notify.core.builder import FeishuCardBuilder, build_card, build_webhook_payload
from feishu_card_notify.core.types import LinkButton, NotifyLevel, NotifyMessage


class TestFeishuCardBuilder:
    def test_basic_card_structure(self, sample_message):
        card = FeishuCardBuilder(sample_message).build()
        assert "config" in card
        assert card["config"]["wide_screen_mode"] is True
        assert "header" in card
        assert "elements" in card

    def test_header_color_matches_level(self, sample_message):
        card = FeishuCardBuilder(sample_message).build()
        assert card["header"]["template"] == "orange"  # ERROR = orange

    def test_header_title(self, sample_message):
        card = FeishuCardBuilder(sample_message).build()
        title = card["header"]["title"]["content"]
        assert "Test Error" in title
        assert "\u274c" in title  # ERROR emoji

    def test_content_element(self, sample_message):
        card = FeishuCardBuilder(sample_message).build()
        markdown_elements = [e for e in card["elements"] if e.get("tag") == "markdown"]
        contents = [e["content"] for e in markdown_elements]
        assert any("Something went wrong" in c for c in contents)

    def test_error_block(self, sample_message):
        card = FeishuCardBuilder(sample_message).build()
        markdown_elements = [e for e in card["elements"] if e.get("tag") == "markdown"]
        contents = [e["content"] for e in markdown_elements]
        assert any("NullPointerException" in c for c in contents)

    def test_no_content(self):
        msg = NotifyMessage(level=NotifyLevel.INFO, title="Empty", content="")
        card = FeishuCardBuilder(msg).build()
        # Should still build successfully
        assert card["header"]["template"] == "blue"

    def test_metrics_formatting(self):
        msg = NotifyMessage(
            level=NotifyLevel.SUCCESS, title="Done", content="",
            metrics={"rows": 15000, "small": 42},
        )
        card = FeishuCardBuilder(msg).build()
        markdown_elements = [e for e in card["elements"] if e.get("tag") == "markdown"]
        contents = " ".join(e["content"] for e in markdown_elements)
        assert "15,000" in contents  # large number formatted
        assert "42" in contents

    def test_actions_buttons(self):
        msg = NotifyMessage(
            level=NotifyLevel.INFO, title="Test", content="",
            links=[
                LinkButton(text="View", url="https://example.com"),
                LinkButton(text="Delete", url="https://example.com/delete", is_danger=True),
            ],
        )
        card = FeishuCardBuilder(msg).build()
        action_elements = [e for e in card["elements"] if e.get("tag") == "action"]
        assert len(action_elements) == 1
        buttons = action_elements[0]["actions"]
        assert buttons[0]["type"] == "primary"  # first non-danger is primary
        assert buttons[1]["type"] == "danger"

    def test_at_mention_all(self):
        msg = NotifyMessage(
            level=NotifyLevel.CRITICAL, title="Alert", content="",
            mention_all=True,
        )
        card = FeishuCardBuilder(msg).build()
        markdown_elements = [e for e in card["elements"] if e.get("tag") == "markdown"]
        contents = " ".join(e.get("content", "") for e in markdown_elements)
        assert "<at id=all></at>" in contents

    def test_at_individual(self):
        msg = NotifyMessage(
            level=NotifyLevel.INFO, title="Test", content="",
            mentions=["user123", "user456"],
        )
        card = FeishuCardBuilder(msg).build()
        markdown_elements = [e for e in card["elements"] if e.get("tag") == "markdown"]
        contents = " ".join(e.get("content", "") for e in markdown_elements)
        assert "<at id=user123></at>" in contents
        assert "<at id=user456></at>" in contents

    def test_note_with_source(self, sample_message):
        card = FeishuCardBuilder(sample_message).build()
        note_elements = [e for e in card["elements"] if e.get("tag") == "note"]
        assert len(note_elements) == 1
        note_text = note_elements[0]["elements"][0]["content"]
        assert "test-suite" in note_text

    def test_note_with_dedupe_key(self):
        msg = NotifyMessage(
            level=NotifyLevel.INFO, title="Test", content="",
            dedupe_key="my-key",
        )
        card = FeishuCardBuilder(msg).build()
        note_elements = [e for e in card["elements"] if e.get("tag") == "note"]
        note_text = note_elements[0]["elements"][0]["content"]
        assert "my-key" in note_text

    def test_to_webhook_payload(self, sample_message):
        payload = FeishuCardBuilder(sample_message).to_webhook_payload()
        assert payload["msg_type"] == "interactive"
        assert "card" in payload

    def test_extra_fields(self):
        msg = NotifyMessage(
            level=NotifyLevel.INFO, title="Test", content="",
            extra={"env": "prod", "region": "us-east"},
        )
        card = FeishuCardBuilder(msg).build()
        div_elements = [e for e in card["elements"] if e.get("tag") == "div"]
        # Should have at least one div with extra fields
        all_fields = []
        for div in div_elements:
            all_fields.extend(div.get("fields", []))
        field_contents = [f["text"]["content"] for f in all_fields]
        assert any("env" in c for c in field_contents)


class TestConvenienceFunctions:
    def test_build_card(self, sample_message):
        card = build_card(sample_message)
        assert "header" in card

    def test_build_webhook_payload(self, sample_message):
        payload = build_webhook_payload(sample_message)
        assert payload["msg_type"] == "interactive"
