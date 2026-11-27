from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect
from httpx import HTTPError
from uuid import uuid4
from packages.common.custom_model_paths import CUSTOM_TOPOLOGY, STAGED_CUSTOM_TOPOLOGY, split_custom_topology
from packages.contracts.errors import (
    AccessDeniedError,
    InteractiveConflict,
    OverloadedError,
    QuotaExceededError,
    SimulationClosedError,
    SimulationNotFoundError,
)
from packages.contracts.interactive import Participant, ParticipantRole, SwitchOperation
from packages.contracts.models  import (
    CreateSimulationRequest,
    CreateSimulationResponse,
    ModelSummary,
    SimulationDetail,
    SimulationStatus,
    SimulationSummary,
    QSTSResult,
    QSTSStepResult,
    SolveRequest,
    SolveResponse,
)
from packages.contracts.jobs import (
    SimulationJob,
)
from packages.contracts.progress import (
    SimulationProgress,
)
from packages.contracts.execution import (
    SimulationExecutor,
)
from services.api_manager.platform.settings  import get_settings
from services.api_manager.platform.metrics  import metrics
from services.api_manager.orchestration.custom_models import custom_model_manager
from services.api_manager.orchestration.interactive_service import InteractiveRun, InteractiveService

logger = logging.getLogger(__name__)


def _normalize_topology(topology: str, *, is_admin: bool) -> str:
    value = topology.strip()
    namespace = value.partition(":")[0].lower()
    if namespace == STAGED_CUSTOM_TOPOLOGY or (namespace == CUSTOM_TOPOLOGY and not is_admin):
        raise AccessDeniedError("El usuario no tiene acceso a este modelo personalizado.")
    if namespace == CUSTOM_TOPOLOGY:
        return custom_model_manager.topology(*split_custom_topology(value))
    return value.lower()


@dataclass
class SimulationSession:
    session_id: str
    topology: str
    created_at: datetime
    lock: asyncio.Lock
    model_summary: ModelSummary
    owner_id: str
    viewer_ids: set[str] = field(default_factory=set)
    operator_ids: set[str] = field(default_factory=set)
    invited_viewer_ids: set[str] = field(default_factory=set)
    runtime_identity: int | str | None = None
    load_multiplier: float = 1.0
    initial_load_multiplier: float = 1.0
    job_active: bool = False
    status: SimulationStatus = SimulationStatus.CREATED
    current_job_id: str | None = None
    task_count: int = 0
    last_result: SolveResponse | QSTSResult | None = None
    simulation_type: str | None = None
    last_error: str | None = None
    current_step: int | None = None
    total_steps: int | None = None
    progress_pct: float | None = None
    simulated_hour: float | None = None
    last_qsts_step: QSTSStepResult | None = None
    subscribers: dict[WebSocket, tuple[str | None, bool]] = field(default_factory=dict)
    subscriber_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    interactive: InteractiveRun | None = None
    interactive_revision: int = 0
    switch_history: deque[SwitchOperation] = field(default_factory=lambda: deque(maxlen=3000))
    access_request_ids: set[str] = field(
    default_factory=set
    )

class SimulationService:
    def __init__(
        self,
        executor: SimulationExecutor,
    ) -> None:
        self._sessions: dict[str, SimulationSession] = {}
        self._registry_lock = asyncio.Lock()
        self._admission_lock = asyncio.Lock()
        self._executor = executor
        self.interactive = InteractiveService(self)

    async def create(
        self, request: CreateSimulationRequest, *, owner_id: str, is_admin: bool = False,
    ) -> CreateSimulationResponse:
        started_at = time.perf_counter()
        topology = _normalize_topology(request.topology, is_admin=is_admin)
        async with self._registry_lock:
            if len(self._sessions) >= get_settings().max_active_simulations:
                raise RuntimeError("Se alcanzó MAX_ACTIVE_SIMULATIONS")

        session_id = str(uuid4())
        created_at = datetime.now(timezone.utc)
        execution_info = await self._executor.prepare_session(
            session_id=session_id,
            topology=topology,
            load_multiplier=request.load_multiplier,
        )
        session = SimulationSession(
            session_id=session_id,
            topology=topology,
            status=SimulationStatus.READY,
            model_summary=execution_info.model_summary,
            task_count=execution_info.task_count,
            lock=asyncio.Lock(),
            created_at=created_at,
            runtime_identity=execution_info.runtime_identity,
            load_multiplier=execution_info.load_multiplier,
            initial_load_multiplier=request.load_multiplier,
            owner_id=owner_id
        )

        async with self._registry_lock:
            self._sessions[session_id] = session

        logger.info(
            "simulation_created session_id=%s topology=%s context_id=%s load_multiplier=%s",
            session_id,
            session.topology,
            execution_info.runtime_identity,
            execution_info.load_multiplier,
        )
        metrics.observe(
            "session_create_ms",
            (time.perf_counter() - started_at) * 1000.0,
        )

        return CreateSimulationResponse(
            session_id=session_id,
            topology=session.topology,
            load_multiplier=execution_info.load_multiplier,
            created_at=created_at,
        )

    async def solve(
        self,
        session_id: str,
        request: SolveRequest | None = None,
        *,
        user_id: str | None = None,
        is_admin: bool = True,
    ) -> SolveResponse | QSTSResult:
        session = self._get_session(session_id)
        async with session.lock:
            self._authorize_session(session_id, user_id, is_admin, control=True)
            if session.status == SimulationStatus.CLOSED:
                raise SimulationClosedError(f"La simulación {session_id} está cerrada")
            run = session.interactive
            if run is not None and run.phase not in {"stopped", "completed"}:
                raise InteractiveConflict("Detenga el QSTS interactivo antes de ejecutar Snapshot o QSTS batch.")
            await self._admit_job(session)
            try:
                if run is not None:
                    run.wake.set()
                    session.interactive = None
                session.status = SimulationStatus.RUNNING
                return await self._solve_locked(session, request)
            except Exception:
                if session.status == SimulationStatus.RUNNING:
                    session.status = SimulationStatus.ERROR
                raise
            finally:
                session.job_active = False

    async def _admit_job(self, session: SimulationSession) -> None:
        async with self._admission_lock:
            settings = get_settings()
            if settings.admission_control_enabled:
                running = [item for item in self._sessions.values() if item.job_active]
                if sum(item.owner_id == session.owner_id for item in running) >= settings.max_concurrent_simulations_per_user:
                    raise QuotaExceededError("Se alcanzó la cuota de simulaciones concurrentes")
                if len(running) >= settings.max_concurrent_jobs:
                    raise OverloadedError("Se alcanzó la capacidad global de jobs")
            session.job_active = True

    async def _solve_locked(
        self, session: SimulationSession, request: SolveRequest | None,
    ) -> SolveResponse | QSTSResult:
        session_id = session.session_id
        session.last_error = None
        request = request or SolveRequest()
        session.simulation_type = request.simulation_type
        session.current_step = None
        session.total_steps = None
        session.progress_pct = None
        session.simulated_hour = None
        execution_info = (
            await self._executor.session_info(
                session.session_id
            )
        )
        effective_load_multiplier = (
            request.load_multiplier
            if request.load_multiplier is not None
            else execution_info.load_multiplier
        )
        session.load_multiplier = effective_load_multiplier
        session.last_qsts_step = None

        job_id = str(uuid4())
        session.current_job_id = job_id

        qsts_config = (
            request.qsts.to_config()
            if request.simulation_type == "qsts"
            and request.qsts is not None
            else None
        )
        job = SimulationJob(
            job_id=job_id,
            session_id=session.session_id,
            topology=session.topology,
            simulation_type=(
                request.simulation_type
            ),
            load_multiplier=(
                effective_load_multiplier
            ),
            qsts=qsts_config,
            user_id = session.owner_id
        )
        if request.simulation_type == "qsts" and request.qsts is not None:
            session.total_steps = request.qsts.to_config().total_steps
        await self.broadcast(session, "simulation_started")
        await self.broadcast(
            session, "model_loaded", {"model": session.model_summary.model_dump()}
        )
        await self.broadcast(session, "solving")
        try:
            if job.simulation_type == "qsts":

                async def progress_handler(
                    progress: SimulationProgress,
                ) -> None:
                    await self._handle_executor_progress(
                        session,
                        progress,
                    )

                execution_result = await self._executor.submit(
                    job,
                    progress_handler=progress_handler,
                )
                if execution_result.qsts is None:
                    raise RuntimeError(
                        "QSTS execution returned "
                        "no QSTS result"
                        )
                result = execution_result.qsts
            elif job.simulation_type == "snapshot":
                execution_result = await self._executor.submit(job)
                if execution_result.snapshot is None:
                    raise RuntimeError(
                        "Snapshot execution returned no snapshot result"
                    )
                result = execution_result.snapshot
            else:
                raise ValueError(
                    f"Unsupported simulation type: {job.simulation_type}"
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

        execution_info = await self._executor.session_info(session.session_id)
        session.task_count = execution_info.task_count
        session.model_summary = execution_info.model_summary
        session.runtime_identity = execution_info.runtime_identity
        session.load_multiplier = execution_info.load_multiplier
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

    async def list_sessions(
        self,
        user_id: str,
        is_admin: bool,
    ) -> list[SimulationSummary]:

        result: list[
            SimulationSummary
        ] = []

        for session in self._sessions.values():

            access_mode = self._access_mode(
                session,
                user_id,
                is_admin,
            )
            topology = session.topology

            if access_mode is None:
                if topology.startswith("custom:"):
                    topology = "custom"
                if (
                    user_id
                    in session.access_request_ids
                ):
                    access_mode = "requested"
                else:
                    access_mode = "requestable"

            result.append(
                SimulationSummary(
                    session_id=session.session_id,
                    topology=topology,
                    status=session.status,
                    created_at=session.created_at,
                    task_count=session.task_count,
                    access_mode=access_mode,
                    owner_id=session.owner_id,
                    invited=user_id in session.invited_viewer_ids,
                )
            )

        return result


    def get_detail(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
        is_admin: bool = True,
    ) -> SimulationDetail:
        session = self._get_session(session_id)
        self._authorize_session(session_id, user_id, is_admin, control=False)
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
            worker_identity=session.runtime_identity,
            access_mode=self._access_mode(session, user_id, is_admin) or "owner",
            owner_id=session.owner_id,
            invited=user_id in session.invited_viewer_ids,
        )

    

    @staticmethod
    def _qsts_summary(result: QSTSResult) -> dict:
        return {
            key: value
            for key, value in result.model_dump().items()
            if key not in {"config", "steps"}
        }

    def get_results(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
        is_admin: bool = True,
    ) -> dict:
        session = self._get_session(session_id)
        self._authorize_session(session_id, user_id, is_admin, control=False)
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

    async def close(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
        is_admin: bool = True,
    ) -> None:
        session = self._get_session(session_id)
        self._authorize_session(session_id, user_id, is_admin, control=True)
     
        async with session.lock:
            run = session.interactive
            if run is not None:
                run.phase = "stopped"
                run.deadline = None
                run.wake.set()
            session.status = (
                SimulationStatus.CLOSED
            )

            if run is None:
                await self._executor.close_session(session.session_id)
            else:
                try:
                    await asyncio.wait_for(self._executor.close_session(session.session_id), timeout=15)
                except (KeyError, HTTPError, RuntimeError, TimeoutError):
                    logger.warning("interactive_close_unconfirmed session_id=%s", session_id, exc_info=True)

            await self.broadcast(
                session,
                "completed",
                {
                    "status":
                        SimulationStatus.CLOSED.value
                },
            )

            async with self._registry_lock:
                self._sessions.pop(
                    session_id,
                    None,
                )

        async with session.subscriber_lock:
            sockets = tuple(session.subscribers)
            session.subscribers.clear()
            for websocket in sockets:
                with suppress(RuntimeError, WebSocketDisconnect):
                    await websocket.close()

    async def subscribe(
        self,
        session_id: str,
        websocket: WebSocket,
        *,
        user_id: str | None = None,
        is_admin: bool = True,
        subprotocol: str | None = None,
    ) -> None:
        session = self._get_session(session_id)
        async with session.subscriber_lock:
            self._authorize_session(session_id, user_id, is_admin, control=False)
            await websocket.accept(subprotocol=subprotocol)
            session.subscribers[websocket] = (user_id, is_admin)
            interactive = self.interactive.state(session)
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
                        session.last_qsts_step.model_dump() if session.last_qsts_step else None
                    ),
                    "simulation": SimulationSummary(
                        session_id=session.session_id,
                        topology=session.topology,
                        status=session.status,
                        created_at=session.created_at,
                        task_count=session.task_count,
                        access_mode=self._access_mode(session, user_id, is_admin) or "viewer",
                        invited=user_id in session.invited_viewer_ids,
                    ).model_dump(mode="json"),
                    "model": session.model_summary.model_dump(),
                    "last_result": session.last_result.model_dump() if session.last_result else None,
                    **({
                        "interactive": interactive.model_dump(mode="json"),
                        "switches": [switch.model_dump(mode="json") for switch in session.interactive.switches],
                    } if interactive is not None and session.interactive is not None else {}),
                }
            )

    def unsubscribe(self, session_id: str, websocket: WebSocket) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.subscribers.pop(websocket, None)

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
        async with session.subscriber_lock:
            for websocket in tuple(session.subscribers):
                try:
                    await websocket.send_json(message)
                except (RuntimeError, WebSocketDisconnect):
                    session.subscribers.pop(websocket, None)

    def _get_session(self, session_id: str) -> SimulationSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SimulationNotFoundError(
                f"No existe una simulación con session_id={session_id}"
            )
        return session

    def _access_mode(
        self,
        session: SimulationSession,
        user_id: str | None,
        is_admin: bool,
    ) -> str | None:
        if is_admin:
            return "admin"
        if user_id == session.owner_id:
            return "owner"
        if user_id in session.operator_ids:
            return "operator"
        if user_id in session.viewer_ids:
            return "viewer"
        return None

    def _authorize_session(
        self,
        session_id: str,
        user_id: str | None,
        is_admin: bool,
        *,
        control: bool,
        operate: bool = False,
    ) -> None:
        session = self._get_session(session_id)
        mode = self._access_mode(session, user_id, is_admin)
        if (
            mode is None
            or (control and mode not in {"owner", "admin"})
            or (operate and mode == "viewer")
        ):
            raise AccessDeniedError(
                f"El usuario no tiene acceso a la simulación {session_id}"
            )
    def request_access(
        self,
        session_id: str,
        *,
        user_id: str,
    ) -> None:

        session = self._get_session(
            session_id
        )

        if session.owner_id == user_id:
            raise ValueError(
                "El propietario ya tiene acceso"
            )

        if user_id in session.viewer_ids or user_id in session.operator_ids:
            raise ValueError(
                "El usuario ya tiene acceso"
            )

        session.access_request_ids.add(
            user_id
        )

    def list_access_requests(
        self,
        session_id: str,
        *,
        user_id: str,
        is_admin: bool,
    ) -> list[str]:

        session = self._get_session(
            session_id
        )

        if (
            not is_admin
            and session.owner_id
            != user_id
        ):
            raise AccessDeniedError(
                "Solo el propietario puede "
                "gestionar solicitudes"
            )

        return sorted(
            session.access_request_ids
        )

    def approve_access_request(
        self,
        session_id: str,
        username: str,
        *,
        user_id: str,
        is_admin: bool,
    ) -> list[str]:

        session = self._get_session(
            session_id
        )

        if (
            not is_admin
            and session.owner_id
            != user_id
        ):
            raise AccessDeniedError(
                "Solo el propietario puede "
                "aprobar solicitudes"
            )

        if (
            username
            not in session.access_request_ids
        ):
            raise ValueError(
                "No existe solicitud pendiente"
            )

        session.access_request_ids.discard(
            username
        )

        session.viewer_ids.add(
            username
        )

        return sorted(
            session.viewer_ids
        )

    def reject_access_request(
        self,
        session_id: str,
        username: str,
        *,
        user_id: str,
        is_admin: bool,
    ) -> None:

        session = self._get_session(
            session_id
        )

        if (
            not is_admin
            and session.owner_id
            != user_id
        ):
            raise AccessDeniedError(
                "Solo el propietario puede "
                "rechazar solicitudes"
            )

        session.access_request_ids.discard(
            username
        )

    def list_viewers(
        self,
        session_id: str,
        *,
        user_id: str,
        is_admin: bool,
        invited_only: bool = False,
    ) -> list[str]:
        session = self._get_session(session_id)
        if not is_admin and session.owner_id != user_id:
            raise AccessDeniedError("Solo el propietario puede gestionar viewers")
        viewers = session.viewer_ids
        return sorted(viewers & session.invited_viewer_ids if invited_only else viewers)

    def add_viewer(
        self,
        session_id: str,
        username: str,
        *,
        user_id: str,
        is_admin: bool,
    ) -> list[str]:
        session = self._get_session(session_id)
        if not is_admin and session.owner_id != user_id:
            raise AccessDeniedError("Solo el propietario puede gestionar viewers")
        if username == session.owner_id:
            raise ValueError("El propietario no puede agregarse como viewer")
        if username not in session.viewer_ids and username not in session.operator_ids:
            session.viewer_ids.add(username)
            session.invited_viewer_ids.add(username)
        session.access_request_ids.discard(username)
        return sorted(session.viewer_ids)

    async def remove_viewer(
        self,
        session_id: str,
        username: str,
        *,
        user_id: str,
        is_admin: bool,
    ) -> list[str]:
        session = self._get_session(session_id)
        await self.remove_participant(session_id, username, user_id=user_id, is_admin=is_admin)
        return sorted(session.viewer_ids)

    def list_participants(self, session_id: str, user_id: str, is_admin: bool) -> list[Participant]:
        self._authorize_session(session_id, user_id, is_admin, control=True)
        session = self._get_session(session_id)
        return [
            Participant(
                username=name, role="operator" if name in session.operator_ids else "viewer",
                invited=name in session.invited_viewer_ids,
            )
            for name in sorted(session.viewer_ids | session.operator_ids)
        ]

    async def set_participant(
        self, session_id: str, username: str, role: ParticipantRole, *, user_id: str, is_admin: bool,
    ) -> Participant:
        session = self._get_session(session_id)
        async with session.lock:
            self._authorize_session(session_id, user_id, is_admin, control=True)
            if username == session.owner_id:
                raise InteractiveConflict("El rol del propietario no se modifica.")
            if username not in session.viewer_ids and username not in session.operator_ids:
                session.invited_viewer_ids.add(username)
            session.viewer_ids.discard(username)
            session.operator_ids.discard(username)
            participants = session.operator_ids if role == "operator" else session.viewer_ids
            participants.add(username)
            session.access_request_ids.discard(username)
            invited = username in session.invited_viewer_ids
            async with session.subscriber_lock:
                for websocket, (subscriber, administrator) in tuple(session.subscribers.items()):
                    if subscriber == username:
                        try:
                            await websocket.send_json({
                                "type": "participant_role", "session_id": session_id,
                                "access_mode": self._access_mode(session, subscriber, administrator),
                                "invited": invited,
                            })
                        except (RuntimeError, WebSocketDisconnect):
                            session.subscribers.pop(websocket, None)
            await self.broadcast(session, "participants_changed")
            return Participant(username=username, role=role, invited=invited)

    async def remove_participant(
        self, session_id: str, username: str, *, user_id: str, is_admin: bool,
    ) -> None:
        session = self._get_session(session_id)
        async with session.lock, session.subscriber_lock:
            self._authorize_session(session_id, user_id, is_admin, control=True)
            if username == session.owner_id:
                return
            session.viewer_ids.discard(username)
            session.operator_ids.discard(username)
            session.invited_viewer_ids.discard(username)
            for websocket, (subscriber_id, subscriber_is_admin) in tuple(session.subscribers.items()):
                if subscriber_id == username and not subscriber_is_admin:
                    session.subscribers.pop(websocket, None)
                    with suppress(RuntimeError, WebSocketDisconnect):
                        await websocket.close(code=1008)
        await self.broadcast(session, "participants_changed")

    async def session_engine_identity(
        self,
        session_id: str,
    ) -> int | str | None:
        return self._get_session(session_id).runtime_identity

    async def session_load_multiplier(
        self,
        session_id: str,
    ) -> float:
        return self._get_session(session_id).load_multiplier

    def get_engine_identity(self, session_id: str) -> int | str | None:
        return self._get_session(session_id).runtime_identity

    def get_load_multiplier(self, session_id: str) -> float:
        return self._get_session(session_id).load_multiplier

    def metrics_snapshot(self) -> dict[str, object]:
        statuses = [session.status for session in self._sessions.values()]
        result: dict[str, object] = {
            "active": len(statuses),
            "running": sum(status.value == "RUNNING" for status in statuses),
            "completed": sum(status.value == "COMPLETED" for status in statuses),
            "error": sum(status.value == "ERROR" for status in statuses),
        }
        pool_metrics = getattr(self._executor, "metrics_snapshot", None)
        if pool_metrics is not None:
            result.update(pool_metrics())
        return result
    async def _handle_executor_progress(
        self,
        session: SimulationSession,
        progress: SimulationProgress,
    ) -> None:
        session.current_step = (
            progress.step or 0
        )

        session.total_steps = (
            progress.total_steps or 0
        )

        session.progress_pct = (
            progress.progress_pct
        )

        session.simulated_hour = (
            progress.simulated_hour
        )

        required = (
            progress.step,
            progress.simulated_minutes,
            progress.simulated_hour,
            progress.converged,
            progress.solve_ms,
            progress.load_multiplier,
        )
        if any(value is None for value in required):
            raise RuntimeError("QSTS progress is missing required fields")

        session.last_qsts_step = QSTSStepResult(
            step=progress.step,
            simulated_minutes=progress.simulated_minutes,
            simulated_hour=progress.simulated_hour,
            opendss_hour=progress.opendss_hour,
            opendss_time_of_step_us=(
                progress.opendss_time_of_step_us
            ),
            converged=progress.converged,
            solve_ms=progress.solve_ms,
            load_multiplier=progress.load_multiplier,
            total_kw=progress.total_kw,
            total_kvar=progress.total_kvar,
            min_voltage_pu=progress.min_voltage_pu,
            max_voltage_pu=progress.max_voltage_pu,
            solution_iterations=(
                progress.solution_iterations
            ),
            rss_mb=progress.rss_mb,
        )

        await self.broadcast(
            session,
            "qsts_progress",
            {
                "step": progress.step,
                "total_steps": progress.total_steps,
                "progress_pct": progress.progress_pct,
                "simulated_minutes": progress.simulated_minutes,
                "simulated_hour": progress.simulated_hour,
                "converged": progress.converged,
                "solve_ms": progress.solve_ms,
                "load_multiplier": progress.load_multiplier,
                "total_kw": progress.total_kw,
                "total_kvar": progress.total_kvar,
                "min_voltage_pu": progress.min_voltage_pu,
                "max_voltage_pu": progress.max_voltage_pu,
                "opendss_hour": progress.opendss_hour,
                "opendss_time_of_step_us": (
                    progress.opendss_time_of_step_us
                ),
                "solution_iterations": progress.solution_iterations,
                "rss_mb": progress.rss_mb,
            },
        )
