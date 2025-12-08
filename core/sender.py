"""
飞书消息发送器

支持:
- 同步/异步发送
- 自动重试
- 错误处理
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from core.builder import FeishuCardBuilder
from core.types import NotifyMessage


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
    
    支持同步和异步发送，带自动重试
    """
    
    def __init__(
        self,
        webhook_url: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        初始化发送器
        
        Args:
            webhook_url: 飞书机器人 Webhook URL
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self._sync_client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None
    
    def _get_sync_client(self) -> httpx.Client:
        """获取同步 HTTP 客户端"""
        if self._sync_client is None:
            self._sync_client = httpx.Client(timeout=self.timeout)
        return self._sync_client
    
    def _get_async_client(self) -> httpx.AsyncClient:
        """获取异步 HTTP 客户端"""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client
    
    def send(self, message: NotifyMessage) -> SendResult:
        """
        同步发送消息
        
        Args:
            message: 消息对象
            
        Returns:
            发送结果
        """
        payload = FeishuCardBuilder(message).to_webhook_payload()
        return self.send_raw(payload)
    
    async def send_async(self, message: NotifyMessage) -> SendResult:
        """
        异步发送消息
        
        Args:
            message: 消息对象
            
        Returns:
            发送结果
        """
        payload = FeishuCardBuilder(message).to_webhook_payload()
        return await self.send_raw_async(payload)
    
    def send_raw(self, payload: Dict[str, Any]) -> SendResult:
        """
        同步发送原始 payload
        
        Args:
            payload: 飞书消息 payload
            
        Returns:
            发送结果
        """
        client = self._get_sync_client()
        retries = 0
        last_error = None
        start_time = time.time()
        
        while retries <= self.max_retries:
            try:
                response = client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                
                elapsed_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == 0 or data.get("StatusCode") == 0:
                        return SendResult(
                            success=True,
                            message="发送成功",
                            status_code=response.status_code,
                            response_data=data,
                            retries=retries,
                            elapsed_ms=elapsed_ms,
                        )
                    else:
                        error_msg = data.get("msg") or data.get("StatusMessage") or "Unknown error"
                        return SendResult(
                            success=False,
                            message=f"飞书返回错误: {error_msg}",
                            status_code=response.status_code,
                            response_data=data,
                            retries=retries,
                            elapsed_ms=elapsed_ms,
                        )
                else:
                    last_error = f"HTTP {response.status_code}"
                    
            except httpx.TimeoutException as e:
                last_error = f"请求超时: {e}"
            except httpx.HTTPError as e:
                last_error = f"HTTP 错误: {e}"
            except Exception as e:
                last_error = f"未知错误: {e}"
            
            retries += 1
            if retries <= self.max_retries:
                logger.warning(f"发送失败，{self.retry_delay}s 后重试 ({retries}/{self.max_retries}): {last_error}")
                time.sleep(self.retry_delay)
        
        elapsed_ms = (time.time() - start_time) * 1000
        return SendResult(
            success=False,
            message=f"发送失败（已重试 {self.max_retries} 次）: {last_error}",
            retries=retries - 1,
            elapsed_ms=elapsed_ms,
        )
    
    async def send_raw_async(self, payload: Dict[str, Any]) -> SendResult:
        """
        异步发送原始 payload
        
        Args:
            payload: 飞书消息 payload
            
        Returns:
            发送结果
        """
        client = self._get_async_client()
        retries = 0
        last_error = None
        start_time = time.time()
        
        while retries <= self.max_retries:
            try:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                
                elapsed_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == 0 or data.get("StatusCode") == 0:
                        return SendResult(
                            success=True,
                            message="发送成功",
                            status_code=response.status_code,
                            response_data=data,
                            retries=retries,
                            elapsed_ms=elapsed_ms,
                        )
                    else:
                        error_msg = data.get("msg") or data.get("StatusMessage") or "Unknown error"
                        return SendResult(
                            success=False,
                            message=f"飞书返回错误: {error_msg}",
                            status_code=response.status_code,
                            response_data=data,
                            retries=retries,
                            elapsed_ms=elapsed_ms,
                        )
                else:
                    last_error = f"HTTP {response.status_code}"
                    
            except httpx.TimeoutException as e:
                last_error = f"请求超时: {e}"
            except httpx.HTTPError as e:
                last_error = f"HTTP 错误: {e}"
            except Exception as e:
                last_error = f"未知错误: {e}"
            
            retries += 1
            if retries <= self.max_retries:
                logger.warning(f"发送失败，{self.retry_delay}s 后重试 ({retries}/{self.max_retries}): {last_error}")
                await asyncio.sleep(self.retry_delay)
        
        elapsed_ms = (time.time() - start_time) * 1000
        return SendResult(
            success=False,
            message=f"发送失败（已重试 {self.max_retries} 次）: {last_error}",
            retries=retries - 1,
            elapsed_ms=elapsed_ms,
        )
    
    def close(self):
        """关闭同步客户端"""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
    
    async def close_async(self):
        """关闭异步客户端"""
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

