from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

import httpx

from packages.contracts.errors import (
    InteractiveConflict, InteractiveContextLost, InteractiveExecutionError, OverloadedError,
    QuotaExceededError, SwitchNotFoundError, WorkerUnavailableError,
)
from packages.contracts.interactive import (
    InteractiveEvent, InteractivePhase, InteractiveStart, InteractiveState, InteractiveStepResponse,
    InteractiveStepResult, IntervalCommand, ModeCommand, NetworkBranch, RunReference, StepCommand,
    SwitchCommand, SwitchOperation, SwitchState, WorkerInitialize, WorkerInteractiveCommand,
    WorkerInteractiveReply, WorkerProbe, WorkerStep, WorkerStop, WorkerSwitch, WorkerSwitches,
)
from packages.contracts.models import SimulationStatus

if TYPE_CHECKING:
    from services.api_manager.orchestration.simulation_service import SimulationService, SimulationSession

logger = logging.getLogger(__name__)
WORKER_PROBE_SECONDS = 10.0
ACTIVE_PHASES = {"ready", "running", "paused"}


@dataclass
class InteractiveRun:
    request: InteractiveStart
    run_id: UUID = field(default_factory=uuid4)
    phase: InteractivePhase = "ready"
    total_steps: int = field(init=False)
    completed: int = 0
    deadline: float | None = None
    probe_at: float = 0
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    latest: InteractiveStepResult | None = None
    results_stale: bool = False
    message: str | None = None
    switches: list[SwitchState] = field(default_factory=list)
    branches: list[NetworkBranch] = field(default_factory=list)
    steps: list[InteractiveStepResult] = field(default_factory=list)
    step_commands: dict[UUID, tuple[str, int, InteractiveStepResult]] = field(default_factory=dict)
    switch_commands: dict[UUID, SwitchOperation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.total_steps = self.request.to_config().total_steps


class InteractiveService:
    def __init__(self, service: SimulationService) -> None:
        self._service = service
        self._stopping = False

    @staticmethod
    def state(session: SimulationSession) -> InteractiveState | None:
        run = session.interactive
        if run is None:
            return None
        next_step_at = None
        if run.deadline is not None:
            delay = max(0, run.deadline - asyncio.get_running_loop().time())
            next_step_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        return InteractiveState(
            run_id=run.run_id, revision=session.interactive_revision, phase=run.phase,
            execution_mode=run.request.execution_mode, interval_seconds=run.request.interval_seconds,
            duration_hours=run.request.duration_hours, step_minutes=run.request.step_minutes,
            profile_source=run.request.profile_source, completed_steps=run.completed,
            total_steps=run.total_steps,
            simulated_minutes=run.completed * run.request.step_minutes, next_step_at=next_step_at,
            latest_result=run.latest, in_flight=session.job_active, results_stale=run.results_stale, message=run.message,
        )

    def read(self, session_id: str, user: str, admin: bool) -> SimulationSession:
        self._service._authorize_session(session_id, user, admin, control=False)
        return self._service._get_session(session_id)

    @staticmethod
    def _run(session: SimulationSession, command: RunReference | None = None) -> InteractiveRun:
        run = session.interactive
        if run is None or (command is not None and command.run_id != run.run_id):
            raise InteractiveConflict("La ejecución solicitada ya no está activa en esta sesión.")
        return run

    @staticmethod
    def _active(run: InteractiveRun) -> None:
        if run.phase not in ACTIVE_PHASES:
            raise InteractiveConflict("La ejecución está finalizada. Inicie o reinicie un QSTS.")

    def _permission(self, session: SimulationSession, user: str, admin: bool, *, owner: bool) -> None:
        self._service._authorize_session(session.session_id, user, admin, control=owner, operate=not owner)
        if session.status == SimulationStatus.CLOSED or self._stopping:
            raise InteractiveConflict("La simulación está cerrada.")

    async def _publish(
        self, session: SimulationSession, event_type: Literal["interactive_state", "interactive_step", "switch_operation"],
        *, operation: SwitchOperation | None = None, include_switches: bool = False,
    ) -> InteractiveState:
        session.interactive_revision += 1
        state = self.state(session)
        run = self._run(session)
        assert state is not None
        session.status = {
            "running": SimulationStatus.RUNNING, "completed": SimulationStatus.COMPLETED,
            "failed": SimulationStatus.ERROR, "interrupted": SimulationStatus.ERROR,
        }.get(state.phase, SimulationStatus.READY)
        session.current_step = state.completed_steps
        session.total_steps = state.total_steps
        session.simulated_hour = state.simulated_minutes / 60
        session.progress_pct = state.completed_steps / state.total_steps * 100
        session.last_qsts_step = state.latest_result
        session.last_error = state.message if state.phase in {"failed", "interrupted"} else None
        event = InteractiveEvent(
            type=event_type, state=state, switches=run.switches if include_switches else None,
            operation=operation,
        )
        await self._service.broadcast(session, event.type, event.model_dump(mode="json", exclude={"type"}))
        return state

    async def _worker(
        self, session: SimulationSession, run: InteractiveRun, command: WorkerInteractiveCommand,
    ) -> WorkerInteractiveReply:
        try:
            response = await self._service._executor.interactive(session.session_id, command)
            if (
                isinstance(command, WorkerInitialize) and (response.branches is None or response.switches is None)
                or isinstance(command, WorkerStep) and (response.result is None or response.switches is None)
                or isinstance(command, WorkerSwitch) and response.switch is None
                or isinstance(command, WorkerSwitches) and response.switches is None
            ):
                raise InteractiveContextLost("La respuesta del worker no confirma el comando.")
        except SwitchNotFoundError:
            raise
        except (InteractiveContextLost, InteractiveConflict) as exc:
            if run.phase in {"completed", "stopped"}:
                raise InteractiveContextLost("El worker no pudo confirmar el estado eléctrico actual.") from exc
            run.phase = "interrupted"
            run.message = "Se perdió el contexto del worker. El último paso confirmado se conserva. Reinicie para comenzar otro QSTS."
            run.deadline = None
            run.wake.set()
            logger.warning("interactive_context_lost session_id=%s run_id=%s", session.session_id, run.run_id)
            await self._publish(session, "interactive_state")
            raise InteractiveContextLost(run.message) from exc
        except Exception as exc:
            run.phase = "failed"
            run.message = "OpenDSS no pudo completar la operación interactiva. Reinicie el QSTS."
            run.deadline = None
            run.wake.set()
            logger.exception("interactive_command_failed session_id=%s run_id=%s", session.session_id, run.run_id)
            await self._publish(session, "interactive_state")
            raise InteractiveExecutionError(run.message) from exc
        run.probe_at = asyncio.get_running_loop().time() + WORKER_PROBE_SECONDS
        return response

    async def _initialize(self, session: SimulationSession, request: InteractiveStart) -> InteractiveState:
        previous = session.interactive
        reset = previous is not None
        replace_context = previous is not None and previous.phase == "interrupted"
        if previous is not None:
            previous.wake.set()
            if not replace_context:
                try:
                    await self._service._executor.interactive(session.session_id, WorkerProbe(run_id=previous.run_id))
                except (InteractiveContextLost, InteractiveConflict):
                    replace_context = True
        run = InteractiveRun(
            request=request, phase="initializing",
        )
        session.interactive = run
        session.last_result = None
        session.simulation_type = None
        if replace_context:
            try:
                with suppress(KeyError, httpx.HTTPError, RuntimeError, TimeoutError):
                    await asyncio.wait_for(self._service._executor.close_session(session.session_id), timeout=15)
                executor = self._service._executor
                arguments = {
                    "session_id": session.session_id, "topology": session.topology,
                    "load_multiplier": session.initial_load_multiplier,
                }
                try:
                    info = await executor.prepare_session(**arguments)
                except WorkerUnavailableError:
                    probe = getattr(executor, "health_probe", None)
                    if probe is None:
                        raise
                    await probe()
                    info = await executor.prepare_session(**arguments)
                session.runtime_identity = info.runtime_identity
                session.model_summary = info.model_summary
                reset = False
            except Exception as exc:
                logger.warning("interactive_restart_unavailable session_id=%s", session.session_id, exc_info=True)
                run.phase = "interrupted"
                run.message = "No se pudo preparar un worker para reiniciar el QSTS."
                await self._publish(session, "interactive_state")
                raise InteractiveContextLost(run.message) from exc
        reply = await self._worker(session, run, WorkerInitialize(run_id=run.run_id, config=request.to_config(), reset=reset))
        run.branches = reply.branches or []
        run.switches = reply.switches or []
        run.phase = "paused" if request.execution_mode == "automatic" else "ready"
        self._ensure_loop(session, run)
        return await self._publish(session, "interactive_state", include_switches=True)

    async def start(self, session_id: str, request: InteractiveStart, user: str, admin: bool) -> InteractiveState:
        session = self.read(session_id, user, admin)
        async with session.lock:
            self._permission(session, user, admin, owner=True)
            if session.interactive is not None and session.interactive.phase in ACTIVE_PHASES:
                raise InteractiveConflict("Ya existe un QSTS activo. Deténgalo o reinícielo.")
            return await self._initialize(session, request)

    async def transition(
        self, session_id: str, command: RunReference, action: Literal["run", "pause", "resume", "interval", "mode", "stop", "restart"],
        user: str, admin: bool,
    ) -> InteractiveState:
        session = self.read(session_id, user, admin)
        async with session.lock:
            self._permission(session, user, admin, owner=action in {"mode", "interval", "stop", "restart"})
            run = self._run(session, command)
            if action == "restart":
                return await self._initialize(session, run.request)
            if action == "stop" and run.phase == "stopped":
                state = self.state(session)
                assert state is not None
                return state
            self._active(run)
            now = asyncio.get_running_loop().time()
            if action == "stop":
                await self._worker(session, run, WorkerStop(run_id=run.run_id))
                run.phase = "stopped"
                run.deadline = None
            elif action == "pause":
                run.phase = "paused"
                run.deadline = None
            elif action == "run":
                if run.request.execution_mode != "automatic":
                    self._permission(session, user, admin, owner=True)
                    run.request = run.request.model_copy(update={"execution_mode": "automatic"})
                if run.phase != "running":
                    run.phase = "running"
                    run.deadline = now
            elif action == "resume":
                if run.phase != "running":
                    run.phase = "running" if run.request.execution_mode == "automatic" else "ready"
                    run.deadline = now if run.phase == "running" else None
            elif action == "interval":
                assert isinstance(command, IntervalCommand)
                run.request = run.request.model_copy(update={"interval_seconds": command.interval_seconds})
                if run.phase == "running":
                    run.deadline = now + command.interval_seconds
            elif action == "mode":
                assert isinstance(command, ModeCommand)
                run.request = run.request.model_copy(update={"execution_mode": command.execution_mode})
                if command.execution_mode == "manual" and run.phase == "running":
                    run.phase = "ready"
                    run.deadline = None
            run.message = None
            run.wake.set()
            return await self._publish(session, "interactive_state")

    async def _advance(self, session: SimulationSession, run: InteractiveRun) -> InteractiveStepResponse:
        await self._service._admit_job(session)
        try:
            reply = await self._worker(session, run, WorkerStep(run_id=run.run_id, expected_step=run.completed))
            result = reply.result
            if result is None or result.step != run.completed + 1:
                run.phase = "interrupted"
                run.deadline = None
                run.message = "El worker no confirmó el avance esperado. Reinicie el QSTS."
                run.wake.set()
                await self._publish(session, "interactive_state")
                raise InteractiveContextLost(run.message)
            run.completed = result.step
            run.latest = result
            run.steps.append(result)
            run.switches = reply.switches or []
            run.results_stale = False
            run.message = None
            if run.completed == run.total_steps:
                run.phase = "completed"
                run.deadline = None
            elif run.phase == "running":
                run.deadline = asyncio.get_running_loop().time() + run.request.interval_seconds
            run.wake.set()
            session.job_active = False
            state = await self._publish(session, "interactive_step", include_switches=True)
            return InteractiveStepResponse(state=state, result=result)
        finally:
            session.job_active = False

    async def step(self, session_id: str, command: StepCommand, user: str, admin: bool) -> InteractiveStepResponse:
        session = self.read(session_id, user, admin)
        async with session.lock:
            self._permission(session, user, admin, owner=False)
            run = self._run(session, command)
            previous = run.step_commands.get(command.command_id)
            if previous is not None:
                if previous[:2] != (user, command.expected_step):
                    raise InteractiveConflict("El identificador de comando ya tiene otro paso o actor.")
                state = self.state(session)
                assert state is not None
                return InteractiveStepResponse(state=state, result=previous[2])
            self._active(run)
            if command.expected_step != run.completed:
                raise InteractiveConflict("El paso cambió. Actualice el estado antes de continuar.")
            response = await self._advance(session, run)
            run.step_commands[command.command_id] = (user, command.expected_step, response.result)
            return response

    async def switches(self, session_id: str, user: str, admin: bool) -> list[SwitchState]:
        session = self.read(session_id, user, admin)
        async with session.lock:
            self.read(session_id, user, admin)
            run = session.interactive
            if run is None:
                return []
            if run.phase == "interrupted":
                raise InteractiveContextLost("El estado actual del interruptor no está disponible tras perder el worker.")
            if run.phase == "failed":
                raise InteractiveConflict("El estado actual del interruptor requiere reiniciar el QSTS.")
            reply = await self._worker(session, run, WorkerSwitches(run_id=run.run_id))
            run.switches = reply.switches or []
            return run.switches

    async def operate(
        self, session_id: str, element: str, command: SwitchCommand, user: str, admin: bool,
    ) -> SwitchOperation:
        session = self.read(session_id, user, admin)
        async with session.lock:
            self._permission(session, user, admin, owner=False)
            run = self._run(session, command)
            previous = run.switch_commands.get(command.command_id)
            if previous is not None:
                if (previous.actor, previous.element.casefold(), previous.action, previous.step) != (
                    user, element.casefold(), command.action, command.expected_step,
                ):
                    raise InteractiveConflict("El identificador ya corresponde a otra operación.")
                return previous
            self._active(run)
            if command.expected_step != run.completed:
                raise InteractiveConflict("El paso cambió antes de operar el interruptor.")
            if len(run.switch_commands) >= 10_000:
                raise InteractiveConflict("Se alcanzó el límite de operaciones de este QSTS.")
            reply = await self._worker(session, run, WorkerSwitch(
                run_id=run.run_id, expected_step=run.completed, element=element, action=command.action,
            ))
            current = reply.switch
            assert current is not None
            operation = SwitchOperation(
                run_id=run.run_id, command_id=command.command_id, actor=user, element=current.element,
                action=command.action, step=run.completed, simulated_minutes=run.completed * run.request.step_minutes,
                timestamp=datetime.now(timezone.utc), effective_state=current,
            )
            run.switch_commands[command.command_id] = operation
            session.switch_history.append(operation)
            run.switches = [current if switch.element == current.element else switch for switch in run.switches]
            run.results_stale = run.latest is not None
            logger.info("switch_operation session_id=%s operation=%s", session_id, operation.model_dump_json())
            await self._publish(session, "switch_operation", operation=operation, include_switches=True)
            return operation

    def _ensure_loop(self, session: SimulationSession, run: InteractiveRun) -> None:
        run.task = asyncio.create_task(self._loop(session, run), name=f"interactive-{run.run_id}")

    async def _loop(self, session: SimulationSession, run: InteractiveRun) -> None:
        clock = asyncio.get_running_loop()
        while not self._stopping:
            async with session.lock:
                if self._stopping or session.interactive is not run or run.phase not in ACTIVE_PHASES:
                    return
                now = clock.time()
                deadline = run.deadline
                try:
                    if deadline is not None and deadline <= now:
                        try:
                            await self._advance(session, run)
                        except (QuotaExceededError, OverloadedError):
                            run.deadline = clock.time() + run.request.interval_seconds
                            if run.message is None:
                                run.message = "Esperando capacidad para el siguiente paso."
                                await self._publish(session, "interactive_state")
                        continue
                    if run.probe_at <= now:
                        await self._worker(session, run, WorkerProbe(run_id=run.run_id))
                        continue
                except (InteractiveContextLost, InteractiveExecutionError):
                    return
                next_wake = min(deadline, run.probe_at) if deadline is not None else run.probe_at
                run.wake.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(run.wake.wait(), timeout=max(0, next_wake - clock.time()))

    async def shutdown(self) -> None:
        self._stopping = True
        tasks = []
        sessions = [session for session in self._service._sessions.values() if session.interactive]
        for session in sessions:
            run = self._run(session)
            if run.task is not None:
                run.wake.set()
                tasks.append(run.task)
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*(
            asyncio.wait_for(self._service.close(session.session_id), timeout=15) for session in sessions
        ), return_exceptions=True)
        self._stopping = False
