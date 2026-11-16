from services.api_manager.platform.settings import settings
from packages.contracts.execution import SimulationExecutor


def build_simulation_executor() -> SimulationExecutor:
    backend = settings.execution_backend.strip().lower()

    if backend == "local":
        from services.simulation_worker.executor import LocalSimulationExecutor

        return LocalSimulationExecutor(
            recycle_threshold=settings.recycle_threshold
        )

    if backend == "worker_http":
        from services.api_manager.execution.remote_executor import (
            RemoteSimulationExecutor,
        )

        return RemoteSimulationExecutor(
            base_url=settings.simulation_worker_url,
            timeout_seconds=settings.simulation_worker_timeout_seconds,
        )

    if backend == "worker_pool":
        from services.api_manager.execution.worker_discovery import (
            DnsWorkerDiscovery,
            StaticWorkerDiscovery,
        )
        from services.api_manager.execution.worker_pool import (
            WorkerPoolSimulationExecutor,
        )

        discovery_backend = settings.worker_discovery_backend.strip().lower()
        if discovery_backend == "dns":
            discovery = DnsWorkerDiscovery(
                host=settings.worker_discovery_host,
                port=settings.worker_discovery_port,
                scheme=settings.worker_discovery_scheme,
                refresh_seconds=settings.worker_discovery_refresh_seconds,
            )
        elif discovery_backend == "static":
            endpoints = [
                item.strip()
                for item in settings.simulation_worker_urls.split(",")
                if item.strip()
            ] or [settings.simulation_worker_url]
            discovery = StaticWorkerDiscovery(endpoints)
        else:
            raise RuntimeError(
                "Unsupported worker discovery backend: "
                f"{settings.worker_discovery_backend}"
            )

        return WorkerPoolSimulationExecutor(
            discovery=discovery,
            timeout_seconds=settings.simulation_worker_timeout_seconds,
        )

    raise RuntimeError(
        "Unsupported execution backend: "
        f"{settings.execution_backend}"
    )
