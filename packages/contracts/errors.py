from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from packages.contracts.version import CONTRACT_VERSION



class SimulationNotFoundError(KeyError):
    """Raised when a simulation session does not exist."""


class TopologyNotFoundError(ValueError):
    """Raised when the requested topology is not available."""


class SimulationClosedError(RuntimeError):
    """Raised when an operation targets a closed simulation."""


class AccessDeniedError(PermissionError):
    """Raised when a user does not own a simulation."""


class QuotaExceededError(RuntimeError):
    """Raised when a user exceeds the concurrent simulation quota."""


class OverloadedError(RuntimeError):
    """Raised when global job capacity is exhausted."""


class SimulationErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    TOPOLOGY_NOT_FOUND = "TOPOLOGY_NOT_FOUND"
    SOLVE_FAILED = "SOLVE_FAILED"
    WORKER_ERROR = "WORKER_ERROR"
    WORKER_LOST = "WORKER_LOST"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SimulationError(BaseModel):
    """
    Serializable error reported by an executor or worker.
    """

    contract_version: Literal["1.0"] = CONTRACT_VERSION

    job_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)

    code: SimulationErrorCode
    message: str = Field(min_length=1)

    retryable: bool = False

    attempt: int = Field(
        default=1,
        ge=1,
    )

    details: dict[str, Any] = Field(
        default_factory=dict
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )