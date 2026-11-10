from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from packages.contracts.models import QSTSConfig
from packages.contracts.version import CONTRACT_VERSION


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SimulationJob(BaseModel):
    """
    Provider-independent description of one simulation job.

    This contract must not contain FastAPI, WebSocket, ECS, SQS,
    filesystem handles or an OpenDSS engine instance.
    """

    contract_version: Literal["1.0"] = CONTRACT_VERSION

    job_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)

    # It remains optional until authentication is introduced.
    user_id: str | None = None

    topology: str = Field(min_length=1)

    simulation_type: Literal["snapshot", "qsts"]

    # Effective multiplier for Snapshot.
    load_multiplier: float = Field(
        default=1.0,
        gt=0.0,
        le=5.0,
    )

    # Required only for QSTS.
    qsts: QSTSConfig | None = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    attempt: int = Field(
        default=1,
        ge=1,
    )

    @model_validator(mode="after")
    def validate_simulation_configuration(self) -> "SimulationJob":
        if self.simulation_type == "qsts" and self.qsts is None:
            raise ValueError(
                "qsts es obligatorio para simulation_type='qsts'"
            )

        if self.simulation_type == "snapshot" and self.qsts is not None:
            raise ValueError(
                "qsts no se permite para simulation_type='snapshot'"
            )

        return self