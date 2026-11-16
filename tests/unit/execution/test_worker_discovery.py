import asyncio
import socket

from services.api_manager.execution.worker_discovery import DnsWorkerDiscovery, StaticWorkerDiscovery


def test_static_worker_discovery_normalizes_urls() -> None:
    discovery = StaticWorkerDiscovery(["http://worker-1:8100/", "http://worker-2:8100"])
    assert asyncio.run(discovery.endpoints()) == [
        "http://worker-1:8100",
        "http://worker-2:8100",
    ]


def test_dns_worker_discovery_returns_all_ipv4_addresses(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.1.10", 8100)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.1.11", 8100)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.1.10", 8100)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    discovery = DnsWorkerDiscovery(
        host="simulation-worker.opendss.local",
        port=8100,
        refresh_seconds=1,
    )
    assert asyncio.run(discovery.endpoints(force=True)) == [
        "http://10.0.1.10:8100",
        "http://10.0.1.11:8100",
    ]
