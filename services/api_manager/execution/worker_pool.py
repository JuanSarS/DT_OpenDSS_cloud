from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from packages.contracts.execution import ExecutorSessionInfo, ProgressHandler
from packages.contracts.jobs import JobStatus, SimulationJob
from packages.contracts.results import SimulationResult
from services.api_manager.execution.remote_executor import RemoteSimulationExecutor
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
        endpoints: list[str],
        *,
        timeout_seconds: float,
    ) -> None:
        self._endpoints = [endpoint.rstrip("/") for endpoint in endpoints if endpoint]
        self._clients = {
            endpoint: RemoteSimulationExecutor(
                base_url=endpoint,
                timeout_seconds=timeout_seconds,
            )
            for endpoint in self._endpoints
        }
        self._bindings: dict[str, WorkerBinding] = {}
        self._job_bindings: dict[str, str] = {}
        self._unhealthy: set[str] = set()
        self._lock = asyncio.Lock()
        self._cursor = 0
        self._worker_failures = 0
        self._job_retries = 0

    async def _choose_worker(self, exclude: str | None = None) -> str:
        async with self._lock:
            candidates = [
                endpoint for endpoint in self._endpoints
                if endpoint != exclude
            ]
            if not candidates:
                raise RuntimeError("No hay workers disponibles")
            healthy = [endpoint for endpoint in candidates if endpoint not in self._unhealthy]
            if not healthy:
                raise RuntimeError("No hay workers saludables disponibles")
            candidates = healthy
            endpoint = candidates[self._cursor % len(candidates)]
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
        self, *, session_id: str, topology: str, load_multiplier: float
    ) -> ExecutorSessionInfo:
        endpoint = await self._choose_worker()
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
        return isinstance(exc, httpx.HTTPStatusError) and (
            exc.response.status_code in {502, 503, 504}
        )

    async def submit(
        self,
        job: SimulationJob,
        progress_handler: ProgressHandler | None = None,
    ) -> SimulationResult:
        binding = self._binding(job.session_id)
        client = self._clients[binding.endpoint]
        try:
            self._job_bindings[job.job_id] = binding.endpoint
            return await client.submit(job, progress_handler)
        except Exception as exc:
            if not settings.worker_retry_enabled or not self._recoverable(exc):
                raise
            last_error = exc
            for _ in range(settings.worker_max_retries):
                await self._mark_unhealthy(binding.endpoint)
                record_security_event(
                    SecurityEvent.WORKER_LOST.value,
                    detail=binding.endpoint,
                )
                await asyncio.sleep(settings.worker_retry_backoff_seconds)
                try:
                    endpoint = await self._choose_worker(binding.endpoint)
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
                        detail=endpoint,
                    )
                    retry_job = job.model_copy(
                        update={"attempt": job.attempt + 1}
                    )
                    self._job_bindings[retry_job.job_id] = endpoint
                    return await self._clients[endpoint].submit(
                        retry_job,
                        progress_handler,
                    )
                except Exception as retry_error:
                    last_error = retry_error
            raise last_error

    async def status(self, job_id: str) -> JobStatus:
        endpoint = self._job_bindings[job_id]
        return await self._clients[endpoint].status(job_id)

    async def cancel(self, job_id: str) -> JobStatus:
        endpoint = self._job_bindings[job_id]
        return await self._clients[endpoint].cancel(job_id)

    async def session_info(self, session_id: str) -> ExecutorSessionInfo:
        binding = self._binding(session_id)
        info = await self._clients[binding.endpoint].session_info(session_id)
        return ExecutorSessionInfo(
            session_id=info.session_id,
            topology=info.topology,
            model_summary=info.model_summary,
            task_count=info.task_count,
            runtime_identity=binding.endpoint,
            load_multiplier=info.load_multiplier,
        )

    async def close_session(self, session_id: str) -> None:
        binding = self._binding(session_id)
        await self._clients[binding.endpoint].close_session(session_id)
        async with self._lock:
            self._bindings.pop(session_id, None)

    async def health_probe(self) -> dict[str, object]:
        healthy = 0
        states: dict[str, bool] = {}
        for endpoint in self._endpoints:
            try:
                async with httpx.AsyncClient(
                    base_url=endpoint,
                    timeout=5.0,
                ) as client:
                    response = await client.get("/internal/health")
                    response.raise_for_status()
                states[endpoint] = True
                healthy += 1
                self._unhealthy.discard(endpoint)
            except httpx.HTTPError:
                states[endpoint] = False
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
