from fastapi import APIRouter

from services.api_manager.orchestration.container import (
    simulation_service,
)
from services.api_manager.platform.metrics import (
    metrics,
)
router = APIRouter(tags=["metrics"])


@router.get("/metrics", summary="Consultar métricas internas de rendimiento")
async def get_metrics() -> dict:
    return metrics.snapshot(simulation_service.metrics_snapshot())
