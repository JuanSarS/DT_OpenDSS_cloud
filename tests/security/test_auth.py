import pytest
from fastapi import HTTPException

from packages.contracts.auth import UserRecord
from services.api_manager.auth import dependencies
from services.api_manager.auth.jwt import create_access_token
from services.api_manager.platform.settings import settings


def test_missing_token_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(None)
    assert error.value.status_code == 401


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