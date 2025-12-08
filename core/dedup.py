"""
去重与限流模块

支持:
- 基于 dedupe_key 的消息去重
- 滑动窗口限流
- 内存存储（TTL 自动过期）
- 可扩展 Redis 后端
"""

import hashlib
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.types import NotifyLevel, NotifyMessage


@dataclass
class DedupRecord:
    """去重记录"""
    key: str
    first_seen: float
    last_seen: float
    count: int = 1
    last_message_hash: str = ""


@dataclass
class RateLimitRecord:
    """限流记录"""
    key: str
    timestamps: List[float] = field(default_factory=list)


class DedupBackend(ABC):
    """去重后端抽象基类"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[DedupRecord]:
        """获取去重记录"""
        pass
    
    @abstractmethod
    def set(self, key: str, record: DedupRecord, ttl: int) -> None:
        """设置去重记录"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> None:
        """删除去重记录"""
        pass
    
    @abstractmethod
    def cleanup(self) -> int:
        """清理过期记录，返回清理数量"""
        pass


class MemoryDedupBackend(DedupBackend):
    """内存去重后端"""
    
    def __init__(self):
        self._data: Dict[str, Tuple[DedupRecord, float]] = {}  # key -> (record, expire_time)
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[DedupRecord]:
        with self._lock:
            if key in self._data:
                record, expire_time = self._data[key]
                if time.time() < expire_time:
                    return record
                else:
                    del self._data[key]
            return None
    
    def set(self, key: str, record: DedupRecord, ttl: int) -> None:
        with self._lock:
            expire_time = time.time() + ttl
            self._data[key] = (record, expire_time)
    
    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
    
    def cleanup(self) -> int:
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, (_, expire_time) in self._data.items()
                if now >= expire_time
            ]
            for key in expired_keys:
                del self._data[key]
            return len(expired_keys)


class DedupManager:
    """
    去重管理器
    
    基于 dedupe_key 判断消息是否重复:
    - 相同 dedupe_key 在 TTL 内视为重复
    - 支持更新已有消息的计数和时间
    """
    
    def __init__(
        self,
        backend: Optional[DedupBackend] = None,
        ttl_seconds: int = 300,
        enable_auto_cleanup: bool = True,
        cleanup_interval: int = 60,
    ):
        """
        初始化去重管理器
        
        Args:
            backend: 存储后端，None 则使用内存
            ttl_seconds: 去重 TTL（秒）
            enable_auto_cleanup: 是否自动清理过期记录
            cleanup_interval: 清理间隔（秒）
        """
        self.backend = backend or MemoryDedupBackend()
        self.ttl_seconds = ttl_seconds
        
        if enable_auto_cleanup:
            self._start_cleanup_thread(cleanup_interval)
    
    def _start_cleanup_thread(self, interval: int):
        """启动自动清理线程"""
        def cleanup_worker():
            while True:
                time.sleep(interval)
                try:
                    count = self.backend.cleanup()
                    if count > 0:
                        pass  # logger.debug(f"Cleaned up {count} expired dedup records")
                except Exception:
                    pass
        
        thread = threading.Thread(target=cleanup_worker, daemon=True)
        thread.start()
    
    def _generate_key(self, message: NotifyMessage) -> str:
        """生成去重 key"""
        if message.dedupe_key:
            return f"dedup:{message.dedupe_key}"
        
        # 没有指定 dedupe_key，基于消息内容生成
        content = f"{message.level.name}:{message.source}:{message.title}:{message.content}"
        hash_value = hashlib.md5(content.encode()).hexdigest()[:16]
        return f"dedup:auto:{hash_value}"
    
    def _generate_message_hash(self, message: NotifyMessage) -> str:
        """生成消息内容哈希"""
        content = f"{message.title}:{message.content}:{message.error_msg or ''}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def is_duplicate(self, message: NotifyMessage) -> Tuple[bool, Optional[DedupRecord]]:
        """
        检查消息是否重复
        
        Args:
            message: 消息对象
            
        Returns:
            (是否重复, 已有记录)
        """
        key = self._generate_key(message)
        record = self.backend.get(key)
        
        if record is not None:
            return True, record
        return False, None
    
    def mark(self, message: NotifyMessage) -> DedupRecord:
        """
        标记消息已发送
        
        Args:
            message: 消息对象
            
        Returns:
            去重记录
        """
        key = self._generate_key(message)
        message_hash = self._generate_message_hash(message)
        now = time.time()
        
        existing = self.backend.get(key)
        if existing:
            # 更新已有记录
            existing.last_seen = now
            existing.count += 1
            existing.last_message_hash = message_hash
            self.backend.set(key, existing, self.ttl_seconds)
            return existing
        else:
            # 创建新记录
            record = DedupRecord(
                key=key,
                first_seen=now,
                last_seen=now,
                count=1,
                last_message_hash=message_hash,
            )
            self.backend.set(key, record, self.ttl_seconds)
            return record
    
    def clear(self, message: NotifyMessage) -> None:
        """清除消息的去重记录"""
        key = self._generate_key(message)
        self.backend.delete(key)


class RateLimiter:
    """
    限流器
    
    使用滑动窗口算法限制消息发送频率
    """
    
    def __init__(
        self,
        window_seconds: int = 60,
        max_count: int = 10,
        enable_auto_cleanup: bool = True,
    ):
        """
        初始化限流器
        
        Args:
            window_seconds: 时间窗口（秒）
            max_count: 窗口内最大消息数
            enable_auto_cleanup: 是否自动清理过期记录
        """
        self.window_seconds = window_seconds
        self.max_count = max_count
        
        self._records: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.RLock()
        
        if enable_auto_cleanup:
            self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """启动自动清理线程"""
        def cleanup_worker():
            while True:
                time.sleep(self.window_seconds)
                self._cleanup()
        
        thread = threading.Thread(target=cleanup_worker, daemon=True)
        thread.start()
    
    def _cleanup(self):
        """清理过期的时间戳"""
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            
            for key in list(self._records.keys()):
                self._records[key] = [
                    ts for ts in self._records[key] if ts > cutoff
                ]
                if not self._records[key]:
                    del self._records[key]
    
    def _get_key(self, message: NotifyMessage) -> str:
        """生成限流 key"""
        # 按来源+级别限流
        return f"ratelimit:{message.source}:{message.level.name}"
    
    def is_allowed(self, message: NotifyMessage) -> Tuple[bool, int]:
        """
        检查消息是否允许发送
        
        Args:
            message: 消息对象
            
        Returns:
            (是否允许, 当前窗口内已发送数量)
        """
        key = self._get_key(message)
        now = time.time()
        cutoff = now - self.window_seconds
        
        with self._lock:
            # 清理过期时间戳
            self._records[key] = [
                ts for ts in self._records[key] if ts > cutoff
            ]
            
            current_count = len(self._records[key])
            
            # CRITICAL 和 ERROR 级别不限流
            if message.level in (NotifyLevel.CRITICAL, NotifyLevel.ERROR):
                return True, current_count
            
            if current_count >= self.max_count:
                return False, current_count
            
            return True, current_count
    
    def record(self, message: NotifyMessage) -> None:
        """记录消息发送"""
        key = self._get_key(message)
        
        with self._lock:
            self._records[key].append(time.time())
    
    def get_remaining(self, message: NotifyMessage) -> int:
        """获取剩余配额"""
        key = self._get_key(message)
        now = time.time()
        cutoff = now - self.window_seconds
        
        with self._lock:
            current_count = len([
                ts for ts in self._records[key] if ts > cutoff
            ])
            return max(0, self.max_count - current_count)
    
    def reset(self, message: Optional[NotifyMessage] = None) -> None:
        """
        重置限流记录
        
        Args:
            message: 指定消息则只重置该消息的记录，None 则重置所有
        """
        with self._lock:
            if message:
                key = self._get_key(message)
                self._records.pop(key, None)
            else:
                self._records.clear()


class MessageFilter:
    """
    消息过滤器
    
    组合去重和限流功能
    """
    
    def __init__(
        self,
        dedup_manager: Optional[DedupManager] = None,
        rate_limiter: Optional[RateLimiter] = None,
        enable_dedup: bool = True,
        enable_rate_limit: bool = True,
    ):
        """
        初始化消息过滤器
        
        Args:
            dedup_manager: 去重管理器
            rate_limiter: 限流器
            enable_dedup: 是否启用去重
            enable_rate_limit: 是否启用限流
        """
        self.dedup_manager = dedup_manager or DedupManager()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.enable_dedup = enable_dedup
        self.enable_rate_limit = enable_rate_limit
    
    def should_send(self, message: NotifyMessage) -> Tuple[bool, str]:
        """
        判断消息是否应该发送
        
        Args:
            message: 消息对象
            
        Returns:
            (是否发送, 原因说明)
        """
        # 检查去重
        if self.enable_dedup:
            is_dup, record = self.dedup_manager.is_duplicate(message)
            if is_dup and record:
                return False, f"消息重复（已发送 {record.count} 次，首次: {record.first_seen:.0f}）"
        
        # 检查限流
        if self.enable_rate_limit:
            allowed, count = self.rate_limiter.is_allowed(message)
            if not allowed:
                return False, f"触发限流（{self.rate_limiter.window_seconds}s 内已发送 {count} 条）"
        
        return True, "允许发送"
    
    def mark_sent(self, message: NotifyMessage) -> None:
        """标记消息已发送"""
        if self.enable_dedup:
            self.dedup_manager.mark(message)
        
        if self.enable_rate_limit:
            self.rate_limiter.record(message)

