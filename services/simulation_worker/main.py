from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from packages.contracts.errors import (
    SimulationError,
    SimulationErrorCode,
)
from packages.contracts.jobs import JobStatus
from packages.contracts.worker_api import (
    WorkerExecuteRequest,
    WorkerHealthResponse,
    WorkerJobStatusResponse,
    WorkerPrepareSessionRequest,
    WorkerSessionInfo,
)
from services.simulation_worker.executor import (
    LocalSimulationExecutor,
)
from services.simulation_worker.settings import (
    worker_settings,
)
from services.simulation_worker.topology_resolver import (
    resolve_worker_topology,
)


app = FastAPI(
    title="OpenDSS Simulation Worker",
    version="1.0.0",
)


executor = LocalSimulationExecutor(
    recycle_threshold=(
        worker_settings.recycle_threshold
    )
)


@app.get(
    "/internal/health",
    response_model=WorkerHealthResponse,
)
async def health() -> WorkerHealthResponse:
    return WorkerHealthResponse(
        pid=os.getpid()
    )


@app.post(
    "/internal/sessions",
    response_model=WorkerSessionInfo,
    status_code=201,
)
async def prepare_session(
    request: WorkerPrepareSessionRequest,
) -> WorkerSessionInfo:
    try:
        topology_path = (
            resolve_worker_topology(
                request.topology
            )
        )

        info = await executor.prepare_session(
            session_id=request.session_id,
            topology=request.topology,
            topology_source=str(
                topology_path
            ),
            load_multiplier=(
                request.load_multiplier
            ),
        )

        return (
            WorkerSessionInfo
            .from_executor_info(info)
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@app.get(
    "/internal/sessions/{session_id}",
    response_model=WorkerSessionInfo,
)
async def session_info(
    session_id: str,
) -> WorkerSessionInfo:
    try:
        info = await executor.session_info(
            session_id
        )

        return (
            WorkerSessionInfo
            .from_executor_info(info)
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.delete(
    "/internal/sessions/{session_id}",
    status_code=204,
)
async def close_session(
    session_id: str,
) -> None:
    await executor.close_session(
        session_id
    )


@app.get(
    "/internal/jobs/{job_id}/status",
    response_model=WorkerJobStatusResponse,
)
async def job_status(
    job_id: str,
) -> WorkerJobStatusResponse:
    try:
        status = await executor.status(
            job_id
        )

        return WorkerJobStatusResponse(
            job_id=job_id,
            status=status,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.post(
    "/internal/jobs/{job_id}/cancel",
    response_model=WorkerJobStatusResponse,
)
async def cancel_job(
    job_id: str,
) -> WorkerJobStatusResponse:
    try:
        status = await executor.cancel(
            job_id
        )

        return WorkerJobStatusResponse(
            job_id=job_id,
            status=status,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.post(
    "/internal/jobs/execute",
)
async def execute_job(
    request: WorkerExecuteRequest,
) -> StreamingResponse:

    job = request.job

    async def event_stream():
        queue: asyncio.Queue = (
            asyncio.Queue()
        )

        async def on_progress(
            progress,
        ) -> None:
            await queue.put(
                (
                    "progress",
                    progress,
                )
            )

        task = asyncio.create_task(
            executor.submit(
                job,
                progress_handler=on_progress,
            )
        )

        while (
            not task.done()
            or not queue.empty()
        ):
            try:
                event_type, payload = (
                    await asyncio.wait_for(
                        queue.get(),
                        timeout=0.05,
                    )
                )

                event = {
                    "type": event_type,
                    "payload":
                        payload.model_dump(
                            mode="json"
                        ),
                }

                yield (
                    json.dumps(event)
                    + "\n"
                )

            except asyncio.TimeoutError:
                pass

        try:
            result = await task

            event = {
                "type": "result",
                "payload":
                    result.model_dump(
                        mode="json"
                    ),
            }

            yield json.dumps(event) + "\n"

        except Exception as exc:
            error = SimulationError(
                job_id=job.job_id,
                session_id=job.session_id,
                code=(
                    SimulationErrorCode
                    .WORKER_ERROR
                ),
                message=str(exc),
                retryable=False,
                attempt=job.attempt,
            )

            event = {
                "type": "error",
                "payload":
                    error.model_dump(
                        mode="json"
                    ),
            }

            yield json.dumps(event) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
    )