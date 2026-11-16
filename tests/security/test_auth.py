import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from packages.contracts.auth import UserRecord
from services.api_manager import main
from services.api_manager.auth import routes
from services.api_manager.auth import dependencies
from services.api_manager.auth.jwt import create_access_token
from services.api_manager.platform.settings import settings
from starlette.requests import Request

def test_missing_token_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "auth_enabled",
        True,
    )

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": (
                "testserver",
                80,
            ),
            "client": (
                "127.0.0.1",
                12345,
            ),
        }
    )

    with pytest.raises(
        HTTPException
    ) as error:
        dependencies.get_current_user(
            request,
            None,
        )

    assert (
        error.value.status_code
        == 401
    )

def test_valid_token_returns_user(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setenv("JWT_SECRET", "test-secret-" * 4)
    user = UserRecord(
        username="user1",
        role="user",
        disabled=False,
        password_hash="not-used",
    )
    token, _ = create_access_token(
        user,
        expires_minutes=30,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    monkeypatch.setattr(dependencies, "load_users", lambda: {"user1": user})
    assert dependencies.get_user_from_token(token).username == "user1"


def test_http_login_cookie_authenticates_follow_up_request(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setenv("JWT_SECRET", "test-secret-" * 4)
    user = UserRecord(
        username="user1",
        role="user",
        disabled=False,
        password_hash="not-used",
    )
    monkeypatch.setattr(routes, "authenticate_user", lambda username, password: user)
    monkeypatch.setattr(routes, "load_users", lambda: {"user1": user})
    monkeypatch.setattr(dependencies, "load_users", lambda: {"user1": user})

    with TestClient(main.app) as client:
        login_response = client.post(
            "/auth/token",
            data={"username": "user1", "password": "password"},
        )

        assert login_response.status_code == 200
        assert "Secure" not in login_response.headers["set-cookie"]
        assert client.get("/auth/me").status_code == 200
