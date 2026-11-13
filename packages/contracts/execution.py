from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol, runtime_checkable

from packages.contracts.jobs import JobStatus, SimulationJob
from packages.contracts.models import ModelSummary
from packages.contracts.progress import SimulationProgress
from packages.contracts.results import SimulationResult


ProgressHandler = Callable[
    [SimulationProgress],
    Awaitable[None],
]


@dataclass(frozen=True)
class ExecutorSessionInfo:
    """
    Information exposed by an executor about one logical
    simulation session.

    runtime_identity is intentionally opaque to the API.
    Local execution may expose an integer engine identity,
    while a remote executor may expose a worker/task id.
    """

    session_id: str
    topology: str
    model_summary: ModelSummary
    task_count: int
    runtime_identity: int | str | None
    load_multiplier: float


@runtime_checkable
class SimulationExecutor(Protocol):
    """
    Execution boundary between API orchestration and the
    underlying simulation runtime.

    Implementations may execute locally, in another process,
    in Docker, ECS/Fargate or another provider.
    """

    async def prepare_session(
        self,
        *,
        session_id: str,
        topology: str,
        topology_source: str,
        load_multiplier: float,
    ) -> ExecutorSessionInfo:
        ...

    async def submit(
        self,
        job: SimulationJob,
        progress_handler: ProgressHandler | None = None,
    ) -> SimulationResult:
        ...

    async def status(
        self,
        job_id: str,
    ) -> JobStatus:
        ...

    async def cancel(
        self,
        job_id: str,
    ) -> JobStatus:
        ...

    async def session_info(
        self,
        session_id: str,
    ) -> ExecutorSessionInfo:
        ...

    async def close_session(
        self,
        session_id: str,
    ) -> None:
        ...