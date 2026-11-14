from packages.contracts.execution  import (
    SimulationExecutor,
)
from services.simulation_worker.executor import (
    LocalSimulationExecutor,
)


def test_local_executor_implements_protocol() -> None:
    executor = LocalSimulationExecutor()

    assert isinstance(
        executor,
        SimulationExecutor,
    )