from __future__ import annotations

from typing import Mapping


def _viewer_address_ip(value: str) -> str:
    value = value.strip()
    if not value:
        return "unknown"
    if value.startswith("[") and "]" in value:
        return value[1 : value.index("]")]
    # CloudFront-Viewer-Address is viewer-ip:source-port. IPv4 is trivial;
    # IPv6 values can contain many colons, so remove only the final port.
    host, sep, _port = value.rpartition(":")
    return host if sep and host else value


def external_client_ip(headers: Mapping[str, str], fallback: str = "unknown") -> str:
    cloudfront = headers.get("cloudfront-viewer-address", "")
    if cloudfront:
        return _viewer_address_ip(cloudfront)

    forwarded = headers.get("x-forwarded-for", "")
    if forwarded:
        # Local Caddy and common reverse proxies put the original client first.
        return forwarded.split(",", 1)[0].strip() or fallback

    return fallback


def external_is_https(headers: Mapping[str, str], scheme: str) -> bool:
    cloudfront_proto = headers.get("cloudfront-forwarded-proto", "")
    if cloudfront_proto:
        return cloudfront_proto.lower() == "https"

    forwarded_proto = headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.split(",", 1)[0].strip().lower() == "https"

    return scheme.lower() == "https"
