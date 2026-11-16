import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from packages.contracts.auth import TokenResponse, UserPublic
from services.api_manager.auth.dependencies import CurrentUser
from services.api_manager.auth.jwt import create_access_token
from services.api_manager.auth.users import authenticate_user, load_users
from services.api_manager.platform.settings import settings
from services.api_manager.security.events import (
    SecurityEvent,
    record_security_event,
)
from services.api_manager.auth.constants import (
    ACCESS_COOKIE_NAME,
)
from services.api_manager.security.rate_limit import rate_limiter
from services.api_manager.security.proxy import external_client_ip, external_is_https


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
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    settings_value = settings
    client_ip = external_client_ip(
        request.headers,
        request.client.host if request.client else "unknown",
    )
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

    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=expires_in,
        httponly=True,
        secure=external_is_https(request.headers, request.url.scheme),
        samesite="strict",
        path="/",
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

@router.post(
    "/logout",
    status_code=204,
)
async def logout(
    response: Response,
) -> None:
    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )

@router.get(
    "/users",
    response_model=list[UserPublic],
)
async def list_users(
    current_user: CurrentUser,
) -> list[UserPublic]:

    return sorted(
        [
            UserPublic(
                username=user.username,
                role=user.role,
                disabled=user.disabled,
            )
            for user
            in load_users().values()
            if (
                not user.disabled
                and user.username
                != current_user.username
            )
        ],
        key=lambda user: user.username,
    )