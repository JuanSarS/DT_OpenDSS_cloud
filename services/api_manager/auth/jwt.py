from datetime import (
    datetime,
    timedelta,
    timezone,
)
from uuid import uuid4

import jwt
from jwt.exceptions import (
    InvalidTokenError,
)

from packages.common.secrets import (
    read_secret,
)
from packages.contracts.auth import (
    TokenClaims,
    UserRecord,
)


ALGORITHM = "HS256"


def create_access_token(
    user: UserRecord,
    *,
    expires_minutes: int,
    issuer: str,
    audience: str,
) -> tuple[str, int]:
    now = datetime.now(
        timezone.utc
    )

    expires = now + timedelta(
        minutes=expires_minutes
    )

    payload = {
        "sub": user.username,
        "role": user.role,
        "jti": str(uuid4()),
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int(
            expires.timestamp()
        ),
    }

    token = jwt.encode(
        payload,
        read_secret("JWT_SECRET"),
        algorithm=ALGORITHM,
    )

    return (
        token,
        int(
            timedelta(
                minutes=expires_minutes
            ).total_seconds()
        ),
    )


def decode_access_token(
    token: str,
    *,
    issuer: str,
    audience: str,
) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            read_secret(
                "JWT_SECRET"
            ),
            algorithms=[
                ALGORITHM
            ],
            issuer=issuer,
            audience=audience,
        )

        return TokenClaims.model_validate(
            payload
        )

    except InvalidTokenError as exc:
        raise ValueError(
            "Invalid access token"
        ) from exc