from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts.models import QSTSConfig, QSTSSolveRequest, QSTSStepResult

IntervalSeconds = Annotated[float, Field(ge=0.1, le=3600, allow_inf_nan=False)]
ExecutionMode = Literal["manual", "automatic"]
InteractivePhase = Literal["initializing", "ready", "running", "paused", "stopped", "completed", "interrupted", "failed"]
SwitchAction = Literal["open", "close"]
ParticipantRole = Literal["operator", "viewer"]


class InteractiveStart(QSTSSolveRequest):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    duration_hours: float = Field(default=24, gt=0, le=168)
    step_minutes: float = Field(default=5, ge=1 / 60)
    load_multipliers: list[float] | None = Field(default=None, max_length=10_000)
    execution_mode: ExecutionMode = "manual"
    interval_seconds: IntervalSeconds = 5

    @model_validator(mode="after")
    def limit_steps(self) -> "InteractiveStart":
        if self.to_config().total_steps > 10_000:
            raise ValueError("El QSTS interactivo admite hasta 10000 pasos.")
        return self


class RunReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID


class StepCommand(RunReference):
    command_id: UUID
    expected_step: int = Field(ge=0)


class IntervalCommand(RunReference):
    interval_seconds: IntervalSeconds


class ModeCommand(RunReference):
    execution_mode: ExecutionMode


class SwitchCommand(StepCommand):
    action: SwitchAction


class SwitchState(BaseModel):
    element: str
    status: Literal["open", "closed", "partial"]
    open_conductors: list[list[bool]]


class NetworkBranch(BaseModel):
    element: str
    bus_from: str
    bus_to: str


class InteractiveStepResult(QSTSStepResult):
    loss_kw: float
    loss_kvar: float


class SwitchOperation(BaseModel):
    run_id: UUID
    command_id: UUID
    actor: str
    element: str
    action: SwitchAction
    step: int
    simulated_minutes: float
    timestamp: datetime
    effective_state: SwitchState


class InteractiveState(BaseModel):
    run_id: UUID
    revision: int
    phase: InteractivePhase
    execution_mode: ExecutionMode
    interval_seconds: IntervalSeconds
    duration_hours: float
    step_minutes: float
    profile_source: str
    completed_steps: int
    total_steps: int
    simulated_minutes: float
    next_step_at: datetime | None
    latest_result: InteractiveStepResult | None
    in_flight: bool
    results_stale: bool
    message: str | None = None


class InteractiveStepResponse(BaseModel):
    state: InteractiveState
    result: InteractiveStepResult


class InteractiveEvent(BaseModel):
    type: Literal["interactive_state", "interactive_step", "switch_operation"]
    state: InteractiveState
    switches: list[SwitchState] | None = None
    operation: SwitchOperation | None = None


class ParticipantUpdate(BaseModel):
    role: ParticipantRole


class Participant(BaseModel):
    username: str
    role: ParticipantRole
    invited: bool


class WorkerInitialize(RunReference):
    type: Literal["initialize"] = "initialize"
    config: QSTSConfig
    reset: bool = False


class WorkerStep(RunReference):
    type: Literal["step"] = "step"
    expected_step: int = Field(ge=0)


class WorkerSwitches(RunReference):
    type: Literal["switches"] = "switches"


class WorkerSwitch(RunReference):
    type: Literal["switch"] = "switch"
    element: str
    action: SwitchAction
    expected_step: int = Field(ge=0)


class WorkerStop(RunReference):
    type: Literal["stop"] = "stop"


class WorkerProbe(RunReference):
    type: Literal["probe"] = "probe"


WorkerInteractiveCommand = Annotated[
    WorkerInitialize | WorkerStep | WorkerSwitches | WorkerSwitch | WorkerStop | WorkerProbe,
    Field(discriminator="type"),
]


class WorkerInteractiveReply(BaseModel):
    switches: list[SwitchState] | None = None
    branches: list[NetworkBranch] | None = None
    result: InteractiveStepResult | None = None
    switch: SwitchState | None = None
