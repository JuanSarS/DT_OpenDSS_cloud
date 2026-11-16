from services.api_manager.security.proxy import external_client_ip, external_is_https


def test_cloudfront_viewer_address_wins() -> None:
    headers = {
        "cloudfront-viewer-address": "198.51.100.10:46532",
        "x-forwarded-for": "203.0.113.9, 192.0.2.1",
    }
    assert external_client_ip(headers, "10.0.0.1") == "198.51.100.10"


def test_local_proxy_falls_back_to_xff() -> None:
    assert external_client_ip({"x-forwarded-for": "127.0.0.1"}, "10.0.0.1") == "127.0.0.1"


def test_cloudfront_https_is_detected_even_if_origin_is_http() -> None:
    assert external_is_https({"cloudfront-forwarded-proto": "https"}, "http") is True


def test_plain_http_testclient_remains_non_secure_cookie_mode() -> None:
    assert external_is_https({}, "http") is False
