import hmac
import logging

from fastapi import Header, HTTPException, status

from packages.common.secrets import read_secret


logger = logging.getLogger(__name__)


async def require_worker_token(
    authorization: str | None = Header(default=None),
) -> None:
    expected = read_secret("WORKER_SHARED_TOKEN")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, expected):
        logger.warning("security_event=WORKER_AUTH_REJECTED")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Worker authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )