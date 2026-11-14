import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status

from packages.contracts.errors import (
    AccessDeniedError,
    OverloadedError,
    QuotaExceededError,
    SimulationClosedError,
    SimulationNotFoundError,
    TopologyNotFoundError,
)
from packages.contracts.models import (
    CreateSimulationRequest,
    CreateSimulationResponse,
    QSTSResult,
    QSTSSolveResponse,
    QSTSSolveSummary,
    SimulationDetail,
    SimulationSummary,
    SolveRequest,
    SolveResponse,
)
from services.api_manager.auth.dependencies import (
    CurrentUser,
    get_user_from_token,
)
from services.api_manager.orchestration.container import simulation_service
from services.api_manager.platform.metrics import metrics
from services.api_manager.security.events import (
    SecurityEvent,
    record_security_event,
)

router = APIRouter(prefix="/simulations", tags=["simulations"])
websocket_router = APIRouter(prefix="/ws/simulations", tags=["simulations"])


@router.post("", response_model=CreateSimulationResponse, status_code=status.HTTP_201_CREATED)
async def create_simulation(
    request: CreateSimulationRequest,
    current_user: CurrentUser,
) -> CreateSimulationResponse:
    try:
        return await simulation_service.create(request, owner_id=current_user.username)
    except (TopologyNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[SimulationSummary])
async def list_simulations(current_user: CurrentUser) -> list[SimulationSummary]:
    return await simulation_service.list_sessions(
        current_user.username,
        current_user.role == "admin",
    )


@router.get("/{session_id}", response_model=SimulationDetail)
async def get_simulation(session_id: str, current_user: CurrentUser) -> SimulationDetail:
    try:
        return simulation_service.get_detail(
            session_id,
            user_id=current_user.username,
            is_admin=current_user.role == "admin",
        )
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AccessDeniedError as exc:
        record_security_event(
            SecurityEvent.ACCESS_DENIED.value,
            username=current_user.username,
            path=f"/simulations/{session_id}",
            status_code=403,
            detail="session ownership",
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{session_id}/results")
async def get_simulation_results(session_id: str, current_user: CurrentUser) -> dict:
    started_at = time.perf_counter()
    try:
        result = simulation_service.get_results(
            session_id,
            user_id=current_user.username,
            is_admin=current_user.role == "admin",
        )
        metrics.observe("get_results_ms", (time.perf_counter() - started_at) * 1000.0)
        return result
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AccessDeniedError as exc:
        record_security_event(
            SecurityEvent.ACCESS_DENIED.value,
            username=current_user.username,
            path=f"/simulations/{session_id}/results",
            status_code=403,
            detail="session ownership",
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_simulation(session_id: str, current_user: CurrentUser) -> None:
    try:
        await simulation_service.close(
            session_id,
            user_id=current_user.username,
            is_admin=current_user.role == "admin",
        )
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AccessDeniedError as exc:
        record_security_event(
            SecurityEvent.ACCESS_DENIED.value,
            username=current_user.username,
            path=f"/simulations/{session_id}",
            status_code=403,
            detail="session ownership",
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{session_id}/solve", response_model=SolveResponse | QSTSSolveResponse)
async def solve_simulation(
    session_id: str,
    current_user: CurrentUser,
    request: SolveRequest | None = None,
) -> SolveResponse | QSTSSolveResponse:
    started_at = time.perf_counter()
    try:
        result = await simulation_service.solve(
            session_id,
            request,
            user_id=current_user.username,
            is_admin=current_user.role == "admin",
        )
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
    except AccessDeniedError as exc:
        record_security_event(
            SecurityEvent.ACCESS_DENIED.value,
            username=current_user.username,
            path=f"/simulations/{session_id}/solve",
            status_code=403,
            detail="session ownership",
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except SimulationClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (QuotaExceededError, OverloadedError) as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@websocket_router.websocket("/{session_id}")
async def simulation_websocket(websocket: WebSocket, session_id: str) -> None:
    try:
        token = None
        protocols = [item.strip() for item in websocket.headers.get("sec-websocket-protocol", "").split(",")]
        if "opendss.jwt" in protocols:
            index = protocols.index("opendss.jwt")
            if index + 1 < len(protocols):
                token = protocols[index + 1]
        user = get_user_from_token(token or "")
        await simulation_service.subscribe(
            session_id,
            websocket,
            user_id=user.username,
            is_admin=user.role == "admin",
            subprotocol="opendss.jwt" if token else None,
        )
        while True:
            await websocket.receive_text()
    except (SimulationNotFoundError, AccessDeniedError, HTTPException):
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        simulation_service.unsubscribe(session_id, websocket)
    finally:
        simulation_service.unsubscribe(session_id, websocket)
