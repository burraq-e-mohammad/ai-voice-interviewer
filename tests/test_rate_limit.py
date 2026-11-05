"""Unit tests for the sliding-window rate limiter.

We use a fake clock so we can "travel in time" instantly instead of sleeping.
"""

import pytest

from app.core.errors import RateLimitExceededError
from app.core.rate_limit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_requests_up_to_the_limit() -> None:
    limiter = RateLimiter(max_requests=3, window_seconds=60, clock=FakeClock())

    for _ in range(3):
        limiter.check("1.2.3.4")  # must not raise


def test_blocks_the_request_over_the_limit() -> None:
    limiter = RateLimiter(max_requests=2, window_seconds=60, clock=FakeClock())
    limiter.check("1.2.3.4")
    limiter.check("1.2.3.4")

    with pytest.raises(RateLimitExceededError) as exc_info:
        limiter.check("1.2.3.4")

    assert exc_info.value.retry_after_seconds == 61


def test_allows_again_after_the_window_passes() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_requests=1, window_seconds=60, clock=clock)
    limiter.check("1.2.3.4")

    clock.now += 61  # jump forward past the window

    limiter.check("1.2.3.4")  # must not raise


def test_retry_after_shrinks_as_time_passes() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_requests=1, window_seconds=60, clock=clock)
    limiter.check("1.2.3.4")
    clock.now += 50

    with pytest.raises(RateLimitExceededError) as exc_info:
        limiter.check("1.2.3.4")

    assert exc_info.value.retry_after_seconds == 11


def test_clients_are_limited_independently() -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60, clock=FakeClock())
    limiter.check("1.1.1.1")

    limiter.check("2.2.2.2")  # a different client still has its own quota
