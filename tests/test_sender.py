"""Tests for FeishuSender (mocked httpx)"""

import pytest
import httpx
import respx

from feishu_card_notify.core.sender import FeishuSender, SendResult
from feishu_card_notify.core.types import NotifyLevel, NotifyMessage


WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook"


def _make_msg(**kwargs):
    defaults = dict(level=NotifyLevel.ERROR, title="Test", content="content", source="test")
    defaults.update(kwargs)
    return NotifyMessage(**defaults)


def _sender(**kwargs):
    defaults = dict(
        webhook_url=WEBHOOK_URL,
        max_retries=2,
        retry_delay=0.01,
    )
    defaults.update(kwargs)
    return FeishuSender(**defaults)


class TestSendRaw:
    @respx.mock
    def test_success(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0, "msg": "ok"})
        )
        sender = _sender()
        result = sender.send_raw({"msg_type": "interactive", "card": {}})
        assert result.success is True
        assert result.retries == 0
        sender.close()

    @respx.mock
    def test_feishu_error(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 1, "msg": "invalid token"})
        )
        sender = _sender()
        result = sender.send_raw({"msg_type": "interactive", "card": {}})
        assert result.success is False
        assert "invalid token" in result.message
        sender.close()

    @respx.mock
    def test_retry_on_500(self):
        route = respx.post(WEBHOOK_URL)
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(200, json={"code": 0}),
        ]
        sender = _sender()
        result = sender.send_raw({"msg_type": "interactive", "card": {}})
        assert result.success is True
        assert result.retries == 1
        sender.close()

    @respx.mock
    def test_all_retries_exhausted(self):
        respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(500))
        sender = _sender(max_retries=1)
        result = sender.send_raw({"msg_type": "interactive", "card": {}})
        assert result.success is False
        assert "重试" in result.message
        sender.close()

    @respx.mock
    def test_timeout(self):
        respx.post(WEBHOOK_URL).mock(side_effect=httpx.TimeoutException("timeout"))
        sender = _sender(max_retries=0)
        result = sender.send_raw({"msg_type": "interactive", "card": {}})
        assert result.success is False
        assert "超时" in result.message
        sender.close()

    @respx.mock
    def test_status_code_response(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"StatusCode": 0})
        )
        sender = _sender()
        result = sender.send_raw({"msg_type": "interactive", "card": {}})
        assert result.success is True
        sender.close()


class TestSendRawAsync:
    @respx.mock
    @pytest.mark.asyncio
    async def test_success(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        sender = _sender()
        result = await sender.send_raw_async({"msg_type": "interactive", "card": {}})
        assert result.success is True
        await sender.close_async()

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry(self):
        route = respx.post(WEBHOOK_URL)
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(200, json={"code": 0}),
        ]
        sender = _sender()
        result = await sender.send_raw_async({"msg_type": "interactive", "card": {}})
        assert result.success is True
        assert result.retries == 1
        await sender.close_async()


class TestSendMessage:
    @respx.mock
    def test_send_builds_card(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        sender = _sender()
        msg = _make_msg()
        result = sender.send(msg)
        assert result.success is True
        sender.close()


class TestExponentialBackoff:
    def test_retry_delay_calculation(self):
        sender = _sender(retry_delay=1.0)
        assert sender._retry_delay(1) == 1.0
        assert sender._retry_delay(2) == 2.0
        assert sender._retry_delay(3) == 4.0


class TestTokenManagement:
    @respx.mock
    def test_ensure_token(self):
        respx.post(FeishuSender.AUTH_URL).mock(
            return_value=httpx.Response(200, json={
                "code": 0,
                "tenant_access_token": "test-token",
                "expire": 7200,
            })
        )
        sender = _sender(app_id="test-id", app_secret="test-secret")
        token = sender._ensure_token()
        assert token == "test-token"
        sender.close()

    def test_validate_app_credentials_missing(self):
        sender = _sender()
        with pytest.raises(ValueError, match="app_id"):
            sender._validate_app_credentials()

    @respx.mock
    def test_token_caching(self):
        route = respx.post(FeishuSender.AUTH_URL)
        route.mock(return_value=httpx.Response(200, json={
            "code": 0,
            "tenant_access_token": "cached-token",
            "expire": 7200,
        }))
        sender = _sender(app_id="id", app_secret="secret")
        token1 = sender._ensure_token()
        token2 = sender._ensure_token()
        assert token1 == token2
        assert route.call_count == 1  # only called once
        sender.close()

    @respx.mock
    def test_send_to_user(self):
        respx.post(FeishuSender.AUTH_URL).mock(
            return_value=httpx.Response(200, json={
                "code": 0,
                "tenant_access_token": "tok",
                "expire": 7200,
            })
        )
        respx.post(url__startswith=FeishuSender.IM_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        sender = _sender(app_id="id", app_secret="secret")
        msg = _make_msg()
        result = sender.send_to_user(msg, "ou_xxx")
        assert result.success is True
        assert "ou_xxx" in result.message
        sender.close()


class TestContextManager:
    @respx.mock
    def test_sync_context_manager(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        with _sender() as sender:
            result = sender.send_raw({"msg_type": "interactive", "card": {}})
            assert result.success is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        respx.post(WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        async with _sender() as sender:
            result = await sender.send_raw_async({"msg_type": "interactive", "card": {}})
            assert result.success is True
