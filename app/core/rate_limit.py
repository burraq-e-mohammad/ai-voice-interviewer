"""A small in-memory rate limiter (sliding window).

Why rate limiting?
  Every /chat request runs a speech model, calls Groq (which has a free-tier
  quota) and runs a TTS model. Without a limit, one client could overload the
  server or burn through the Groq quota.

How it works (sliding window):
  For each client (identified by IP address) we keep the timestamps of their
  recent requests. On a new request we drop timestamps older than the window,
  then check how many are left. If the client is at the limit, we refuse.

Limitation (documented on purpose):
  The data lives in this process's memory, so it resets on restart and is not
  shared between multiple server processes. That is fine for a local demo; a
  production system would use Redis or an API gateway instead.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from app.core.errors import RateLimitExceededError


class RateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # The clock is injectable so tests can control time instead of sleeping.
        # monotonic() never jumps backwards (unlike the wall clock).
        self._clock = clock
        self._requests: dict[str, deque[float]] = {}
        # Requests are handled concurrently, so protect the shared dict with a lock.
        self._lock = threading.Lock()

    def check(self, client_id: str) -> None:
        """Record one request for `client_id`, or raise if over the limit."""
        now = self._clock()
        window_start = now - self.window_seconds

        with self._lock:
            timestamps = self._requests.setdefault(client_id, deque())

            # Forget requests that are outside the current window.
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) >= self.max_requests:
                # The oldest request leaves the window first; tell the client when.
                retry_after = int(timestamps[0] - window_start) + 1
                raise RateLimitExceededError(
                    f"Too many requests. Try again in {retry_after} seconds.",
                    retry_after_seconds=retry_after,
                )

            timestamps.append(now)

            # Housekeeping: drop clients with no recent requests so the dict
            # does not grow forever. Cheap enough for a demo-sized server.
            if len(self._requests) > 10_000:
                self._requests = {k: v for k, v in self._requests.items() if v}
