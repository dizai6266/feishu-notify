"""
飞书消息发送器

支持:
- 同步/异步发送
- 自动重试（指数退避）
- 错误处理
- Webhook（群机器人）和 IM API（直发个人）双通道
"""

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import httpx

from feishu_card_notify.core.types import NotifyMessage

if TYPE_CHECKING:
    from feishu_card_notify.templates.loader import TemplateLoader


logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    """发送结果"""
    success: bool
    message: str
    status_code: Optional[int] = None
    response_data: Optional[Dict[str, Any]] = None
    retries: int = 0
    elapsed_ms: float = 0.0


class FeishuSender:
    """
    飞书消息发送器

    支持同步和异步发送，带自动重试（指数退避）
    支持 Webhook（群机器人）和 IM API（直发个人）两种通道
    """

    FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
    AUTH_URL = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
    IM_URL = f"{FEISHU_BASE_URL}/im/v1/messages"

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        receive_id_type: str = "open_id",
        timeout: float = 10.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        template_loader: Optional["TemplateLoader"] = None,
    ):
        self.webhook_url = webhook_url or ""
        self.app_id = app_id
        self.app_secret = app_secret
        self.receive_id_type = receive_id_type
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._template_loader = template_loader

        self._sync_client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

        # Token 缓存 + 锁
        self._access_token: Optional[str] = None
        self._token_expire_time: float = 0
        self._token_lock = threading.Lock()
        self._token_async_lock: Optional[asyncio.Lock] = None

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(timeout=self.timeout)
        return self._sync_client

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client

    def _get_async_token_lock(self) -> asyncio.Lock:
        if self._token_async_lock is None:
            self._token_async_lock = asyncio.Lock()
        return self._token_async_lock

    # ==================== 核心：响应解析 ====================

    def _handle_response(
        self,
        response: httpx.Response,
        start_time: float,
        retries: int,
        user_id: Optional[str] = None,
    ) -> Optional[SendResult]:
        """解析响应为 SendResult。返回 None 表示需要重试。"""
        elapsed_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0 or data.get("StatusCode") == 0:
                msg = f"发送成功: {user_id}" if user_id else "发送成功"
                if user_id:
                    logger.info(msg)
                return SendResult(
                    success=True, message=msg,
                    status_code=response.status_code, response_data=data,
                    retries=retries, elapsed_ms=elapsed_ms,
                )
            else:
                error_msg = data.get("msg") or data.get("StatusMessage") or "Unknown error"
                return SendResult(
                    success=False, message=f"飞书返回错误: {error_msg}",
                    status_code=response.status_code, response_data=data,
                    retries=retries, elapsed_ms=elapsed_ms,
                )
        # 非 200 状态码 → 需要重试
        return None

    def _make_failure_result(
        self, start_time: float, retries: int, last_error: Optional[str]
    ) -> SendResult:
        elapsed_ms = (time.time() - start_time) * 1000
        return SendResult(
            success=False,
            message=f"发送失败（已重试 {self.max_retries} 次）: {last_error}",
            retries=retries - 1,
            elapsed_ms=elapsed_ms,
        )

    def _retry_delay(self, retry_count: int) -> float:
        """指数退避延迟"""
        return self.retry_delay * (2 ** (retry_count - 1))

    # ==================== 核心：同步/异步重试 ====================

    def _post_with_retry(
        self,
        client: httpx.Client,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        user_id: Optional[str] = None,
    ) -> SendResult:
        retries = 0
        last_error = None
        start_time = time.time()

        while retries <= self.max_retries:
            try:
                response = client.post(url, json=payload, headers=headers)
                result = self._handle_response(response, start_time, retries, user_id)
                if result is not None:
                    return result
                last_error = f"HTTP {response.status_code}"
            except httpx.TimeoutException as e:
                last_error = f"请求超时: {e}"
            except httpx.HTTPError as e:
                last_error = f"HTTP 错误: {e}"
            except Exception as e:
                last_error = f"未知错误: {e}"

            retries += 1
            if retries <= self.max_retries:
                delay = self._retry_delay(retries)
                logger.warning(
                    f"发送失败，{delay}s 后重试 ({retries}/{self.max_retries}): {last_error}"
                )
                time.sleep(delay)

        return self._make_failure_result(start_time, retries, last_error)

    async def _post_with_retry_async(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        user_id: Optional[str] = None,
    ) -> SendResult:
        retries = 0
        last_error = None
        start_time = time.time()

        while retries <= self.max_retries:
            try:
                response = await client.post(url, json=payload, headers=headers)
                result = self._handle_response(response, start_time, retries, user_id)
                if result is not None:
                    return result
                last_error = f"HTTP {response.status_code}"
            except httpx.TimeoutException as e:
                last_error = f"请求超时: {e}"
            except httpx.HTTPError as e:
                last_error = f"HTTP 错误: {e}"
            except Exception as e:
                last_error = f"未知错误: {e}"

            retries += 1
            if retries <= self.max_retries:
                delay = self._retry_delay(retries)
                logger.warning(
                    f"发送失败，{delay}s 后重试 ({retries}/{self.max_retries}): {last_error}"
                )
                await asyncio.sleep(delay)

        return self._make_failure_result(start_time, retries, last_error)

    # ==================== Webhook 发送 ====================

    def _build_payload(self, message: NotifyMessage) -> Dict[str, Any]:
        """构建 Webhook payload"""
        from feishu_card_notify.core.builder import FeishuCardBuilder
        return FeishuCardBuilder(message, self._template_loader).to_webhook_payload()

    def send(self, message: NotifyMessage) -> SendResult:
        """同步发送消息"""
        return self.send_raw(self._build_payload(message))

    async def send_async(self, message: NotifyMessage) -> SendResult:
        """异步发送消息"""
        return await self.send_raw_async(self._build_payload(message))

    def send_raw(self, payload: Dict[str, Any]) -> SendResult:
        """同步发送原始 payload"""
        return self._post_with_retry(
            self._get_sync_client(), self.webhook_url, payload,
            {"Content-Type": "application/json"},
        )

    async def send_raw_async(self, payload: Dict[str, Any]) -> SendResult:
        """异步发送原始 payload"""
        return await self._post_with_retry_async(
            self._get_async_client(), self.webhook_url, payload,
            {"Content-Type": "application/json"},
        )

    # ==================== IM API（直发个人）====================

    def _validate_app_credentials(self) -> None:
        if not self.app_id or not self.app_secret:
            raise ValueError(
                "发送个人通知需要配置 app_id 和 app_secret。"
                "可通过参数传入或设置环境变量 FEISHU_APP_ID + FEISHU_APP_SECRET。"
            )

    def _parse_token_response(self, data: Dict[str, Any]) -> str:
        if data.get("code") == 0:
            self._access_token = data["tenant_access_token"]
            expire_in = data.get("expire", 7200)
            self._token_expire_time = time.time() + expire_in - 300
            logger.debug(f"获取 tenant_access_token 成功，有效期 {expire_in}s")
            return self._access_token
        raise RuntimeError(f"获取 tenant_access_token 失败: {data.get('msg')}")

    def _token_is_valid(self) -> bool:
        return bool(self._access_token and time.time() < self._token_expire_time)

    def _ensure_token(self) -> str:
        with self._token_lock:
            if self._token_is_valid():
                return self._access_token  # type: ignore[return-value]
            self._validate_app_credentials()
            response = self._get_sync_client().post(
                self.AUTH_URL,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            return self._parse_token_response(response.json())

    async def _ensure_token_async(self) -> str:
        async with self._get_async_token_lock():
            if self._token_is_valid():
                return self._access_token  # type: ignore[return-value]
            self._validate_app_credentials()
            response = await self._get_async_client().post(
                self.AUTH_URL,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            return self._parse_token_response(response.json())

    def _build_im_request(
        self, card: Dict[str, Any], user_id: str, token: str
    ) -> tuple:
        """构建 IM API 请求参数，返回 (url, payload, headers)"""
        url = f"{self.IM_URL}?receive_id_type={self.receive_id_type}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "receive_id": user_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        return url, payload, headers

    def send_to_user(self, message: NotifyMessage, user_id: str) -> SendResult:
        """同步发送消息给单个用户"""
        from feishu_card_notify.core.builder import FeishuCardBuilder
        card = FeishuCardBuilder(message, self._template_loader).build()
        return self._send_card_to_user(card, user_id)

    async def send_to_user_async(self, message: NotifyMessage, user_id: str) -> SendResult:
        """异步发送消息给单个用户"""
        from feishu_card_notify.core.builder import FeishuCardBuilder
        card = FeishuCardBuilder(message, self._template_loader).build()
        return await self._send_card_to_user_async(card, user_id)

    def _send_card_to_user(self, card: Dict[str, Any], user_id: str) -> SendResult:
        """同步发送已构建的卡片给单个用户"""
        token = self._ensure_token()
        url, payload, headers = self._build_im_request(card, user_id, token)
        return self._post_with_retry(
            self._get_sync_client(), url, payload, headers, user_id
        )

    async def _send_card_to_user_async(self, card: Dict[str, Any], user_id: str) -> SendResult:
        """异步发送已构建的卡片给单个用户"""
        token = await self._ensure_token_async()
        url, payload, headers = self._build_im_request(card, user_id, token)
        return await self._post_with_retry_async(
            self._get_async_client(), url, payload, headers, user_id
        )

    def send_to_users(self, message: NotifyMessage, user_ids: List[str]) -> List[SendResult]:
        """同步发送消息给多个用户"""
        from feishu_card_notify.core.builder import FeishuCardBuilder
        card = FeishuCardBuilder(message, self._template_loader).build()
        return [self._send_card_to_user(card, uid) for uid in user_ids]

    async def send_to_users_async(
        self, message: NotifyMessage, user_ids: List[str]
    ) -> List[SendResult]:
        """异步发送消息给多个用户（并发）"""
        from feishu_card_notify.core.builder import FeishuCardBuilder
        card = FeishuCardBuilder(message, self._template_loader).build()
        return list(await asyncio.gather(*[
            self._send_card_to_user_async(card, uid) for uid in user_ids
        ]))

    # ==================== 资源管理 ====================

    def close(self):
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

    async def close_async(self):
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_async()
