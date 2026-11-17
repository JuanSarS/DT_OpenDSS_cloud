from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from packages.contracts.execution import ExecutorSessionInfo, ProgressHandler
from packages.contracts.jobs import JobStatus, SimulationJob
from packages.contracts.results import SimulationResult
from services.api_manager.execution.remote_executor import RemoteSimulationExecutor, RemoteWorkerError
from services.api_manager.execution.worker_discovery import (
    StaticWorkerDiscovery,
    WorkerDiscovery,
)
from services.api_manager.platform.settings import settings
from services.api_manager.security.events import (
    SecurityEvent,
    record_security_event,
)


@dataclass
class WorkerBinding:
    endpoint: str
    topology: str
    load_multiplier: float
    healthy: bool = True
    failures: int = 0


class WorkerPoolSimulationExecutor:
    def __init__(
        self,
        endpoints: list[str] | None = None,
        *,
        discovery: WorkerDiscovery | None = None,
        timeout_seconds: float,
    ) -> None:
        if discovery is None:
            discovery = StaticWorkerDiscovery(endpoints or [])
        self._discovery = discovery
        self._timeout_seconds = timeout_seconds
        self._endpoints: list[str] = []
        self._clients: dict[str, RemoteSimulationExecutor] = {}
        self._bindings: dict[str, WorkerBinding] = {}
        self._job_bindings: dict[str, str] = {}
        self._unhealthy: set[str] = set()
        self._lock = asyncio.Lock()
        self._cursor = 0
        self._worker_failures = 0
        self._job_retries = 0

    async def _sync_workers(self, *, force: bool = False) -> list[str]:
        discovered = [
            endpoint.rstrip("/")
            for endpoint in await self._discovery.endpoints(force=force)
            if endpoint
        ]
        if not discovered:
            raise RuntimeError("Worker discovery no devolvió endpoints")

        async with self._lock:
            for endpoint in discovered:
                if endpoint not in self._clients:
                    self._clients[endpoint] = RemoteSimulationExecutor(
                        base_url=endpoint,
                        timeout_seconds=self._timeout_seconds,
                    )
            self._endpoints = list(dict.fromkeys(discovered))
            self._unhealthy.intersection_update(self._clients.keys())
            return list(self._endpoints)

    async def _choose_worker(
        self,
        exclude: set[str] | None = None,
    ) -> str:
        await self._sync_workers()
        excluded = exclude or set()
        async with self._lock:
            candidates = [
                endpoint
                for endpoint in self._endpoints
                if endpoint not in excluded
                and endpoint not in self._unhealthy
            ]
            if not candidates:
                raise RuntimeError("No hay workers saludables disponibles")

            counts = {endpoint: 0 for endpoint in candidates}
            for binding in self._bindings.values():
                if binding.endpoint in counts:
                    counts[binding.endpoint] += 1

            minimum = min(counts.values())
            least_loaded = [
                endpoint for endpoint, count in counts.items() if count == minimum
            ]
            endpoint = least_loaded[self._cursor % len(least_loaded)]
            self._cursor += 1
            return endpoint

    async def _mark_unhealthy(self, endpoint: str) -> None:
        async with self._lock:
            for binding in self._bindings.values():
                if binding.endpoint == endpoint:
                    binding.healthy = False
                    binding.failures += 1
            self._unhealthy.add(endpoint)
            self._worker_failures += 1

    async def prepare_session(
        self,
        *,
        session_id: str,
        topology: str,
        load_multiplier: float,
    ) -> ExecutorSessionInfo:
        await self._sync_workers(force=True)
        attempted: set[str] = set()
        last_error: Exception | None = None

        for _ in range(max(len(self._endpoints), 1)):
            endpoint = await self._choose_worker(attempted)
            attempted.add(endpoint)
            try:
                info = await self._clients[endpoint].prepare_session(
                    session_id=session_id,
                    topology=topology,
                    load_multiplier=load_multiplier,
                )
                async with self._lock:
                    self._bindings[session_id] = WorkerBinding(
                        endpoint=endpoint,
                        topology=topology,
                        load_multiplier=load_multiplier,
                    )
                return ExecutorSessionInfo(
                    session_id=info.session_id,
                    topology=info.topology,
                    model_summary=info.model_summary,
                    task_count=info.task_count,
                    runtime_identity=endpoint,
                    load_multiplier=info.load_multiplier,
                )
            except Exception as exc:
                last_error = exc
                if not self._recoverable(exc):
                    raise
                await self._mark_unhealthy(endpoint)

        if last_error is not None:
            raise last_error
        raise RuntimeError("No fue posible preparar la sesión en ningún worker")

    def _binding(self, session_id: str) -> WorkerBinding:
        try:
            return self._bindings[session_id]
        except KeyError as exc:
            raise KeyError(f"No existe binding para {session_id}") from exc

    @staticmethod
    def _recoverable(exc: Exception) -> bool:
        if isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.TimeoutException,
            ),
        ):
         
            return True
        
        if (
            isinstance(exc, RemoteWorkerError)
            and "Worker stream ended without SimulationResult" in str(exc)
        ):
            return True
        return isinstance(exc, httpx.HTTPStatusError) and (
            exc.response.status_code in {502, 503, 504}
        )

    async def submit(
        self,
        job: SimulationJob,
        progress_handler: ProgressHandler | None = None,
    ) -> SimulationResult:
        binding = self._binding(job.session_id)
        current_endpoint = binding.endpoint
        self._job_bindings[job.job_id] = current_endpoint

        try:
            return await self._clients[current_endpoint].submit(job, progress_handler)
        except Exception as exc:
            if not settings.worker_retry_enabled or not self._recoverable(exc):
                raise
            last_error: Exception = exc

        failed_endpoints: set[str] = {current_endpoint}
        for retry_index in range(settings.worker_max_retries):
            await self._mark_unhealthy(current_endpoint)
            record_security_event(
                SecurityEvent.WORKER_LOST.value,
                detail=current_endpoint,
            )
            await asyncio.sleep(settings.worker_retry_backoff_seconds)
            await self._sync_workers(force=True)

            try:
                endpoint = await self._choose_worker(failed_endpoints)
                await self._clients[endpoint].prepare_session(
                    session_id=job.session_id,
                    topology=binding.topology,
                    load_multiplier=binding.load_multiplier,
                )
                async with self._lock:
                    self._bindings[job.session_id] = WorkerBinding(
                        endpoint=endpoint,
                        topology=binding.topology,
                        load_multiplier=binding.load_multiplier,
                    )
                    self._job_retries += 1

                record_security_event(
                    SecurityEvent.JOB_RETRY.value,
                    detail=f"{current_endpoint} -> {endpoint}",
                )

                retry_job = job.model_copy(
                    update={"attempt": job.attempt + retry_index + 1}
                )
                self._job_bindings[retry_job.job_id] = endpoint
                try:
                    return await self._clients[endpoint].submit(
                        retry_job,
                        progress_handler,
                    )
                except Exception as retry_submit_error:
                    if not self._recoverable(retry_submit_error):
                        raise
                    last_error = retry_submit_error
                    current_endpoint = endpoint
                    failed_endpoints.add(endpoint)
            except Exception as retry_error:
                if not self._recoverable(retry_error):
                    raise
                last_error = retry_error
                if "endpoint" in locals():
                    current_endpoint = endpoint
                    failed_endpoints.add(endpoint)

        raise last_error

    async def status(self, job_id: str) -> JobStatus:
        endpoint = self._job_bindings[job_id]
        return await self._clients[endpoint].status(job_id)

    async def cancel(self, job_id: str) -> JobStatus:
        endpoint = self._job_bindings[job_id]
        return await self._clients[endpoint].cancel(job_id)

    async def session_info(self, session_id: str) -> ExecutorSessionInfo:
        binding = self._binding(session_id)
        current_endpoint = binding.endpoint

        try:
            info = await self._clients[current_endpoint].session_info(session_id)

            return ExecutorSessionInfo(
                session_id=info.session_id,
                topology=info.topology,
                model_summary=info.model_summary,
                task_count=info.task_count,
                runtime_identity=current_endpoint,
                load_multiplier=info.load_multiplier,
            )

        except Exception as exc:
            if (
                not settings.worker_retry_enabled
                or not self._recoverable(exc)
            ):
                raise

            last_error: Exception = exc
            failed_endpoints: set[str] = {current_endpoint}

            await self._mark_unhealthy(current_endpoint)

            record_security_event(
                SecurityEvent.WORKER_LOST.value,
                detail=current_endpoint,
            )

            await asyncio.sleep(
                settings.worker_retry_backoff_seconds
            )

            for _ in range(settings.worker_max_retries):
                await self._sync_workers(force=True)

                endpoint: str | None = None

                try:
                    endpoint = await self._choose_worker(
                        failed_endpoints
                    )

                    info = await self._clients[
                        endpoint
                    ].prepare_session(
                        session_id=session_id,
                        topology=binding.topology,
                        load_multiplier=binding.load_multiplier,
                    )

                    async with self._lock:
                        self._bindings[
                            session_id
                        ] = WorkerBinding(
                            endpoint=endpoint,
                            topology=binding.topology,
                            load_multiplier=binding.load_multiplier,
                        )

                    return ExecutorSessionInfo(
                        session_id=info.session_id,
                        topology=info.topology,
                        model_summary=info.model_summary,
                        task_count=info.task_count,
                        runtime_identity=endpoint,
                        load_multiplier=info.load_multiplier,
                    )

                except Exception as recovery_error:
                    last_error = recovery_error

                    if not self._recoverable(
                        recovery_error
                    ):
                        raise

                    if endpoint is not None:
                        failed_endpoints.add(endpoint)
                        await self._mark_unhealthy(
                            endpoint
                        )

                    await asyncio.sleep(
                        settings.worker_retry_backoff_seconds
                    )

            raise last_error

    async def close_session(self, session_id: str) -> None:
        binding = self._binding(session_id)
        try:
            await self._clients[binding.endpoint].close_session(session_id)
        except Exception as exc:
            if not self._recoverable(exc):
                raise
        finally:
            async with self._lock:
                self._bindings.pop(session_id, None)

    async def health_probe(self) -> dict[str, object]:
        await self._sync_workers(force=True)
        healthy = 0
        states: dict[str, bool] = {}
        for endpoint in list(self._endpoints):
            try:
                async with httpx.AsyncClient(
                    base_url=endpoint,
                    timeout=5.0,
                ) as client:
                    response = await client.get("/internal/health")
                    response.raise_for_status()
                states[endpoint] = True
                healthy += 1
                async with self._lock:
                    self._unhealthy.discard(endpoint)
                    for binding in self._bindings.values():
                        if binding.endpoint == endpoint:
                            binding.healthy = True
            except httpx.HTTPError:
                states[endpoint] = False
                async with self._lock:
                    self._unhealthy.add(endpoint)

        return {
            "worker_count": len(self._endpoints),
            "healthy_workers": healthy,
            "unhealthy_workers": len(self._endpoints) - healthy,
            "workers": states,
        }

    def metrics_snapshot(self) -> dict[str, object]:
        counts = {endpoint: 0 for endpoint in self._endpoints}
        for binding in self._bindings.values():
            counts[binding.endpoint] = counts.get(binding.endpoint, 0) + 1
        return {
            "worker_count": len(self._endpoints),
            "healthy_workers": len(self._endpoints) - len(self._unhealthy),
            "unhealthy_workers": len(self._unhealthy),
            "sessions_per_worker": counts,
            "worker_failures": self._worker_failures,
            "job_retries": self._job_retries,
        }
