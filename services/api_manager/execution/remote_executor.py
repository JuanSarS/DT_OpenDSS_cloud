from __future__ import annotations

import json

import httpx

from packages.common.secrets import read_secret
from packages.contracts.errors import SimulationError
from packages.contracts.execution import ExecutorSessionInfo, ProgressHandler
from packages.contracts.jobs import JobStatus, SimulationJob
from packages.contracts.progress import SimulationProgress
from packages.contracts.results import SimulationResult
from packages.contracts.worker_api import (
    WorkerExecuteRequest,
    WorkerJobStatusResponse,
    WorkerPrepareSessionRequest,
    WorkerSessionInfo,
)


class RemoteWorkerError(RuntimeError):
    pass


class RemoteSimulationExecutor:
    def __init__(self, *, base_url: str, timeout_seconds: float = 600.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout),
            headers={
                "Authorization": (
                    "Bearer " + read_secret("WORKER_SHARED_TOKEN")
                )
            },
        )

    async def prepare_session(
        self, *, session_id: str, topology: str, load_multiplier: float
    ) -> ExecutorSessionInfo:
        request = WorkerPrepareSessionRequest(
            session_id=session_id,
            topology=topology,
            load_multiplier=load_multiplier,
        )
        async with self._client() as client:
            response = await client.post(
                "/internal/sessions",
                json=request.model_dump(mode="json"),
            )
            self._raise_prepare_error(
                response
            )
            return WorkerSessionInfo.model_validate(
                response.json()
            ).to_executor_info()

    async def submit(
        self,
        job: SimulationJob,
        progress_handler: ProgressHandler | None = None,
    ) -> SimulationResult:
        result = None
        async with self._client() as client:
            async with client.stream(
                "POST",
                "/internal/jobs/execute",
                json=WorkerExecuteRequest(job=job).model_dump(mode="json"),
            ) as response:
                self._raise_prepare_error(
                response
            )
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    payload = event.get("payload")
                    if event.get("type") == "progress":
                        if progress_handler is not None:
                            await progress_handler(
                                SimulationProgress.model_validate(payload)
                            )
                    elif event.get("type") == "result":
                        result = SimulationResult.model_validate(payload)
                    elif event.get("type") == "error":
                        error = SimulationError.model_validate(payload)
                        raise RemoteWorkerError(
                            f"{error.code}: {error.message}"
                        )
        if result is None:
            raise RemoteWorkerError("Worker stream ended without SimulationResult")
        return result

    async def status(self, job_id: str) -> JobStatus:
        async with self._client() as client:
            response = await client.get(f"/internal/jobs/{job_id}/status")
            self._raise_prepare_error(
                response
            )
            return WorkerJobStatusResponse.model_validate(
                response.json()
            ).status

    async def cancel(self, job_id: str) -> JobStatus:
        async with self._client() as client:
            response = await client.post(f"/internal/jobs/{job_id}/cancel")
            self._raise_prepare_error(
                response
            )
            return WorkerJobStatusResponse.model_validate(
                response.json()
            ).status

    async def session_info(self, session_id: str) -> ExecutorSessionInfo:
        async with self._client() as client:
            response = await client.get(f"/internal/sessions/{session_id}")
            self._raise_prepare_error(
                response
            )
            return WorkerSessionInfo.model_validate(
                response.json()
            ).to_executor_info()

    async def close_session(self, session_id: str) -> None:
        async with self._client() as client:
            response = await client.delete(f"/internal/sessions/{session_id}")
            self._raise_prepare_error(
                response
            )

    def _raise_prepare_error(
        self,
        response: httpx.Response,
    ) -> None:
        if not response.is_error:
            return

        if response.status_code in {
            502,
            503,
            504,
        }:
        
            response.raise_for_status()

        try:
            payload = response.json()

            detail = payload.get(
                "detail",
                response.text,
            )

        except Exception:
            detail = response.text

        raise RemoteWorkerError(
            f"Worker {self._base_url}: "
            f"{detail or 'error desconocido'}"
        )