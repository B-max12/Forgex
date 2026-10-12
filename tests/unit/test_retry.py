from __future__ import annotations

import pytest

from forgex.orchestration.retry import RetryPolicy, is_retryable, run_with_retries
from forgex.schemas.error import AuthenticationError, ProviderError, RateLimitError


class Recorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)


async def test_success_first_attempt():
    calls: list[int] = []

    async def func() -> str:
        calls.append(1)
        return "ok"

    rec = Recorder()
    result, attempts = await run_with_retries(func, policy=RetryPolicy(jitter=False), sleep=rec.sleep)
    assert (result, attempts) == ("ok", 1)
    assert rec.delays == []


async def test_retries_rate_limit_then_succeeds():
    state = {"n": 0}

    async def func() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise RateLimitError("limited")
        return "ok"

    rec = Recorder()
    result, attempts = await run_with_retries(
        func,
        policy=RetryPolicy(max_attempts=3, initial_delay=1.0, jitter=False),
        sleep=rec.sleep,
    )
    assert (result, attempts) == ("ok", 3)
    assert rec.delays == [1.0, 2.0]


async def test_no_retry_on_auth_error():
    state = {"n": 0}

    async def func() -> str:
        state["n"] += 1
        raise AuthenticationError("bad key")

    with pytest.raises(AuthenticationError):
        await run_with_retries(func, policy=RetryPolicy(max_attempts=3), sleep=Recorder().sleep)
    assert state["n"] == 1


async def test_exhausts_attempts_and_raises_last():
    async def func() -> str:
        raise ProviderError("boom", retryable=True)

    rec = Recorder()
    with pytest.raises(ProviderError):
        await run_with_retries(
            func,
            policy=RetryPolicy(max_attempts=3, jitter=False, max_delay=5.0),
            sleep=rec.sleep,
        )
    assert rec.delays == [1.0, 2.0]


def test_is_retryable_classification():
    assert is_retryable(RateLimitError("x"))
    assert is_retryable(ProviderError("x", retryable=True))
    assert not is_retryable(ProviderError("x"))
    assert not is_retryable(AuthenticationError("x"))
    assert not is_retryable(ValueError("x"))
