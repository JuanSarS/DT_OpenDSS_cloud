from typing import Callable, Protocol

from app.domain.models import QSTSConfig, QSTSResult, QSTSStepResult, SolveResponse


class SimulationEngine(Protocol):
    @property
    def identity(self) -> int:
        ...

    def solve(self, session_id: str, topology: str) -> SolveResponse:
        ...

    def solve_qsts(
        self,
        config: QSTSConfig,
        progress_callback: Callable[[QSTSStepResult, int, int], None] | None = None,
    ) -> QSTSResult:
        ...

    def set_load_multiplier(self, load_multiplier: float) -> None:
        ...
