from __future__ import annotations

import asyncio
from uuid import uuid4
from pathlib import Path

import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from app.adapters.opendss.topology_catalog import (
    resolve_topology,
)
from packages.contracts.jobs import (
    JobStatus,
    SimulationJob,
)
from packages.contracts.models import QSTSConfig
from services.api_manager.execution.local_executor import (
    LocalSimulationExecutor,
)


async def main() -> None:
    executor = LocalSimulationExecutor(
        recycle_threshold=1000
    )

    session_id = str(uuid4())

    topology = "ieee123"
    topology_path = resolve_topology(
        topology
    )

    info = await executor.prepare_session(
        session_id=session_id,
        topology=topology,
        topology_source=str(
            topology_path
        ),
        load_multiplier=1.0,
    )

    print(
        "Prepared:",
        info.session_id,
        info.runtime_identity,
    )

    snapshot_job = SimulationJob(
        job_id=str(uuid4()),
        session_id=session_id,
        topology=topology,
        simulation_type="snapshot",
        load_multiplier=1.0,
    )

    snapshot_result = await executor.submit(
        snapshot_job
    )

    assert (
        snapshot_result.status
        == JobStatus.COMPLETED
    )

    assert (
        snapshot_result.snapshot
        is not None
    )

    assert (
        snapshot_result.snapshot.converged
        is True
    )

    assert (
        await executor.status(
            snapshot_job.job_id
        )
        == JobStatus.COMPLETED
    )
    cancel_status = await executor.cancel(
    snapshot_job.job_id
    )

    assert (
        cancel_status
        == JobStatus.COMPLETED
    )
    print("Snapshot executor OK")

    progress_steps: list[int] = []

    async def on_progress(
        progress,
    ) -> None:
        if progress.step is not None:
            progress_steps.append(
                progress.step
            )

            print(
                f"[{progress.step}/"
                f"{progress.total_steps}] "
                f"{progress.progress_pct:.1f}%"
            )

    qsts_job = SimulationJob(
        job_id=str(uuid4()),
        session_id=session_id,
        topology=topology,
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

    qsts_result = await executor.submit(
        qsts_job,
        progress_handler=on_progress,
    )

    assert (
        qsts_result.status
        == JobStatus.COMPLETED
    )

    assert qsts_result.qsts is not None
    
    assert (
        qsts_result.qsts.total_steps
        == 3
    )

    assert progress_steps == [
        1,
        2,
        3,
    ]

    assert (
        await executor.status(
            qsts_job.job_id
        )
        == JobStatus.COMPLETED
    )
    cancel_status = await executor.cancel(
            qsts_job.job_id
        )
    
    assert (
        cancel_status
        == JobStatus.COMPLETED
    )
    print("QSTS executor OK")

    final_info = (
        await executor.session_info(
            session_id
        )
    )

    assert final_info.task_count == 2

    print(
        "Task count:",
        final_info.task_count,
    )

    await executor.close_session(
        session_id
    )

    print("EXECUTOR SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())