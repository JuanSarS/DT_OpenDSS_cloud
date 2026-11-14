import argparse
import base64
import json
from getpass import getpass
from urllib.parse import urlparse

import httpx

from tools.security_lab.unauthorized_client import local_url


def decode_payload(token: str) -> dict:
    encoded = token.split(".")[1]
    encoded += "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(encoded))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://localhost:8443")
    parser.add_argument("--username", default="user1")
    args = parser.parse_args()
    base_url = local_url(args.base_url)
    with httpx.Client(verify=False, timeout=10) as client:
        response = client.post(
            f"{base_url}/auth/token",
            data={"username": args.username, "password": getpass("Password: ")},
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        print("Claims:", json.dumps(decode_payload(token), indent=2))
        header, payload, signature = token.split(".")
        claims = decode_payload(token)
        claims["role"] = "admin"
        changed = base64.urlsafe_b64encode(
            json.dumps(claims, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        tampered = f"{header}.{changed}.{signature}"
        result = client.get(
            f"{base_url}/metrics",
            headers={"Authorization": f"Bearer {tampered}"},
        )
        print("Tampered token response:", result.status_code)


if __name__ == "__main__":
    main()