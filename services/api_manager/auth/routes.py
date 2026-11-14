import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from packages.contracts.auth import TokenResponse, UserPublic
from services.api_manager.auth.dependencies import CurrentUser
from services.api_manager.auth.jwt import create_access_token
from services.api_manager.auth.users import authenticate_user
from services.api_manager.platform.settings import settings
from services.api_manager.security.events import (
    SecurityEvent,
    record_security_event,
)
from services.api_manager.security.rate_limit import rate_limiter


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/token",
    response_model=TokenResponse,
)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    settings_value = settings
    client_ip = request.client.host if request.client else "unknown"
    retry_after = rate_limiter.check(
        f"login:{client_ip}",
        settings_value.login_rate_limit_requests,
        settings_value.login_rate_limit_window_seconds,
    ) if settings_value.rate_limit_enabled else None
    if retry_after is not None:
        record_security_event(
            SecurityEvent.RATE_LIMITED.value,
            client_ip=client_ip,
            path="/auth/token",
            status_code=429,
            detail="login rate limit",
        )
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )
    user = authenticate_user(
        form_data.username,
        form_data.password,
    )

    if user is None:
        record_security_event(
            SecurityEvent.LOGIN_FAILED.value,
            username=form_data.username,
            status_code=401,
            detail="invalid credentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, expires_in = create_access_token(
        user,
        expires_minutes=settings.jwt_expire_minutes,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    record_security_event(
        SecurityEvent.LOGIN_SUCCESS.value,
        username=user.username,
        status_code=200,
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
    )


@router.get(
    "/me",
    response_model=UserPublic,
)
async def get_me(
    current_user: CurrentUser,
) -> UserPublic:
    return current_user
