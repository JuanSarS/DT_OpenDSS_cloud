from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from packages.contracts.auth import UserPublic
from services.api_manager.auth.constants import ACCESS_COOKIE_NAME
from services.api_manager.auth.jwt import decode_access_token
from services.api_manager.auth.users import load_users
from services.api_manager.platform.settings import settings
from services.api_manager.security.events import (
    SecurityEvent,
    record_security_event,
)


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/token",
    auto_error=False,
)

    
def _unauthorized() -> HTTPException:
    record_security_event(
        SecurityEvent.AUTH_REJECTED.value,
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing credentials",
    )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> UserPublic:
    
    if not settings.auth_enabled:
        return UserPublic(username="dev-admin", role="admin")
    
    if token is None:
        token = request.cookies.get(
                    ACCESS_COOKIE_NAME
                )
    if token is None:
        
        raise _unauthorized()

    try:
        claims = decode_access_token(
            token,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except ValueError as exc:
        raise _unauthorized() from exc

    user = load_users().get(claims.sub)
    if user is None or user.disabled or user.role != claims.role:
        raise _unauthorized()

    return UserPublic.model_validate(user.model_dump())


def get_user_from_token(token: str) -> UserPublic:
    if not settings.auth_enabled:
        return UserPublic(username="dev-admin", role="admin")

    try:
        claims = decode_access_token(
            token,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except ValueError as exc:
        raise _unauthorized() from exc

    user = load_users().get(claims.sub)
    if user is None or user.disabled or user.role != claims.role:
        raise _unauthorized()
    return UserPublic.model_validate(user.model_dump())


CurrentUser = Annotated[UserPublic, Depends(get_current_user)]


def require_admin(
    current_user: CurrentUser,
) -> UserPublic:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )

    return current_user


AdminUser = Annotated[UserPublic, Depends(require_admin)]
