from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


UserRole = Literal["admin", "user"]


class UserPublic(BaseModel):
    username: str
    role: UserRole
    disabled: bool = False


class UserRecord(UserPublic):
    password_hash: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenClaims(BaseModel):
    sub: str
    role: UserRole
    jti: str
    iss: str
    aud: str
    exp: int
    iat: int