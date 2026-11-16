from __future__ import annotations

import asyncio
import socket
import time
from dataclasses import dataclass
from typing import Protocol


class WorkerDiscovery(Protocol):
    async def endpoints(self, *, force: bool = False) -> list[str]: ...


@dataclass
class StaticWorkerDiscovery:
    worker_endpoints: list[str]

    async def endpoints(self, *, force: bool = False) -> list[str]:
        _ = force
        return [endpoint.rstrip("/") for endpoint in self.worker_endpoints if endpoint]


class DnsWorkerDiscovery:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        scheme: str = "http",
        refresh_seconds: float = 5.0,
    ) -> None:
        self._host = host.strip()
        self._port = int(port)
        self._scheme = scheme.strip().lower()
        self._refresh_seconds = max(float(refresh_seconds), 0.5)
        self._cached: list[str] = []
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    async def endpoints(self, *, force: bool = False) -> list[str]:
        now = time.monotonic()
        if (
            not force
            and self._cached
            and now - self._cached_at < self._refresh_seconds
        ):
            return list(self._cached)

        async with self._lock:
            now = time.monotonic()
            if (
                not force
                and self._cached
                and now - self._cached_at < self._refresh_seconds
            ):
                return list(self._cached)

            infos = await asyncio.to_thread(
                socket.getaddrinfo,
                self._host,
                self._port,
                socket.AF_INET,
                socket.SOCK_STREAM,
            )
            addresses = sorted({info[4][0] for info in infos})
            if not addresses:
                raise RuntimeError(
                    f"DNS discovery no devolvió workers para {self._host}:{self._port}"
                )

            self._cached = [
                f"{self._scheme}://{address}:{self._port}"
                for address in addresses
            ]
            self._cached_at = time.monotonic()
            return list(self._cached)
