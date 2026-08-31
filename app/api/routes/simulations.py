from fastapi import APIRouter, HTTPException, status

from app.domain.models import (
    CreateSimulationRequest,
    CreateSimulationResponse,
    SolveResponse,
)
from app.domain.errors import SimulationNotFoundError, TopologyNotFoundError
from app.orchestration.container import simulation_service

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post(
    "",
    response_model=CreateSimulationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_simulation(
    request: CreateSimulationRequest,
) -> CreateSimulationResponse:
    try:
        return await simulation_service.create(request)
    except TopologyNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/solve", response_model=SolveResponse)
async def solve_simulation(session_id: str) -> SolveResponse:
    try:
        return await simulation_service.solve(session_id)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
