from __future__ import annotations

import json

import httpx

from packages.contracts.errors import (
    SimulationError,
)
from packages.contracts.execution import (
    ExecutorSessionInfo,
    ProgressHandler,
)
from packages.contracts.jobs import (
    JobStatus,
    SimulationJob,
)
from packages.contracts.progress import (
    SimulationProgress,
)
from packages.contracts.results import (
    SimulationResult,
)
from packages.contracts.worker_api import (
    WorkerExecuteRequest,
    WorkerJobStatusResponse,
    WorkerPrepareSessionRequest,
    WorkerSessionInfo,
)


class RemoteWorkerError(RuntimeError):
    pass


class RemoteSimulationExecutor:
    """
    SimulationExecutor implementation backed by
    an independent HTTP simulation worker.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 600.0,
    ) -> None:
        self._base_url = (
            base_url.rstrip("/")
        )

        self._timeout = (
            timeout_seconds
        )

    def _client(
        self,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                self._timeout
            ),
        )

    async def prepare_session(
        self,
        *,
        session_id: str,
        topology: str,
        topology_source: str,
        load_multiplier: float,
    ) -> ExecutorSessionInfo:
        # topology_source belongs to the API filesystem
        # and must not cross process boundaries.
        _ = topology_source

        request = (
            WorkerPrepareSessionRequest(
                session_id=session_id,
                topology=topology,
                load_multiplier=(
                    load_multiplier
                ),
            )
        )

        async with self._client() as client:
            response = await client.post(
                "/internal/sessions",
                json=request.model_dump(
                    mode="json"
                ),
            )

            response.raise_for_status()

            info = (
                WorkerSessionInfo
                .model_validate(
                    response.json()
                )
            )

            return info.to_executor_info()

    async def submit(
        self,
        job: SimulationJob,
        progress_handler: (
            ProgressHandler | None
        ) = None,
    ) -> SimulationResult:
        request = WorkerExecuteRequest(
            job=job
        )

        result: SimulationResult | None = (
            None
        )

        async with self._client() as client:
            async with client.stream(
                "POST",
                "/internal/jobs/execute",
                json=request.model_dump(
                    mode="json"
                ),
            ) as response:

                response.raise_for_status()

                async for line in (
                    response.aiter_lines()
                ):
                    if not line:
                        continue

                    event = json.loads(
                        line
                    )

                    event_type = (
                        event.get("type")
                    )

                    payload = (
                        event.get("payload")
                    )

                    if event_type == "progress":
                        progress = (
                            SimulationProgress
                            .model_validate(
                                payload
                            )
                        )

                        if (
                            progress_handler
                            is not None
                        ):
                            await progress_handler(
                                progress
                            )

                    elif event_type == "result":
                        result = (
                            SimulationResult
                            .model_validate(
                                payload
                            )
                        )

                    elif event_type == "error":
                        error = (
                            SimulationError
                            .model_validate(
                                payload
                            )
                        )

                        raise RemoteWorkerError(
                            f"{error.code}: "
                            f"{error.message}"
                        )

        if result is None:
            raise RemoteWorkerError(
                "Worker stream ended "
                "without SimulationResult"
            )

        return result

    async def status(
        self,
        job_id: str,
    ) -> JobStatus:
        async with self._client() as client:
            response = await client.get(
                f"/internal/jobs/"
                f"{job_id}/status"
            )

            response.raise_for_status()

            payload = (
                WorkerJobStatusResponse
                .model_validate(
                    response.json()
                )
            )

            return payload.status

    async def cancel(
        self,
        job_id: str,
    ) -> JobStatus:
        async with self._client() as client:
            response = await client.post(
                f"/internal/jobs/"
                f"{job_id}/cancel"
            )

            response.raise_for_status()

            payload = (
                WorkerJobStatusResponse
                .model_validate(
                    response.json()
                )
            )

            return payload.status

    async def session_info(
        self,
        session_id: str,
    ) -> ExecutorSessionInfo:
        async with self._client() as client:
            response = await client.get(
                f"/internal/sessions/"
                f"{session_id}"
            )

            response.raise_for_status()

            payload = (
                WorkerSessionInfo
                .model_validate(
                    response.json()
                )
            )

            return (
                payload.to_executor_info()
            )

    async def close_session(
        self,
        session_id: str,
    ) -> None:
        async with self._client() as client:
            response = await client.delete(
                f"/internal/sessions/"
                f"{session_id}"
            )

            response.raise_for_status()