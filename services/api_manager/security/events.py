from collections import Counter, deque
from datetime import datetime, timezone
import logging
from threading import Lock
from typing import Any
from enum import Enum

from services.api_manager.platform.settings import settings


logger = logging.getLogger(__name__)


class SecurityEvent(str, Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    AUTH_REJECTED = "AUTH_REJECTED"
    ACCESS_DENIED = "ACCESS_DENIED"
    WORKER_AUTH_REJECTED = "WORKER_AUTH_REJECTED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    OVERLOAD_REJECTED = "OVERLOAD_REJECTED"
    WORKER_LOST = "WORKER_LOST"
    JOB_RETRY = "JOB_RETRY"


class SecurityEventStore:
    def __init__(self, maxlen: int) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = Lock()

    def record(
        self,
        event: str,
        *,
        username: str | None = None,
        client_ip: str | None = None,
        path: str | None = None,
        status_code: int | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "username": username,
            "client_ip": client_ip,
            "path": path,
            "status_code": status_code,
            "detail": detail,
        }
        with self._lock:
            self._events.append(payload)
        logger.info("security_event", extra={"security_event": payload})
        return payload

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def summary(self) -> dict[str, int]:
        counts = Counter(item["event"] for item in self.list())
        return dict(counts)


security_events = SecurityEventStore(settings.security_event_buffer_size)


def record_security_event(
    event: str,
    **fields: Any,
) -> dict[str, Any]:
    return security_events.record(event, **fields)
