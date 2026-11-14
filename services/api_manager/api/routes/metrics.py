from fastapi import APIRouter

from services.api_manager.orchestration.container import (
    simulation_service,
)
from services.api_manager.platform.metrics import (
    metrics,
)
from services.api_manager.auth.dependencies import AdminUser
router = APIRouter(tags=["metrics"])


@router.get("/metrics", summary="Consultar métricas internas de rendimiento")
async def get_metrics(_: AdminUser) -> dict:
    return metrics.snapshot(simulation_service.metrics_snapshot())
