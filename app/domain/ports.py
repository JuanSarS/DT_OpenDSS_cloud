from typing import Protocol

from app.domain.models import SolveResponse


class SimulationEngine(Protocol):
    @property
    def identity(self) -> int:
        ...

    def solve(self, session_id: str, topology: str) -> SolveResponse:
        ...
