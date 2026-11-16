import argparse
import ipaddress
from urllib.parse import urlparse

import httpx


def local_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.hostname is None:
        raise ValueError("URL inválida")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if parsed.hostname != "localhost":
            raise ValueError("Solo se permiten targets loopback")
    else:
        if not address.is_loopback:
            raise ValueError("Solo se permiten targets loopback")
    return value.rstrip("/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://localhost:8443")
    parser.add_argument("--requests", type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.requests <= 500:
        raise ValueError("--requests debe estar entre 1 y 500")
    base_url = local_url(args.base_url)
    with httpx.Client(verify=False, timeout=10) as client:
        statuses = [
            client.get(f"{base_url}/simulations").status_code
            for _ in range(args.requests)
        ]
        print({status: statuses.count(status) for status in sorted(set(statuses))})
        health = client.get(f"{base_url}/health")
        print("health:", health.status_code)


if __name__ == "__main__":
    main()