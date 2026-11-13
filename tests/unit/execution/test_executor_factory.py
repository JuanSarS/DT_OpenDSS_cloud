from services.api_manager.execution.factory import (
    build_simulation_executor,
)
from services.api_manager.execution.local_executor import (
    LocalSimulationExecutor,
)


def test_default_executor_is_local() -> None:
    executor = build_simulation_executor()

    assert isinstance(
        executor,
        LocalSimulationExecutor,
    )