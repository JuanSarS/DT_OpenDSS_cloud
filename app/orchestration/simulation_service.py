from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from packages.simulation_core.engine import OpenDSSContextEngine
from services.api_manager.execution.local_executor import (
    LocalSimulationExecutor,
)
from app.adapters.opendss.topology_catalog import resolve_topology
from app.domain.errors import SimulationClosedError, SimulationNotFoundError
from app.domain.models import (
    CreateSimulationRequest,
    CreateSimulationResponse,
    ModelSummary,
    SimulationDetail,
    SimulationStatus,
    SimulationSummary,
    QSTSConfig,
    QSTSResult,
    QSTSStepResult,
    SolveRequest,
    SolveResponse,
)
from app.platform.settings import get_settings
from app.platform.metrics import metrics

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
    last_result: SolveResponse | QSTSResult | None = None
    simulation_type: str | None = None
    last_error: str | None = None
    current_step: int | None = None
    total_steps: int | None = None
    progress_pct: float | None = None
    simulated_hour: float | None = None
    last_qsts_step: QSTSStepResult | None = None
    subscribers: set[WebSocket] = field(default_factory=set)


class SimulationService:
    def __init__(self) -> None:
        self._sessions: dict[str, SimulationSession] = {}
        self._registry_lock = asyncio.Lock()
        self._executor = LocalSimulationExecutor()

    async def create(
        self, request: CreateSimulationRequest
    ) -> CreateSimulationResponse:
        started_at = time.perf_counter()
        topology_path = resolve_topology(request.topology)
        async with self._registry_lock:
            if len(self._sessions) >= get_settings().max_active_simulations:
                raise RuntimeError("Se alcanzó MAX_ACTIVE_SIMULATIONS")

        # Engine construction is synchronous/native. Keep it out of the event
        # loop because future networks can be much heavier than IEEE13.
        engine = await self._executor.create_engine(
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
            model_summary=self._executor.model_summary(
                engine,
                request.topology.lower(),
            )
        )

        async with self._registry_lock:
            self._sessions[session_id] = session

        logger.info(
            "simulation_created session_id=%s topology=%s context_id=%s load_multiplier=%s",
            session_id,
            session.topology,
            self._executor.identity(engine),
            self._executor.load_multiplier(engine),
        )
        metrics.observe(
            "session_create_ms",
            (time.perf_counter() - started_at) * 1000.0,
        )

        return CreateSimulationResponse(
            session_id=session_id,
            topology=session.topology,
            load_multiplier=self._executor.load_multiplier(engine),
            created_at=created_at,
        )

    async def solve(
        self, session_id: str, request: SolveRequest | None = None
    ) -> SolveResponse | QSTSResult:
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
            session.last_error = None
            request = request or SolveRequest()
            session.simulation_type = request.simulation_type
            session.current_step = None
            session.total_steps = None
            session.progress_pct = None
            session.simulated_hour = None
            session.last_qsts_step = None
            if request.simulation_type == "qsts" and request.qsts is not None:
                session.total_steps = request.qsts.to_config().total_steps
            await self.broadcast(session, "simulation_started")
            await self.broadcast(
                session, "model_loaded", {"model": session.model_summary.model_dump()}
            )
            await self.broadcast(session, "solving")
            try:
                if request.simulation_type == "snapshot":
                    result = await self._executor.solve_snapshot(
                        session.engine,
                        session.session_id,
                        session.topology,
                        request.load_multiplier,
                    )
                else:
                    config = request.qsts.to_config()
                    result = await self._executor.solve_qsts(
                        session.engine,
                        config,
                        self._qsts_progress_callback(
                            session,
                            asyncio.get_running_loop(),
                        ),
                    )
            except Exception as exc:
                session.status = SimulationStatus.ERROR
                session.last_error = str(exc)
                await self.broadcast(
                    session,
                    "error",
                    {
                        "simulation_type": session.simulation_type,
                        "detail": "No fue posible completar la simulación.",
                    },
                )
                raise
            session.task_count += 1
            session.last_result = result
            if isinstance(result, SolveResponse):
                metrics.increment("snapshot_runs")
                metrics.observe("snapshot_solve_ms", result.elapsed_ms)
            else:
                metrics.increment("qsts_runs")
                metrics.increment("qsts_total_steps", result.total_steps)
                metrics.observe("qsts_elapsed_ms", result.elapsed_ms)
                for step in result.steps:
                    metrics.observe("qsts_step_ms", step.solve_ms)
            if isinstance(result, QSTSResult):
                session.current_step = result.total_steps
                session.total_steps = result.total_steps
                session.progress_pct = 100.0
                session.simulated_hour = (
                    result.steps[-1].simulated_hour if result.steps else None
                )
                session.last_qsts_step = result.steps[-1] if result.steps else None
                result_payload = {
                    "simulation_type": "qsts",
                    "summary": self._qsts_summary(result),
                }
            else:
                result_payload = {
                    "simulation_type": "snapshot",
                    "result": result.model_dump(),
                }
            await self.broadcast(session, "result", result_payload)
            session.status = SimulationStatus.COMPLETED
            await self.broadcast(session, "completed")

            if session.task_count >= RECYCLE_THRESHOLD:
                old_engine = session.engine
                await self._executor.close(old_engine)
                session.engine = await self._executor.create_engine(
                    resolve_topology(session.topology),
                    (
                        result.load_multiplier
                        if isinstance(result, SolveResponse)
                        else result.steps[-1].load_multiplier
                    ),
                )
                session.model_summary = self._executor.model_summary(
                    session.engine,
                    session.topology,
                )
                session.task_count = 0

        logger.info(
            "simulation_solved session_id=%s topology=%s elapsed_ms=%.3f converged=%s",
            session_id,
            session.topology,
            result.elapsed_ms,
            result.converged
            if isinstance(result, SolveResponse)
            else result.failed_steps == 0,
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
            simulation_type=session.simulation_type,
            last_error=session.last_error,
            current_step=session.current_step,
            total_steps=session.total_steps,
            progress_pct=session.progress_pct,
            simulated_hour=session.simulated_hour,
            last_qsts_step=session.last_qsts_step,
            worker_identity=session.engine.identity,
        )

    def _qsts_progress_callback(
        self, session: SimulationSession, loop: asyncio.AbstractEventLoop
    ):
        def callback(step: QSTSStepResult, current_step: int, total_steps: int) -> None:
            future = asyncio.run_coroutine_threadsafe(
                self._publish_qsts_progress(
                    session, step, current_step, total_steps
                ),
                loop,
            )
            future.result()

        return callback

    async def _publish_qsts_progress(
        self,
        session: SimulationSession,
        step: QSTSStepResult,
        current_step: int,
        total_steps: int,
    ) -> None:
        session.current_step = current_step
        session.total_steps = total_steps
        session.progress_pct = round(current_step * 100.0 / total_steps, 3)
        session.simulated_hour = step.simulated_hour
        session.last_qsts_step = step
        await self.broadcast(
            session,
            "qsts_progress",
            {
                "simulation_type": "qsts",
                "step": step.step,
                "total_steps": total_steps,
                "progress_pct": session.progress_pct,
                "simulated_minutes": step.simulated_minutes,
                "simulated_hour": step.simulated_hour,
                "converged": step.converged,
                "solve_ms": step.solve_ms,
                "load_multiplier": step.load_multiplier,
                "total_kw": step.total_kw,
                "total_kvar": step.total_kvar,
                "min_voltage_pu": step.min_voltage_pu,
                "max_voltage_pu": step.max_voltage_pu,
            },
        )

    @staticmethod
    def _qsts_summary(result: QSTSResult) -> dict:
        return {
            key: value
            for key, value in result.model_dump().items()
            if key not in {"config", "steps"}
        }

    def get_results(self, session_id: str) -> dict:
        session = self._get_session(session_id)
        if session.last_result is None:
            raise LookupError("La simulación todavía no tiene resultados")
        if isinstance(session.last_result, QSTSResult):
            return {
                "session_id": session.session_id,
                "simulation_type": "qsts",
                "config": session.last_result.config.model_dump(),
                "summary": {
                    key: value
                    for key, value in session.last_result.model_dump().items()
                    if key not in {"config", "steps"}
                },
                "steps": [
                    step.model_dump() for step in session.last_result.steps
                ],
            }
        return {
            "session_id": session.session_id,
            "simulation_type": "snapshot",
            "result": session.last_result.model_dump(),
        }

    async def close(self, session_id: str) -> None:
        session = self._get_session(session_id)
        async with session.lock:
            session.status = SimulationStatus.CLOSED
            await self._executor.close(session.engine)
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
                "simulation_type": session.simulation_type,
                "current_step": session.current_step,
                "total_steps": session.total_steps,
                "progress_pct": session.progress_pct,
                "simulated_hour": session.simulated_hour,
                "last_qsts_step": (
                    session.last_qsts_step.model_dump()
                    if session.last_qsts_step
                    else None
                ),
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
            "simulation_type": session.simulation_type,
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
        return self._executor.identity(session.engine)

    def get_load_multiplier(self, session_id: str) -> float:
        session = self._get_session(session_id)
        return self._executor.load_multiplier(session.engine)

    def metrics_snapshot(self) -> dict[str, int]:
        statuses = [session.status for session in self._sessions.values()]
        return {
            "active": len(statuses),
            "running": sum(status.value == "RUNNING" for status in statuses),
            "completed": sum(status.value == "COMPLETED" for status in statuses),
            "error": sum(status.value == "ERROR" for status in statuses),
        }
