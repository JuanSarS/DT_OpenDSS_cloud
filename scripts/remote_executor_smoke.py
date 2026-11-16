from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import asyncio
from uuid import uuid4

from packages.contracts.jobs import (
    JobStatus,
    SimulationJob,
)
from packages.contracts.models import (
    QSTSConfig,
)
from services.api_manager.execution.remote_executor import (
    RemoteSimulationExecutor,
)


async def main() -> None:
    executor = RemoteSimulationExecutor(
        base_url="http://127.0.0.1:8100"
    )

    session_id = str(uuid4())

    info = await executor.prepare_session(
        session_id=session_id,
        topology="ieee123",
        load_multiplier=1.0,
    )

    print(
        "Remote session:",
        info.runtime_identity,
    )

    snapshot_job = SimulationJob(
        job_id=str(uuid4()),
        session_id=session_id,
        topology="ieee123",
        simulation_type="snapshot",
        load_multiplier=1.0,
    )

    result = await executor.submit(
        snapshot_job
    )

    assert (
        result.status
        == JobStatus.COMPLETED
    )

    assert result.snapshot is not None
    assert result.snapshot.converged

    print("Remote Snapshot OK")

    steps = []

    async def progress_handler(
        progress,
    ) -> None:
        steps.append(
            progress.step
        )

    qsts_job = SimulationJob(
        job_id=str(uuid4()),
        session_id=session_id,
        topology="ieee123",
        simulation_type="qsts",
        qsts=QSTSConfig(
            duration_hours=0.25,
            step_minutes=5,
            profile_source="values",
            load_multipliers=[
                0.8,
                1.0,
                1.2,
            ],
        ),
    )

    result = await executor.submit(
        qsts_job,
        progress_handler=progress_handler,
    )

    assert result.qsts is not None
    assert steps == [1, 2, 3]

    assert (
        await executor.status(
            qsts_job.job_id
        )
        == JobStatus.COMPLETED
    )

    print("Remote QSTS OK")

    await executor.close_session(
        session_id
    )

    print(
        "REMOTE EXECUTOR SMOKE OK"
    )


if __name__ == "__main__":
    asyncio.run(main())