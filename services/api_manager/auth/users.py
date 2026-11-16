import json

from packages.common.secrets import (
    read_secret,
)
from packages.contracts.auth import (
    UserRecord,
)
from services.api_manager.auth.passwords import (
    DUMMY_HASH,
    verify_password,
)


def load_users() -> dict[str, UserRecord]:
    raw = read_secret(
        "AUTH_USERS_JSON"
    )

    payload = json.loads(raw)

    return {
        username: UserRecord.model_validate(
            data
        )
        for username, data
        in payload.items()
    }


def authenticate_user(
    username: str,
    password: str,
) -> UserRecord | None:
    users = load_users()

    user = users.get(username)

    if user is None:
        verify_password(
            password,
            DUMMY_HASH,
        )
        return None

    if user.disabled:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    return user