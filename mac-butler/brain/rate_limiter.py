#!/usr/bin/env python3
"""QPM sliding window rate limiter — prevents OOM crashes when LLM calls stack up.
Max 10 LLM calls per minute, max 2 concurrent.
Inspired by CoPaw/AgentScope rate limiting pattern.
"""
from __future__ import annotations

import threading
import time
from collections import deque


class QPMRateLimiter:
    """Queries-per-minute sliding window with semaphore concurrency control."""

    def __init__(self, qpm: int = 10, max_concurrent: int = 2):
        self.qpm = qpm
        self.max_concurrent = max_concurrent
        self._timestamps: deque = deque()
        self._semaphore = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire a slot. Blocks if at limit. Returns False if timeout."""
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            with self._lock:
                now = time.monotonic()
                # Remove timestamps older than 60s
                while self._timestamps and self._timestamps[0] < now - 60:
                    self._timestamps.popleft()

                if len(self._timestamps) < self.qpm:
                    self._timestamps.append(now)
                    break

            time.sleep(0.5)
        else:
            return False

        return self._semaphore.acquire(timeout=max(0.0, deadline - time.monotonic()))

    def release(self):
        self._semaphore.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


# Global limiter — max 10 LLM calls per minute, max 2 concurrent
_LLM_LIMITER = QPMRateLimiter(qpm=10, max_concurrent=2)


def get_limiter() -> QPMRateLimiter:
    return _LLM_LIMITER
