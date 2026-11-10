from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    simulation_type: Literal["snapshot", "qsts"] | None = None
    last_result: "SolveResponse | QSTSResult | None" = None
    last_error: str | None = None
    current_step: int | None = None
    total_steps: int | None = None
    progress_pct: float | None = None
    simulated_hour: float | None = None
    last_qsts_step: "QSTSStepResult | None" = None
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


class QSTSSolveRequest(BaseModel):
    duration_hours: float = Field(
        default=24.0,
        gt=0.0,
        description="Duración total de la simulación temporal en horas.",
    )
    step_minutes: float = Field(
        default=5.0,
        gt=0.0,
        description="Tamaño de cada paso temporal en minutos.",
    )
    profile_source: Literal[
        "constant", "synthetic_daily", "model", "values"
    ] = Field(
        default="constant",
        description="Origen del multiplicador temporal.",
    )
    load_multiplier: float | None = Field(
        default=None,
        gt=0.0,
        description="Multiplicador constante para el perfil constant.",
    )
    load_multipliers: list[float] | None = Field(
        default=None,
        description="Un multiplicador positivo por cada paso para profile_source=values.",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_numeric_values(cls, values: object) -> object:
        if isinstance(values, dict) and values.get("load_multipliers") is not None:
            multipliers = values["load_multipliers"]
            if not isinstance(multipliers, list) or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                for value in multipliers
            ):
                raise ValueError("load_multipliers debe ser una lista de valores numéricos")
        return values

    @model_validator(mode="after")
    def validate_profile_values(self) -> "QSTSSolveRequest":
        raw_steps = self.duration_hours * 60.0 / self.step_minutes
        total_steps = round(raw_steps)
        if total_steps < 1 or abs(raw_steps - total_steps) > 1e-9:
            raise ValueError("duration_hours debe ser divisible entre step_minutes")
        if self.profile_source == "values":
            if self.load_multipliers is None:
                raise ValueError(
                    "load_multipliers es obligatorio para profile_source='values'"
                )
            if len(self.load_multipliers) != total_steps:
                raise ValueError(
                    "load_multipliers debe tener exactamente "
                    f"{total_steps} valores para esta configuración"
                )
        elif self.load_multipliers is not None:
            raise ValueError(
                "load_multipliers solo se permite con profile_source='values'"
            )
        return self

    def to_config(self) -> "QSTSConfig":
        return QSTSConfig(
            duration_hours=self.duration_hours,
            step_minutes=self.step_minutes,
            profile_source=self.profile_source,
            load_multiplier=self.load_multiplier or 1.0,
            load_multipliers=self.load_multipliers,
        )


class SolveRequest(BaseModel):
    simulation_type: Literal["snapshot", "qsts"] = Field(
        default="snapshot",
        description="Tipo de simulación a ejecutar.",
    )
    load_multiplier: float | None = Field(
        default=None,
        gt=0.0,
        description="Multiplicador para Snapshot o perfil constant de QSTS.",
    )
    qsts: QSTSSolveRequest | None = Field(
        default=None,
        description="Configuración requerida cuando simulation_type=qsts.",
    )

    @model_validator(mode="after")
    def validate_type_configuration(self) -> "SolveRequest":
        if self.simulation_type == "qsts" and self.qsts is None:
            raise ValueError("qsts es obligatorio cuando simulation_type='qsts'")
        if self.simulation_type == "snapshot" and self.qsts is not None:
            raise ValueError("qsts solo se permite cuando simulation_type='qsts'")
        return self


class QSTSSolveSummary(BaseModel):
    total_steps: int
    converged_steps: int
    failed_steps: int
    elapsed_ms: float
    solve_mean_ms: float
    solve_p50_ms: float
    solve_p95_ms: float
    solve_max_ms: float
    rss_start_mb: float | None
    rss_peak_mb: float | None


class QSTSSolveResponse(BaseModel):
    session_id: str
    simulation_type: Literal["qsts"] = "qsts"
    status: SimulationStatus
    summary: QSTSSolveSummary


class QSTSConfig(BaseModel):
    duration_hours: float = Field(default=24.0, gt=0.0)
    step_minutes: float = Field(default=5.0, gt=0.0)
    profile_source: Literal[
        "constant", "synthetic_daily", "model", "values"
    ] = "constant"
    load_multiplier: float = Field(default=1.0, gt=0.0)
    load_multipliers: list[float] | None = None

    @property
    def total_steps(self) -> int:
        raw_steps = self.duration_hours * 60.0 / self.step_minutes
        rounded_steps = round(raw_steps)
        if rounded_steps < 1 or abs(raw_steps - rounded_steps) > 1e-9:
            raise ValueError("duration_hours debe ser divisible entre step_minutes")
        return rounded_steps

    @model_validator(mode="after")
    def validate_profile(self) -> "QSTSConfig":
        if self.profile_source == "values" and self.load_multipliers is None:
            raise ValueError("load_multipliers es obligatorio para profile_source='values'")
        if self.profile_source == "values" and not self.load_multipliers:
            raise ValueError("load_multipliers no puede estar vacío")
        if self.load_multipliers is not None:
            if len(self.load_multipliers) != self.total_steps:
                raise ValueError("load_multipliers debe tener un valor por paso QSTS")
            if any(multiplier <= 0 for multiplier in self.load_multipliers):
                raise ValueError("load_multipliers debe contener valores positivos")
        return self


class QSTSStepResult(BaseModel):
    step: int = Field(ge=1)
    simulated_minutes: float = Field(ge=0.0)
    simulated_hour: float = Field(ge=0.0)
    opendss_hour: float | None = None
    opendss_time_of_step_us: float | None = None
    converged: bool
    solve_ms: float = Field(ge=0.0)
    load_multiplier: float = Field(gt=0.0)
    total_kw: float | None = None
    total_kvar: float | None = None
    min_voltage_pu: float | None = None
    max_voltage_pu: float | None = None
    solution_iterations: int | None = Field(default=None, ge=0)
    # RSS is for the Python process containing the active OpenDSS context.
    rss_mb: float | None = Field(default=None, ge=0.0)


class QSTSResult(BaseModel):
    config: QSTSConfig
    total_steps: int = Field(ge=1)
    converged_steps: int = Field(ge=0)
    failed_steps: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0.0)
    solve_mean_ms: float = Field(ge=0.0)
    solve_p50_ms: float = Field(ge=0.0)
    solve_p95_ms: float = Field(ge=0.0)
    solve_max_ms: float = Field(ge=0.0)
    rss_start_mb: float | None = Field(default=None, ge=0.0)
    rss_peak_mb: float | None = Field(default=None, ge=0.0)
    steps: list[QSTSStepResult]
