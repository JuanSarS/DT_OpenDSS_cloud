import argparse
import ipaddress
from urllib.parse import urlparse

import httpx


def local_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("El target debe ser una URL HTTP(S) válida")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if parsed.hostname not in {"localhost"}:
            raise ValueError("Solo se permiten targets loopback")
    else:
        if not address.is_loopback:
            raise ValueError("Solo se permiten targets loopback")
    return value.rstrip("/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://localhost:8443")
    args = parser.parse_args()
    base_url = local_url(args.base_url)
    with httpx.Client(verify=False, timeout=10) as client:
        for path in ("/simulations", "/metrics"):
            response = client.get(f"{base_url}{path}")
            print(path, response.status_code, response.text[:160])


if __name__ == "__main__":
    main()