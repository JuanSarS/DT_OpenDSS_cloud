from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class CreateSimulationRequest(BaseModel):
    topology: str = Field(
        default="ieee13",
        description="Logical topology name registered in the topology catalog.",
    )
    load_multiplier: float = Field(
        default=1.0,
        gt=0.0,
        le=5.0,
        description="OpenDSS load multiplier. Useful for isolation tests.",
    )


class CreateSimulationResponse(BaseModel):
    session_id: str
    topology: str
    load_multiplier: float
    created_at: datetime


class SimulationStatus(str, Enum):
    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    ERROR = "ERROR"


class ModelSummary(BaseModel):
    topology: str
    num_buses: int
    num_nodes: int
    node_names: list[str]


class SimulationSummary(BaseModel):
    session_id: str
    topology: str
    status: SimulationStatus
    created_at: datetime
    task_count: int


class SimulationDetail(SimulationSummary):
    model_summary: ModelSummary
    last_result: "SolveResponse | None" = None
    worker_identity: int


class ComplexValue(BaseModel):
    real: float
    imag: float
    magnitude: float
    angle_deg: float


class SolveResponse(BaseModel):
    session_id: str
    topology: str
    converged: bool
    elapsed_ms: float
    load_multiplier: float
    total_power_kw: float
    total_power_kvar: float
    voltages: dict[str, ComplexValue]
    currents: dict[str, list[ComplexValue]]
