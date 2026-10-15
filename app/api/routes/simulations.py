from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status

from app.domain.models import (
    CreateSimulationRequest,
    CreateSimulationResponse,
    SimulationDetail,
    SimulationSummary,
    QSTSResult,
    QSTSSolveResponse,
    QSTSSolveSummary,
    SolveRequest,
    SolveResponse,
)
from app.domain.errors import (
    SimulationClosedError,
    SimulationNotFoundError,
    TopologyNotFoundError,
)
from app.orchestration.container import simulation_service
from app.platform.metrics import metrics
import time

router = APIRouter(prefix="/simulations", tags=["simulations"])
websocket_router = APIRouter(prefix="/ws/simulations", tags=["simulations"])


@router.post(
    "",
    response_model=CreateSimulationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una simulación",
    description="Crea una sesión autoritativa con un contexto OpenDSS aislado.",
)
async def create_simulation(
    request: CreateSimulationRequest,
) -> CreateSimulationResponse:
    try:
        return await simulation_service.create(request)
    except (TopologyNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[SimulationSummary], summary="Listar simulaciones activas")
async def list_simulations() -> list[SimulationSummary]:
    return await simulation_service.list_sessions()


@router.get("/{session_id}", response_model=SimulationDetail, summary="Consultar una simulación")
async def get_simulation(session_id: str) -> SimulationDetail:
    try:
        return simulation_service.get_detail(session_id)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{session_id}/results",
    summary="Consultar los resultados de la última simulación",
)
async def get_simulation_results(session_id: str) -> dict:
    started_at = time.perf_counter()
    try:
        result = simulation_service.get_results(session_id)
        metrics.observe(
            "get_results_ms",
            (time.perf_counter() - started_at) * 1000.0,
        )
        return result
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar una simulación")
async def delete_simulation(session_id: str) -> None:
    try:
        await simulation_service.close(session_id)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{session_id}/solve",
    response_model=SolveResponse | QSTSSolveResponse,
    summary="Resolver una simulación",
    description=(
        "Ejecuta Snapshot o QSTS fuera del event loop. "
        "Sin body conserva el comportamiento Snapshot."
    ),
)
async def solve_simulation(
    session_id: str,
    request: SolveRequest | None = None,
) -> SolveResponse | QSTSSolveResponse:
    started_at = time.perf_counter()
    try:
        result = await simulation_service.solve(session_id, request)
        metrics.observe(
            "qsts_request_ms" if isinstance(result, QSTSResult) else "snapshot_request_ms",
            (time.perf_counter() - started_at) * 1000.0,
        )
        if isinstance(result, QSTSResult):
            return QSTSSolveResponse(
                session_id=session_id,
                status=simulation_service.get_detail(session_id).status,
                summary=QSTSSolveSummary(
                    total_steps=result.total_steps,
                    converged_steps=result.converged_steps,
                    failed_steps=result.failed_steps,
                    elapsed_ms=result.elapsed_ms,
                    solve_mean_ms=result.solve_mean_ms,
                    solve_p50_ms=result.solve_p50_ms,
                    solve_p95_ms=result.solve_p95_ms,
                    solve_max_ms=result.solve_max_ms,
                    rss_start_mb=result.rss_start_mb,
                    rss_peak_mb=result.rss_peak_mb,
                ),
            )
        return result
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SimulationClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@websocket_router.websocket("/{session_id}")
async def simulation_websocket(websocket: WebSocket, session_id: str) -> None:
    try:
        await simulation_service.subscribe(session_id, websocket)
        while True:
            await websocket.receive_text()
    except SimulationNotFoundError:
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        simulation_service.unsubscribe(session_id, websocket)
    finally:
        simulation_service.unsubscribe(session_id, websocket)
