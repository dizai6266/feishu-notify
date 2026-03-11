"""Tests for core types: NotifyLevel, NotifyMessage, LinkButton"""

import pytest
from datetime import datetime

from feishu_card_notify.core.types import LinkButton, NotifyLevel, NotifyMessage


class TestNotifyLevel:
    def test_all_levels_exist(self):
        levels = [l.name for l in NotifyLevel]
        assert levels == ["CRITICAL", "ERROR", "WARNING", "SUCCESS", "INFO", "PENDING"]

    def test_critical_properties(self):
        assert NotifyLevel.CRITICAL.priority == "P0"
        assert NotifyLevel.CRITICAL.color == "red"
        assert NotifyLevel.CRITICAL.emoji == "\U0001f6a8"
        assert NotifyLevel.CRITICAL.prefix == "[紧急]"

    def test_success_properties(self):
        assert NotifyLevel.SUCCESS.priority == "P3"
        assert NotifyLevel.SUCCESS.color == "green"

    def test_from_string_valid(self):
        assert NotifyLevel.from_string("error") == NotifyLevel.ERROR
        assert NotifyLevel.from_string("ERROR") == NotifyLevel.ERROR
        assert NotifyLevel.from_string("Warning") == NotifyLevel.WARNING

    def test_from_string_invalid(self):
        with pytest.raises(ValueError, match="Unknown notify level"):
            NotifyLevel.from_string("UNKNOWN")


class TestLinkButton:
    def test_to_dict(self):
        link = LinkButton(text="View", url="https://example.com", is_danger=True)
        d = link.to_dict()
        assert d == {"text": "View", "url": "https://example.com", "is_danger": True}

    def test_default_is_danger(self):
        link = LinkButton(text="View", url="https://example.com")
        assert link.is_danger is False


class TestNotifyMessage:
    def test_auto_timestamp(self):
        msg = NotifyMessage(level=NotifyLevel.INFO, title="Test", content="")
        assert isinstance(msg.timestamp, datetime)

    def test_formatted_title(self):
        msg = NotifyMessage(level=NotifyLevel.SUCCESS, title="Done", content="")
        assert msg.formatted_title == "\u2705 [成功] Done"

    def test_formatted_timestamp(self):
        msg = NotifyMessage(level=NotifyLevel.INFO, title="Test", content="")
        ts = msg.formatted_timestamp
        # Should be in YYYY-MM-DD HH:MM:SS format
        assert len(ts) == 19
        assert ts[4] == "-"

    def test_dict_links_conversion(self):
        msg = NotifyMessage(
            level=NotifyLevel.INFO,
            title="Test",
            content="",
            links=[{"text": "Click", "url": "https://example.com"}],
        )
        assert isinstance(msg.links[0], LinkButton)
        assert msg.links[0].text == "Click"

    def test_add_link_chain(self):
        msg = NotifyMessage(level=NotifyLevel.INFO, title="Test", content="")
        result = msg.add_link("View", "https://example.com")
        assert result is msg  # chain
        assert len(msg.links) == 1

    def test_add_mention_no_duplicates(self):
        msg = NotifyMessage(level=NotifyLevel.INFO, title="Test", content="")
        msg.add_mention("user1")
        msg.add_mention("user1")
        assert msg.mentions == ["user1"]

    def test_set_metrics_chain(self):
        msg = NotifyMessage(level=NotifyLevel.INFO, title="Test", content="")
        result = msg.set_metrics(rows=100, tables=5)
        assert result is msg
        assert msg.metrics == {"rows": 100, "tables": 5}

    def test_set_metrics_merges(self):
        msg = NotifyMessage(
            level=NotifyLevel.INFO, title="Test", content="",
            metrics={"existing": 1},
        )
        msg.set_metrics(new=2)
        assert msg.metrics == {"existing": 1, "new": 2}

    def test_to_dict_all_fields(self, full_message):
        d = full_message.to_dict()
        assert d["level"] == "CRITICAL"
        assert d["title"] == "Critical Alert"
        assert d["source"] == "Airflow"
        assert d["task_name"] == "sync_job"
        assert d["error_msg"] == "Connection refused"
        assert d["error_code"] == "ERR_001"
        assert d["metrics"]["rows"] == 15000
        assert len(d["links"]) == 1
        assert d["mentions"] == ["user123"]
        assert d["mention_all"] is True
        assert d["dedupe_key"] == "unique-key"
        assert d["extra"] == {"env": "production"}
