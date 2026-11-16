import pytest
from fastapi import HTTPException

from services.api_manager.auth import dependencies
from services.api_manager.platform.settings import settings


def test_websocket_token_is_required_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setenv("JWT_SECRET", "test-secret-" * 4)
    with pytest.raises(HTTPException) as error:
        dependencies.get_user_from_token("")
    assert error.value.status_code == 401