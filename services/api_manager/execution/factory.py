from app.platform.settings import settings
from services.api_manager.execution.base import (
    SimulationExecutor,
)
from services.api_manager.execution.local_executor import (
    LocalSimulationExecutor,
)


def build_simulation_executor() -> SimulationExecutor:
    backend = settings.execution_backend.strip().lower()

    if backend == "local":
        return LocalSimulationExecutor(
            recycle_threshold=(
                settings.recycle_threshold
            )
        )

    raise RuntimeError(
        "Unsupported execution backend: "
        f"{settings.execution_backend}"
    )