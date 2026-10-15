from fastapi import APIRouter

from app.orchestration.container import simulation_service
from app.platform.metrics import metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", summary="Consultar métricas internas de rendimiento")
async def get_metrics() -> dict:
    return metrics.snapshot(simulation_service.metrics_snapshot())
