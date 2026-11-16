from __future__ import annotations

import argparse
import getpass
import os
import ssl
from pathlib import Path

import httpx


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default="https://localhost:8443")
    parser.add_argument(
        "--username",
        default=os.getenv("OPENDSS_SMOKE_USERNAME", "admin"),
    )
    parser.add_argument(
        "--ca-cert",
        default=os.getenv("OPENDSS_CA_CERT", ""),
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Solo diagnostico local: no verifica TLS",
    )


def ssl_context(
    base_url: str,
    ca_cert: str,
    insecure: bool,
) -> ssl.SSLContext | bool:
    if not base_url.lower().startswith("https://"):
        return True

    if insecure:
        return ssl._create_unverified_context()

    if not ca_cert:
        return ssl.create_default_context()

    path = Path(ca_cert)

    if not path.exists():
        raise FileNotFoundError(
            f"No existe la CA indicada: {path}."
        )

    return ssl.create_default_context(cafile=str(path))


def websocket_ssl_context(
    base_url: str,
    ca_cert: str,
    insecure: bool,
) -> ssl.SSLContext | None:
    if not base_url.lower().startswith("https://"):
        return None

    context = ssl_context(base_url, ca_cert, insecure)
    assert isinstance(context, ssl.SSLContext)
    return context


def websocket_base(base_url: str) -> str:
    return (
        base_url.rstrip("/")
        .replace("https://", "wss://")
        .replace("http://", "ws://")
    )


def read_password(username: str) -> str:
    password = os.getenv("OPENDSS_SMOKE_PASSWORD")

    if password:
        return password

    return getpass.getpass(f"Password de {username}: ")


async def open_authenticated_client(
    *,
    base_url: str,
    username: str,
    ca_cert: str,
    insecure: bool,
    timeout: float = 180.0,
) -> tuple[httpx.AsyncClient, str]:
    verify = ssl_context(
        base_url,
        ca_cert,
        insecure,
    )

    client = httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=timeout,
        verify=verify,
    )

    response = await client.post(
        "/auth/token",
        data={
            "username": username,
            "password": read_password(username),
        },
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded"
        },
    )

    response.raise_for_status()

    token = response.json()["access_token"]

    client.headers["Authorization"] = (
        f"Bearer {token}"
    )

    return client, token
