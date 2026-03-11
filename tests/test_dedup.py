"""Tests for DedupManager, RateLimiter, MessageFilter"""

import time

import pytest

from feishu_card_notify.core.dedup import (
    DedupManager,
    MemoryDedupBackend,
    MessageFilter,
    RateLimiter,
)
from feishu_card_notify.core.types import NotifyLevel, NotifyMessage


def _make_msg(level=NotifyLevel.INFO, title="Test", dedupe_key=None):
    return NotifyMessage(
        level=level, title=title, content="content",
        source="test", dedupe_key=dedupe_key,
    )


class TestMemoryDedupBackend:
    def test_set_and_get(self):
        from feishu_card_notify.core.dedup import DedupRecord
        backend = MemoryDedupBackend()
        record = DedupRecord(key="k", first_seen=1.0, last_seen=1.0)
        backend.set("k", record, ttl=60)
        assert backend.get("k") is not None

    def test_get_expired(self):
        from feishu_card_notify.core.dedup import DedupRecord
        backend = MemoryDedupBackend()
        record = DedupRecord(key="k", first_seen=1.0, last_seen=1.0)
        backend.set("k", record, ttl=0)
        time.sleep(0.01)
        assert backend.get("k") is None

    def test_delete(self):
        from feishu_card_notify.core.dedup import DedupRecord
        backend = MemoryDedupBackend()
        record = DedupRecord(key="k", first_seen=1.0, last_seen=1.0)
        backend.set("k", record, ttl=60)
        backend.delete("k")
        assert backend.get("k") is None

    def test_cleanup(self):
        from feishu_card_notify.core.dedup import DedupRecord
        backend = MemoryDedupBackend()
        backend.set("a", DedupRecord(key="a", first_seen=1.0, last_seen=1.0), ttl=0)
        backend.set("b", DedupRecord(key="b", first_seen=1.0, last_seen=1.0), ttl=300)
        time.sleep(0.01)
        cleaned = backend.cleanup()
        assert cleaned == 1
        assert backend.get("b") is not None


class TestDedupManager:
    def test_first_message_not_duplicate(self):
        mgr = DedupManager(ttl_seconds=60, enable_auto_cleanup=False)
        msg = _make_msg(dedupe_key="k1")
        is_dup, record = mgr.is_duplicate(msg)
        assert is_dup is False

    def test_after_mark_is_duplicate(self):
        mgr = DedupManager(ttl_seconds=60, enable_auto_cleanup=False)
        msg = _make_msg(dedupe_key="k1")
        mgr.mark(msg)
        is_dup, record = mgr.is_duplicate(msg)
        assert is_dup is True
        assert record.count == 1

    def test_mark_increments_count(self):
        mgr = DedupManager(ttl_seconds=60, enable_auto_cleanup=False)
        msg = _make_msg(dedupe_key="k1")
        mgr.mark(msg)
        mgr.mark(msg)
        is_dup, record = mgr.is_duplicate(msg)
        assert record.count == 2

    def test_auto_key_generation(self):
        mgr = DedupManager(ttl_seconds=60, enable_auto_cleanup=False)
        msg = _make_msg()  # no dedupe_key
        mgr.mark(msg)
        is_dup, _ = mgr.is_duplicate(msg)
        assert is_dup is True

    def test_clear(self):
        mgr = DedupManager(ttl_seconds=60, enable_auto_cleanup=False)
        msg = _make_msg(dedupe_key="k1")
        mgr.mark(msg)
        mgr.clear(msg)
        is_dup, _ = mgr.is_duplicate(msg)
        assert is_dup is False


class TestRateLimiter:
    def test_under_limit_allowed(self):
        limiter = RateLimiter(
            window_seconds=60, max_count=5, enable_auto_cleanup=False
        )
        msg = _make_msg()
        allowed, count = limiter.is_allowed(msg)
        assert allowed is True

    def test_over_limit_denied(self):
        limiter = RateLimiter(
            window_seconds=60, max_count=2, enable_auto_cleanup=False
        )
        msg = _make_msg()
        limiter.record(msg)
        limiter.record(msg)
        allowed, count = limiter.is_allowed(msg)
        assert allowed is False
        assert count == 2

    def test_critical_bypasses_limit(self):
        limiter = RateLimiter(
            window_seconds=60, max_count=1, enable_auto_cleanup=False
        )
        msg = _make_msg(level=NotifyLevel.CRITICAL)
        limiter.record(msg)
        limiter.record(msg)
        allowed, _ = limiter.is_allowed(msg)
        assert allowed is True

    def test_error_bypasses_limit(self):
        limiter = RateLimiter(
            window_seconds=60, max_count=1, enable_auto_cleanup=False
        )
        msg = _make_msg(level=NotifyLevel.ERROR)
        limiter.record(msg)
        limiter.record(msg)
        allowed, _ = limiter.is_allowed(msg)
        assert allowed is True

    def test_get_remaining(self):
        limiter = RateLimiter(
            window_seconds=60, max_count=5, enable_auto_cleanup=False
        )
        msg = _make_msg()
        limiter.record(msg)
        limiter.record(msg)
        assert limiter.get_remaining(msg) == 3

    def test_reset_specific(self):
        limiter = RateLimiter(
            window_seconds=60, max_count=2, enable_auto_cleanup=False
        )
        msg = _make_msg()
        limiter.record(msg)
        limiter.reset(msg)
        assert limiter.get_remaining(msg) == 2

    def test_reset_all(self):
        limiter = RateLimiter(
            window_seconds=60, max_count=2, enable_auto_cleanup=False
        )
        limiter.record(_make_msg())
        limiter.reset()
        assert limiter.get_remaining(_make_msg()) == 2


class TestMessageFilter:
    def test_allows_first_message(self):
        filt = MessageFilter(
            dedup_manager=DedupManager(ttl_seconds=60, enable_auto_cleanup=False),
            rate_limiter=RateLimiter(window_seconds=60, max_count=10, enable_auto_cleanup=False),
        )
        msg = _make_msg(dedupe_key="k1")
        ok, reason = filt.should_send(msg)
        assert ok is True

    def test_blocks_duplicate(self):
        filt = MessageFilter(
            dedup_manager=DedupManager(ttl_seconds=60, enable_auto_cleanup=False),
            rate_limiter=RateLimiter(window_seconds=60, max_count=10, enable_auto_cleanup=False),
        )
        msg = _make_msg(dedupe_key="k1")
        filt.mark_sent(msg)
        ok, reason = filt.should_send(msg)
        assert ok is False
        assert "重复" in reason

    def test_blocks_rate_limited(self):
        filt = MessageFilter(
            dedup_manager=DedupManager(ttl_seconds=60, enable_auto_cleanup=False),
            rate_limiter=RateLimiter(window_seconds=60, max_count=1, enable_auto_cleanup=False),
            enable_dedup=False,  # disable dedup to test rate limit only
        )
        msg1 = _make_msg(dedupe_key="a")
        msg2 = _make_msg(dedupe_key="b")
        filt.mark_sent(msg1)
        ok, reason = filt.should_send(msg2)
        assert ok is False
        assert "限流" in reason

    def test_disabled_dedup_no_threads(self):
        filt = MessageFilter(
            enable_dedup=False, enable_rate_limit=False,
        )
        assert filt.dedup_manager is None
        assert filt.rate_limiter is None
        # should_send always passes
        msg = _make_msg()
        ok, _ = filt.should_send(msg)
        assert ok is True

    def test_mark_sent_with_disabled(self):
        filt = MessageFilter(enable_dedup=False, enable_rate_limit=False)
        msg = _make_msg()
        # Should not raise
        filt.mark_sent(msg)
