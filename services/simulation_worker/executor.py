from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID
from packages.common.custom_model_paths import CustomModelError
from packages.contracts.errors import InteractiveConflict, InteractiveContextLost, SwitchNotFoundError
from packages.contracts.interactive import (
    WorkerInitialize, WorkerInteractiveCommand, WorkerInteractiveReply, WorkerProbe, WorkerStep,
    WorkerStop, WorkerSwitch, WorkerSwitches,
)
from packages.contracts.models import ModelSummary
from packages.contracts.jobs import JobStatus, SimulationJob
from packages.contracts.progress import SimulationProgress
from packages.contracts.results import SimulationResult
from packages.simulation_core.engine import OpenDSSContextEngine, QSTSSequence
from packages.simulation_core.custom_dss import custom_model_commands
from packages.contracts.execution  import (
    ExecutorSessionInfo,
    ProgressHandler,
)

from services.simulation_worker.topology_resolver import (
    resolve_worker_topology,
)
from services.simulation_worker.settings import worker_settings
class LocalJobCancelled(Exception):
    """Internal cooperative cancellation signal."""


@dataclass
class WorkerRun:
    run_id: UUID
    sequence: QSTSSequence
    catalog: dict[str, str]
    active: bool = True


@dataclass
class LocalExecutionSession:
    session_id: str
    topology: str
    topology_path: Path
    engine: OpenDSSContextEngine
    model_summary: ModelSummary
    task_count: int = 0
    model_commands: list[str] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    interactive_run: WorkerRun | None = None
    initial_load_multiplier: float = 1.0


class LocalSimulationExecutor:
    """
    Local implementation of SimulationExecutor.

    OpenDSS runs in threads, but the API Manager only communicates
    through provider-independent SimulationJob / Progress / Result
    contracts.

    The executor owns all OpenDSSContextEngine instances.
    """

    def __init__(
        self,
        *,
        recycle_threshold: int = 162,
    ) -> None:
        self._recycle_threshold = recycle_threshold

        self._sessions: dict[
            str,
            LocalExecutionSession,
        ] = {}

        self._job_status: dict[
            str,
            JobStatus,
        ] = {}

        self._cancel_events: dict[
            str,
            threading.Event,
        ] = {}

        self._registry_lock = asyncio.Lock()

    async def prepare_session(
        self,
        *,
        session_id: str,
        topology: str,
        load_multiplier: float,
    ) -> ExecutorSessionInfo:
        topology_path, workspace = resolve_worker_topology(topology)
        model_commands = None
        if workspace is not None:
            model_commands = await asyncio.to_thread(custom_model_commands, workspace, topology_path)
        engine = None
        try:
            engine = await asyncio.to_thread(
                OpenDSSContextEngine,
                topology_path,
                load_multiplier,
                model_commands=model_commands,
            )

            model_summary = await asyncio.to_thread(
                engine.model_summary,
                topology,
            )
            if model_commands is not None and not model_summary.num_buses:
                raise CustomModelError("El master no inicializa un circuito con buses.")
        except Exception as exc:
            if engine is not None:
                try:
                    await asyncio.to_thread(
                        engine.close
                    )
                except Exception:
                    pass
            if isinstance(exc, CustomModelError):
                raise
            if workspace is not None:
                error_code = f" (código {exc.args[0]})" if exc.args and type(exc.args[0]) is int else ""
                master = topology_path.relative_to(workspace).as_posix()
                raise CustomModelError(
                    f"OpenDSS no pudo cargar {master}{error_code}. Revise que el master inicialice un circuito válido."
                ) from exc
            raise ValueError(
                "No se pudo cargar el modelo "
                f"'{topology}' "
                f"({topology_path.name}): "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        
        runtime = LocalExecutionSession(
            session_id=session_id,
            topology=topology,
            topology_path=topology_path,
            engine=engine,
            model_summary=model_summary,
            model_commands=model_commands,
            initial_load_multiplier=load_multiplier,
        )

        async with self._registry_lock:
            if session_id in self._sessions:
                await asyncio.to_thread(engine.close)
                raise ValueError(
                    f"Session already exists: {session_id}"
                )

            self._sessions[session_id] = runtime

        return self._session_info(runtime)

    async def submit(
        self,
        job: SimulationJob,
        progress_handler: ProgressHandler | None = None,
    ) -> SimulationResult:
        runtime = self._require_session(job.session_id)
        async with runtime.lock:
            if self._sessions.get(job.session_id) is not runtime:
                raise KeyError("La sesión de ejecución fue cerrada.")
            if runtime.interactive_run and runtime.interactive_run.active:
                raise InteractiveConflict("El contexto está reservado por un QSTS interactivo.")
            runtime.interactive_run = None
            return await self._submit_job(runtime, job, progress_handler)

    async def _submit_job(
        self, runtime: LocalExecutionSession, job: SimulationJob, progress_handler: ProgressHandler | None,
    ) -> SimulationResult:
        if runtime.topology.lower() != job.topology.lower():
            raise ValueError(
                "Job topology does not match prepared session"
            )

        cancel_event = threading.Event()

        self._cancel_events[job.job_id] = cancel_event
        self._job_status[job.job_id] = JobStatus.RUNNING

        try:
            if job.simulation_type == "snapshot":
                result = await self._submit_snapshot(
                    runtime,
                    job,
                    cancel_event,
                )

            elif job.simulation_type == "qsts":
                result = await self._submit_qsts(
                    runtime,
                    job,
                    cancel_event,
                    progress_handler,
                )

            else:
                raise ValueError(
                    f"Unsupported simulation type: "
                    f"{job.simulation_type}"
                )

            if cancel_event.is_set():
                self._job_status[
                    job.job_id
                ] = JobStatus.CANCELLED

                return SimulationResult(
                    job_id=job.job_id,
                    session_id=job.session_id,
                    topology=job.topology,
                    simulation_type=job.simulation_type,
                    status=JobStatus.CANCELLED,
                )

            self._job_status[
                job.job_id
            ] = JobStatus.COMPLETED

            runtime.task_count += 1

            await self._recycle_if_needed(
                runtime,
                result,
            )

            return result

        except LocalJobCancelled:
            self._job_status[
                job.job_id
            ] = JobStatus.CANCELLED

            return SimulationResult(
                job_id=job.job_id,
                session_id=job.session_id,
                topology=job.topology,
                simulation_type=job.simulation_type,
                status=JobStatus.CANCELLED,
            )

        except Exception:
            self._job_status[
                job.job_id
            ] = JobStatus.FAILED
            raise

        finally:
            self._cancel_events.pop(
                job.job_id,
                None,
            )

    async def _submit_snapshot(
        self,
        runtime: LocalExecutionSession,
        job: SimulationJob,
        cancel_event: threading.Event,
    ) -> SimulationResult:
        if cancel_event.is_set():
            raise LocalJobCancelled()

        await asyncio.to_thread(
            runtime.engine.set_load_multiplier,
            job.load_multiplier,
        )

        snapshot = await asyncio.to_thread(
            runtime.engine.solve,
            job.session_id,
            job.topology,
        )

        if cancel_event.is_set():
            raise LocalJobCancelled()

        return SimulationResult(
            job_id=job.job_id,
            session_id=job.session_id,
            topology=job.topology,
            simulation_type="snapshot",
            status=JobStatus.COMPLETED,
            snapshot=snapshot,
        )

    async def _submit_qsts(
        self,
        runtime: LocalExecutionSession,
        job: SimulationJob,
        cancel_event: threading.Event,
        progress_handler: ProgressHandler | None,
    ) -> SimulationResult:
        if job.qsts is None:
            raise ValueError(
                "QSTS job requires qsts configuration"
            )

        loop = asyncio.get_running_loop()

        def progress_callback(
            step_result,
            step: int,
            total_steps: int,
        ) -> None:
            if cancel_event.is_set():
                raise LocalJobCancelled()

            progress = SimulationProgress(
                job_id=job.job_id,
                session_id=job.session_id,
                simulation_type="qsts",
                status=JobStatus.RUNNING,
                step=step,
                total_steps=total_steps,
                progress_pct=round(
                    step * 100.0 / total_steps,
                    3,
                ),
                simulated_minutes=(
                    step_result.simulated_minutes
                ),
                simulated_hour=(
                    step_result.simulated_hour
                ),
                converged=step_result.converged,
                solve_ms=step_result.solve_ms,
                load_multiplier=(
                    step_result.load_multiplier
                ),
                total_kw=step_result.total_kw,
                total_kvar=step_result.total_kvar,
                min_voltage_pu=(
                    step_result.min_voltage_pu
                ),
                max_voltage_pu=(
                    step_result.max_voltage_pu
                ),
                opendss_hour=(
                    step_result.opendss_hour
                ),

                opendss_time_of_step_us=(
                    step_result.opendss_time_of_step_us
                ),

                solution_iterations=(
                    step_result.solution_iterations
                ),

                rss_mb=(
                    step_result.rss_mb
                ),
            )

            if progress_handler is not None:
                future = asyncio.run_coroutine_threadsafe(
                    progress_handler(progress),
                    loop,
                )
                future.result()
            if worker_settings.test_progress_delay_ms > 0:
                time.sleep(
                    worker_settings.test_progress_delay_ms / 1000.0
                )

        qsts_result = await asyncio.to_thread(
            runtime.engine.solve_qsts,
            job.qsts,
            progress_callback,
        )

        if cancel_event.is_set():
            raise LocalJobCancelled()

        return SimulationResult(
            job_id=job.job_id,
            session_id=job.session_id,
            topology=job.topology,
            simulation_type="qsts",
            status=JobStatus.COMPLETED,
            qsts=qsts_result,
        )

    async def status(
        self,
        job_id: str,
    ) -> JobStatus:
        try:
            return self._job_status[job_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown job: {job_id}"
            ) from exc

    async def cancel(
        self,
        job_id: str,
    ) -> JobStatus:
        status = await self.status(job_id)

        if status in {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }:
            return status

        cancel_event = self._cancel_events.get(
            job_id
        )

        if cancel_event is not None:
            cancel_event.set()

        self._job_status[
            job_id
        ] = JobStatus.CANCELLED

        return JobStatus.CANCELLED

    async def session_info(
        self,
        session_id: str,
    ) -> ExecutorSessionInfo:
        runtime = self._require_session(
            session_id
        )

        async with runtime.lock:
            if self._sessions.get(session_id) is not runtime:
                raise KeyError("La sesión de ejecución fue cerrada.")
            return self._session_info(runtime)

    async def close_session(
        self,
        session_id: str,
    ) -> None:
        async with self._registry_lock:
            runtime = self._sessions.pop(
                session_id,
                None,
            )

        if runtime is not None:
            async with runtime.lock:
                await asyncio.to_thread(runtime.engine.close)

    async def interactive(
        self, session_id: str, command: WorkerInteractiveCommand,
    ) -> WorkerInteractiveReply:
        runtime = self._sessions.get(session_id)
        if runtime is None:
            raise InteractiveContextLost("El worker ya no tiene el contexto de la simulación.")
        async with runtime.lock:
            if self._sessions.get(session_id) is not runtime:
                raise InteractiveContextLost("El contexto de la simulación se cerró.")
            operation = asyncio.create_task(asyncio.to_thread(self._apply_interactive, runtime, command))
            try:
                return await asyncio.shield(operation)
            except asyncio.CancelledError:
                await operation
                raise

    def _apply_interactive(
        self, runtime: LocalExecutionSession, command: WorkerInteractiveCommand,
    ) -> WorkerInteractiveReply:
        run = runtime.interactive_run
        if isinstance(command, WorkerInitialize):
            if run and run.active and not command.reset:
                raise InteractiveConflict("El worker ya tiene un QSTS activo.")
            engine = runtime.engine
            if command.reset:
                engine = OpenDSSContextEngine(
                    runtime.topology_path, runtime.initial_load_multiplier, model_commands=runtime.model_commands,
                )
            try:
                sequence = engine.begin_qsts(command.config)
                branches, catalog = engine.branch_catalog()
                switches = [engine.switch_state(name) for name in catalog.values()]
            except Exception:
                if command.reset:
                    engine.close()
                raise
            if command.reset:
                old = runtime.engine
                runtime.engine = engine
                old.close()
                runtime.task_count = 0
            runtime.interactive_run = WorkerRun(command.run_id, sequence, catalog)
            return WorkerInteractiveReply(branches=branches, switches=switches)

        if run is None or command.run_id != run.run_id:
            raise InteractiveContextLost("El worker no conserva la ejecución interactiva solicitada.")
        if isinstance(command, WorkerProbe):
            return WorkerInteractiveReply()
        engine = runtime.engine
        if isinstance(command, WorkerSwitches):
            return WorkerInteractiveReply(switches=[engine.switch_state(name) for name in run.catalog.values()])
        if isinstance(command, WorkerStop):
            run.active = False
            return WorkerInteractiveReply()
        if not run.active or command.expected_step != run.sequence.completed:
            raise InteractiveConflict("El worker tiene un paso o estado distinto del solicitado.")
        if isinstance(command, WorkerSwitch):
            element = run.catalog.get(command.element.casefold())
            if element is None:
                raise SwitchNotFoundError("El elemento no es un interruptor controlable.")
            return WorkerInteractiveReply(switch=engine.operate_switch(element, command.action))

        assert isinstance(command, WorkerStep)
        result = engine.advance_interactive(run.sequence)
        if run.sequence.completed == run.sequence.config.total_steps:
            run.active = False
        return WorkerInteractiveReply(
            result=result, switches=[engine.switch_state(name) for name in run.catalog.values()],
        )

    def _require_session(
        self,
        session_id: str,
    ) -> LocalExecutionSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown execution session: "
                f"{session_id}"
            ) from exc

    def _session_info(
        self,
        runtime: LocalExecutionSession,
    ) -> ExecutorSessionInfo:
        return ExecutorSessionInfo(
            session_id=runtime.session_id,
            topology=runtime.topology,
            model_summary=runtime.model_summary,
            task_count=runtime.task_count,
            runtime_identity=runtime.engine.identity,
            load_multiplier=(
                runtime.engine.load_multiplier
            ),
        )

    async def _recycle_if_needed(
        self,
        runtime: LocalExecutionSession,
        result: SimulationResult,
    ) -> None:
        if (
            runtime.task_count
            < self._recycle_threshold
        ):
            return

        load_multiplier = (
            runtime.engine.load_multiplier
        )

        if (
            result.snapshot is not None
        ):
            load_multiplier = (
                result.snapshot.load_multiplier
            )

        elif (
            result.qsts is not None
            and result.qsts.steps
        ):
            load_multiplier = (
                result.qsts.steps[-1]
                .load_multiplier
            )

        old_engine = runtime.engine

        await asyncio.to_thread(
            old_engine.close
        )

        runtime.engine = await asyncio.to_thread(
            OpenDSSContextEngine,
            runtime.topology_path,
            load_multiplier,
            model_commands=runtime.model_commands,
        )

        runtime.model_summary = (
            await asyncio.to_thread(
                runtime.engine.model_summary,
                runtime.topology,
            )
        )

        runtime.task_count = 0
