"""Tests for Notifier (integration)"""

import pytest
import httpx
import respx

from feishu_notify.config import NotifyConfig
from feishu_notify.core.sender import SendResult
from feishu_notify.core.types import NotifyLevel, NotifyMessage
from feishu_notify.notifier import Notifier, get_notifier, set_default_notifier


WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook"


def _notifier(**kwargs):
    defaults = dict(
        webhook=WEBHOOK_URL,
        source="test",
        enable_dedup=False,
        enable_rate_limit=False,
    )
    defaults.update(kwargs)
    return Notifier(**defaults)


class TestNotifierSend:
    @respx.mock
    def test_send_to_webhook(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        msg = NotifyMessage(level=NotifyLevel.INFO, title="Test", content="", source="test")
        result = notifier.send(msg)
        assert result.success is True
        notifier.close()

    @respx.mock
    def test_send_force_bypasses_filter(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier(enable_dedup=True)
        msg = NotifyMessage(
            level=NotifyLevel.INFO, title="Test", content="",
            source="test", dedupe_key="dup",
        )
        result1 = notifier.send(msg)
        assert result1.success is True
        # second send would be blocked by dedup
        result2 = notifier.send(msg)
        assert result2.success is False
        # force bypasses
        result3 = notifier.send(msg, force=True)
        assert result3.success is True
        notifier.close()

    @respx.mock
    def test_critical_auto_mention_all(self):
        route = respx.post(WEBHOOK_URL)
        route.mock(return_value=httpx.Response(200, json={"code": 0}))
        notifier = _notifier()
        msg = NotifyMessage(
            level=NotifyLevel.CRITICAL, title="Alert", content="", source="test"
        )
        assert msg.mention_all is False
        notifier.send(msg)
        assert msg.mention_all is True
        notifier.close()


class TestNotifierQuickMethods:
    @respx.mock
    def test_success_method(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        result = notifier.success("Done", metrics={"rows": 100})
        assert result.success is True
        notifier.close()

    @respx.mock
    def test_error_method(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        result = notifier.error("Failed", error_msg="NullPointer")
        assert result.success is True
        notifier.close()

    @respx.mock
    def test_warning_method(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        result = notifier.warning("Delay", content="45min delay")
        assert result.success is True
        notifier.close()

    @respx.mock
    def test_info_method(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        result = notifier.info("Report", link_url="https://example.com")
        assert result.success is True
        notifier.close()

    @respx.mock
    def test_pending_method(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        result = notifier.pending("Approval needed")
        assert result.success is True
        notifier.close()

    @respx.mock
    def test_critical_force_sends(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier(enable_dedup=True)
        result = notifier.critical("Emergency")
        assert result.success is True
        notifier.close()


class TestNotifierAsync:
    @respx.mock
    @pytest.mark.asyncio
    async def test_send_async(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        result = await notifier.success_async("Done")
        assert result.success is True
        await notifier.close_async()

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        async with _notifier() as notifier:
            result = await notifier.info_async("Test")
            assert result.success is True


class TestNotifierCustomTemplates:
    @respx.mock
    def test_custom_method(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        result = notifier.custom("timeout_warning", "Timeout", task_name="job1")
        assert result.success is True
        notifier.close()

    @respx.mock
    def test_dynamic_method(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        result = notifier.timeout_warning("Timeout", duration="45min")
        assert result.success is True
        notifier.close()

    def test_nonexistent_template_raises(self):
        notifier = _notifier()
        with pytest.raises(AttributeError):
            notifier.nonexistent_template_xyz("title")
        notifier.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_dynamic_async_method(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        notifier = _notifier()
        result = await notifier.timeout_warning_async("Timeout")
        assert result.success is True
        await notifier.close_async()


class TestNotifierConfig:
    def test_config_from_params(self):
        notifier = _notifier()
        assert notifier.config.webhook_url == WEBHOOK_URL
        assert notifier.config.default_source == "test"
        notifier.close()

    def test_config_validation_fails(self):
        with pytest.raises(ValueError):
            Notifier()  # no webhook, no app credentials

    def test_reload_templates(self):
        notifier = _notifier()
        notifier.reload_templates()  # should not raise
        notifier.close()
