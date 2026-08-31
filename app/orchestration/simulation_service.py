from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.adapters.opendss.engine import OpenDSSContextEngine
from app.adapters.opendss.topology_catalog import resolve_topology
from app.domain.errors import SimulationNotFoundError
from app.domain.models import (
    CreateSimulationRequest,
    CreateSimulationResponse,
    SolveResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class SimulationSession:
    session_id: str
    topology: str
    created_at: datetime
    engine: OpenDSSContextEngine
    lock: asyncio.Lock


class SimulationService:
    def __init__(self) -> None:
        self._sessions: dict[str, SimulationSession] = {}
        self._registry_lock = asyncio.Lock()

    async def create(
        self, request: CreateSimulationRequest
    ) -> CreateSimulationResponse:
        topology_path = resolve_topology(request.topology)

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
            topology=request.topology.lower(),
            created_at=created_at,
            engine=engine,
            lock=asyncio.Lock(),
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
        async with session.lock:
            result = await asyncio.to_thread(
                session.engine.solve,
                session.session_id,
                session.topology,
            )

        logger.info(
            "simulation_solved session_id=%s topology=%s elapsed_ms=%.3f converged=%s",
            session_id,
            session.topology,
            result.elapsed_ms,
            result.converged,
        )
        return result

    def get_engine_identity(self, session_id: str) -> int:
        """Testing hook: proves two sessions do not share one Python context object."""
        session = self._sessions.get(session_id)
        if session is None:
            raise SimulationNotFoundError(session_id)
        return session.engine.identity

    def get_load_multiplier(self, session_id: str) -> float:
        session = self._sessions.get(session_id)
        if session is None:
            raise SimulationNotFoundError(session_id)
        return session.engine.load_multiplier
