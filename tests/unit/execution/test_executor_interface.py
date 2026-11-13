from services.api_manager.execution.base import (
    SimulationExecutor,
)
from services.api_manager.execution.local_executor import (
    LocalSimulationExecutor,
)


def test_local_executor_implements_protocol() -> None:
    executor = LocalSimulationExecutor()

    assert isinstance(
        executor,
        SimulationExecutor,
    )