from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from app.adapters.opendss.engine import OpenDSSContextEngine
from app.adapters.opendss.topology_catalog import resolve_topology
from app.domain.errors import SimulationClosedError, SimulationNotFoundError
from app.domain.models import (
    CreateSimulationRequest,
    CreateSimulationResponse,
    ModelSummary,
    SimulationDetail,
    SimulationStatus,
    SimulationSummary,
    SolveResponse,
)
from app.platform.settings import get_settings

logger = logging.getLogger(__name__)
RECYCLE_THRESHOLD = get_settings().recycle_threshold


@dataclass
class SimulationSession:
    session_id: str
    topology: str
    created_at: datetime
    engine: OpenDSSContextEngine
    lock: asyncio.Lock
    model_summary: ModelSummary
    status: SimulationStatus = SimulationStatus.CREATED
    task_count: int = 0
    last_result: SolveResponse | None = None
    subscribers: set[WebSocket] = field(default_factory=set)


class SimulationService:
    def __init__(self) -> None:
        self._sessions: dict[str, SimulationSession] = {}
        self._registry_lock = asyncio.Lock()

    async def create(
        self, request: CreateSimulationRequest
    ) -> CreateSimulationResponse:
        topology_path = resolve_topology(request.topology)
        async with self._registry_lock:
            if len(self._sessions) >= get_settings().max_active_simulations:
                raise RuntimeError("Se alcanzó MAX_ACTIVE_SIMULATIONS")

        # Engine construction is synchronous/native. Keep it out of the event
        # loop because future networks can be much heavier than IEEE13.
        engine = await asyncio.to_thread(
            OpenDSSContextEngine,
            topology_path,
            request.load_multiplier,
        )

        session_id = str(uuid4())
        created_at = datetime.now(timezone.utc)
        session = SimulationSession(
            session_id=session_id,
            topology=request.topology,
            created_at=created_at,
            engine=engine,
            lock=asyncio.Lock(),
            status=SimulationStatus.READY,
            model_summary=engine.model_summary(request.topology.lower()),
        )

        async with self._registry_lock:
            self._sessions[session_id] = session

        logger.info(
            "simulation_created session_id=%s topology=%s context_id=%s load_multiplier=%s",
            session_id,
            session.topology,
            engine.identity,
            engine.load_multiplier,
        )

        return CreateSimulationResponse(
            session_id=session_id,
            topology=session.topology,
            load_multiplier=engine.load_multiplier,
            created_at=created_at,
        )

    async def solve(self, session_id: str) -> SolveResponse:
        session = self._sessions.get(session_id)
        if session is None:
            raise SimulationNotFoundError(
                f"No existe una simulación con session_id={session_id}"
            )

        # Never execute two solves simultaneously against the same context.
        # Different sessions still run concurrently because each has its own lock
        # and its own AltDSS context.
        if session.status == SimulationStatus.CLOSED:
            raise SimulationClosedError(f"La simulación {session_id} está cerrada")

        async with session.lock:
            session.status = SimulationStatus.RUNNING
            await self.broadcast(session, "simulation_started")
            await self.broadcast(
                session, "model_loaded", {"model": session.model_summary.model_dump()}
            )
            await self.broadcast(session, "solving")
            try:
                result = await asyncio.to_thread(
                    session.engine.solve,
                    session.session_id,
                    session.topology,
                )
            except Exception:
                session.status = SimulationStatus.ERROR
                raise
            session.task_count += 1
            session.last_result = result
            await self.broadcast(session, "result", {"result": result.model_dump()})
            session.status = SimulationStatus.COMPLETED
            await self.broadcast(session, "completed")

            if                         session.task_count >= RECYCLE_THRESHOLD:
                old_engine = session.engine
                await asyncio.to_thread(old_engine.close)
                session.engine = await asyncio.to_thread(
                    OpenDSSContextEngine,
                    resolve_topology(session.topology),
                    result.load_multiplier,
                )
                session.model_summary = await asyncio.to_thread(
                    session.engine.model_summary, session.topology
                )
                session.task_count = 0

        logger.info(
            "simulation_solved session_id=%s topology=%s elapsed_ms=%.3f converged=%s",
            session_id,
            session.topology,
            result.elapsed_ms,
            result.converged,
        )
        return result

    async def list_sessions(self) -> list[SimulationSummary]:
        return [
            SimulationSummary(
                session_id=session.session_id,
                topology=session.topology,
                status=session.status,
                created_at=session.created_at,
                task_count=session.task_count,
            )
            for session in self._sessions.values()
        ]

    def get_detail(self, session_id: str) -> SimulationDetail:
        session = self._get_session(session_id)
        return SimulationDetail(
            session_id=session.session_id,
            topology=session.topology,
            status=session.status,
            created_at=session.created_at,
            task_count=session.task_count,
            model_summary=session.model_summary,
            last_result=session.last_result,
            worker_identity=session.engine.identity,
        )

    async def close(self, session_id: str) -> None:
        session = self._get_session(session_id)
        async with session.lock:
            session.status = SimulationStatus.CLOSED
            await asyncio.to_thread(session.engine.close)
            await self.broadcast(
                session, "completed", {"status": SimulationStatus.CLOSED.value}
            )
            async with self._registry_lock:
                self._sessions.pop(session_id, None)
        session.subscribers.clear()

    async def subscribe(self, session_id: str, websocket: WebSocket) -> None:
        session = self._get_session(session_id)
        await websocket.accept()
        session.subscribers.add(websocket)
        await websocket.send_json(
            {
                "type": "snapshot",
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "simulation": SimulationSummary(
                    session_id=session.session_id,
                    topology=session.topology,
                    status=session.status,
                    created_at=session.created_at,
                    task_count=session.task_count,
                ).model_dump(mode="json"),
                "model": session.model_summary.model_dump(),
                "last_result": session.last_result.model_dump() if session.last_result else None,
            }
        )

    def unsubscribe(self, session_id: str, websocket: WebSocket) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.subscribers.discard(websocket)

    async def broadcast(
        self, session: SimulationSession, event_type: str, payload: dict | None = None
    ) -> None:
        message = {
            "type": event_type,
            "session_id": session.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(payload or {}),
        }
        disconnected: list[WebSocket] = []
        for websocket in tuple(session.subscribers):
            try:
                await websocket.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                disconnected.append(websocket)
        for websocket in disconnected:
            session.subscribers.discard(websocket)

    def _get_session(self, session_id: str) -> SimulationSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SimulationNotFoundError(
                f"No existe una simulación con session_id={session_id}"
            )
        return session

    def get_engine_identity(self, session_id: str) -> int:
        """Testing hook: proves two sessions do not share one Python context object."""
        session = self._get_session(session_id)
        return session.engine.identity

    def get_load_multiplier(self, session_id: str) -> float:
        session = self._get_session(session_id)
        return session.engine.load_multiplier
