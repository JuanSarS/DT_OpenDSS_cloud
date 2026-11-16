from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from packages.contracts.execution import (
    ExecutorSessionInfo,
)
from packages.contracts.jobs import (
    JobStatus,
    SimulationJob,
)
from packages.contracts.models import ModelSummary


class WorkerPrepareSessionRequest(BaseModel):
    session_id: str = Field(min_length=1)
    topology: str = Field(min_length=1)
    load_multiplier: float = Field(
        default=1.0,
        gt=0.0,
        le=5.0,
    )


class WorkerSessionInfo(BaseModel):
    session_id: str
    topology: str
    model_summary: ModelSummary
    task_count: int
    runtime_identity: int | str | None
    load_multiplier: float

    @classmethod
    def from_executor_info(
        cls,
        info: ExecutorSessionInfo,
    ) -> "WorkerSessionInfo":
        return cls(
            session_id=info.session_id,
            topology=info.topology,
            model_summary=info.model_summary,
            task_count=info.task_count,
            runtime_identity=info.runtime_identity,
            load_multiplier=info.load_multiplier,
        )

    def to_executor_info(
        self,
    ) -> ExecutorSessionInfo:
        return ExecutorSessionInfo(
            session_id=self.session_id,
            topology=self.topology,
            model_summary=self.model_summary,
            task_count=self.task_count,
            runtime_identity=self.runtime_identity,
            load_multiplier=self.load_multiplier,
        )


class WorkerExecuteRequest(BaseModel):
    job: SimulationJob


class WorkerJobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus


class WorkerHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["simulation-worker"] = (
        "simulation-worker"
    )
    pid: int