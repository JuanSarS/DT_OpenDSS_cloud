from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status

from app.domain.models import (
    CreateSimulationRequest,
    CreateSimulationResponse,
    SimulationDetail,
    SimulationSummary,
    SolveResponse,
)
from app.domain.errors import SimulationClosedError, SimulationNotFoundError, TopologyNotFoundError
from app.orchestration.container import simulation_service

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
    except TopologyNotFoundError as exc:
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


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar una simulación")
async def delete_simulation(session_id: str) -> None:
    try:
        await simulation_service.close(session_id)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{session_id}/solve",
    response_model=SolveResponse,
    summary="Resolver una simulación",
    description="Ejecuta un solve snapshot fuera del event loop y emite eventos WebSocket.",
)
async def solve_simulation(session_id: str) -> SolveResponse:
    try:
        return await simulation_service.solve(session_id)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SimulationClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
