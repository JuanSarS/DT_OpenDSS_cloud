from app.platform.settings import settings
from packages.contracts.execution import (
    SimulationExecutor,
)


def build_simulation_executor(
) -> SimulationExecutor:

    backend = (
        settings.execution_backend
        .strip()
        .lower()
    )

    if backend == "local":
        from services.simulation_worker.executor import (
            LocalSimulationExecutor,
        )

        return LocalSimulationExecutor(
            recycle_threshold=(
                settings.recycle_threshold
            )
        )

    if backend == "worker_http":
        from services.api_manager.execution.remote_executor import (
            RemoteSimulationExecutor,
        )

        return RemoteSimulationExecutor(
            base_url=(
                settings.simulation_worker_url
            ),
            timeout_seconds=(
                settings
                .simulation_worker_timeout_seconds
            ),
        )

    raise RuntimeError(
        "Unsupported execution backend: "
        f"{settings.execution_backend}"
    )