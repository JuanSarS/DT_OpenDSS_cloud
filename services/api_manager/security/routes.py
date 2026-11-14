from fastapi import APIRouter

from services.api_manager.auth.dependencies import AdminUser
from services.api_manager.security.events import security_events


router = APIRouter(prefix="/admin/security", tags=["security"])


@router.get("/events")
async def get_security_events(_: AdminUser) -> list[dict]:
    return security_events.list()


@router.get("/summary")
async def get_security_summary(_: AdminUser) -> dict[str, dict[str, int]]:
    return {"events": security_events.summary()}
