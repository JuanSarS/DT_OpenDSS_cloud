from collections import defaultdict, deque
from threading import Lock
import time


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            requests = self._requests[key]
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= limit:
                return max(1, int(requests[0] + window_seconds - now))
            requests.append(now)
        return None


rate_limiter = InMemoryRateLimiter()