"""Retry policy for transient failures (spec section 29).

Retried: rate limits, provider timeouts, transient network errors, 5xx.
Never retried: authentication failures, invalid requests, permission
errors. Exponential backoff with optional jitter; `sleep` and `rand` are
injectable so tests run instantly and deterministically.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay: float = 1.0
    backoff_factor: float = 2.0
    max_delay: float = 30.0
    jitter: bool = True


def is_retryable(exc: BaseException) -> bool:
    return bool(getattr(exc, "retryable", False))


async def run_with_retries(
    func: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    retryable: Callable[[BaseException], bool] = is_retryable,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rand: Callable[[], float] = random.random,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> tuple[T, int]:
    """Run `func` with retries. Returns ``(result, attempts)``; re-raises the
    last error when attempts are exhausted or the error is not retryable."""
    policy = policy or RetryPolicy()
    delay = policy.initial_delay
    attempts = 0
    while True:
        attempts += 1
        try:
            res = await func()
            return res, attempts
        except Exception as exc:
            if attempts >= policy.max_attempts or not retryable(exc):
                try:
                    setattr(exc, "attempts", attempts)
                except (AttributeError, TypeError):
                    pass
                raise
            wait = min(delay, policy.max_delay)
            if policy.jitter:
                wait = wait * (0.5 + 0.5 * rand())
            if on_retry is not None:
                on_retry(attempts, exc, wait)
            await sleep(wait)
            delay = min(delay * policy.backoff_factor, policy.max_delay)
