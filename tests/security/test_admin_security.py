import pytest
from fastapi import HTTPException

from packages.contracts.auth import UserPublic
from services.api_manager.auth.dependencies import require_admin


def test_user_cannot_require_admin() -> None:
    with pytest.raises(HTTPException) as error:
        require_admin(UserPublic(username="user1", role="user"))
    assert error.value.status_code == 403


def test_admin_is_allowed() -> None:
    admin = UserPublic(username="admin", role="admin")
    assert require_admin(admin) == admin