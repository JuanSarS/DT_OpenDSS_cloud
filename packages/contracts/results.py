from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from packages.contracts.jobs import JobStatus
from packages.contracts.models import QSTSResult, SolveResponse
from packages.contracts.version import CONTRACT_VERSION


class SimulationResult(BaseModel):
    """
    Provider-independent result produced by one simulation job.

    A result may initially travel inline. Future cloud execution may
    use result_uri for large artifacts stored externally.
    """

    contract_version: Literal["1.0"] = CONTRACT_VERSION

    job_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    topology: str = Field(min_length=1)

    simulation_type: Literal["snapshot", "qsts"]

    status: JobStatus = JobStatus.COMPLETED

    snapshot: SolveResponse | None = None
    qsts: QSTSResult | None = None

    # Reserved for future S3/object-storage results.
    result_uri: str | None = None

    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @model_validator(mode="after")
    def validate_result_payload(self) -> "SimulationResult":
        if self.status != JobStatus.COMPLETED:
            return self

        if self.simulation_type == "snapshot":
            if self.snapshot is None and self.result_uri is None:
                raise ValueError(
                    "Snapshot requiere snapshot o result_uri"
                )

            if self.qsts is not None:
                raise ValueError(
                    "Un resultado Snapshot no puede contener qsts"
                )

        if self.simulation_type == "qsts":
            if self.qsts is None and self.result_uri is None:
                raise ValueError(
                    "QSTS requiere qsts o result_uri"
                )

            if self.snapshot is not None:
                raise ValueError(
                    "Un resultado QSTS no puede contener snapshot"
                )

        return self