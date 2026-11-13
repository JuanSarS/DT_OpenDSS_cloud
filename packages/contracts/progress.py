from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from packages.contracts.jobs import JobStatus
from packages.contracts.version import CONTRACT_VERSION


class SimulationProgress(BaseModel):
    """
    Compact progress message emitted by a simulation worker.

    It intentionally avoids large voltage/current vectors.
    """

    contract_version: Literal["1.0"] = CONTRACT_VERSION

    job_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)

    simulation_type: Literal["snapshot", "qsts"]

    status: JobStatus = JobStatus.RUNNING

    step: int | None = Field(
        default=None,
        ge=0,
    )

    total_steps: int | None = Field(
        default=None,
        ge=1,
    )

    progress_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )

    simulated_minutes: float | None = Field(
        default=None,
        ge=0.0,
    )

    simulated_hour: float | None = Field(
        default=None,
        ge=0.0,
    )

    converged: bool | None = None

    solve_ms: float | None = Field(
        default=None,
        ge=0.0,
    )

    load_multiplier: float | None = Field(
        default=None,
        gt=0.0,
    )

    total_kw: float | None = None
    total_kvar: float | None = None

    min_voltage_pu: float | None = None
    max_voltage_pu: float | None = None

    opendss_hour: float | None = None

    opendss_time_of_step_us: float | None = None

    solution_iterations: int | None = Field(
        default=None,
        ge=0,
    )

    rss_mb: float | None = Field(
        default=None,
        ge=0.0,
    )
    
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )