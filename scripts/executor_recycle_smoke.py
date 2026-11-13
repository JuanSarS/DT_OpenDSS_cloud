from __future__ import annotations

import asyncio
from uuid import uuid4
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


from packages.contracts.jobs import (
    SimulationJob,
)
from services.api_manager.execution.local_executor import (
    LocalSimulationExecutor,
)


async def main() -> None:
    executor = LocalSimulationExecutor(
        recycle_threshold=2
    )

    topology = "ieee123"

    session_id = str(uuid4())


    initial = await executor.prepare_session(
        session_id=session_id,
        topology=topology,
        load_multiplier=1.0,
    )

    initial_identity = (
        initial.runtime_identity
    )

    for _ in range(2):
        job = SimulationJob(
            job_id=str(uuid4()),
            session_id=session_id,
            topology=topology,
            simulation_type="snapshot",
            load_multiplier=1.0,
        )

        result = await executor.submit(
            job
        )

        assert result.snapshot is not None
        assert result.snapshot.converged

    final = await executor.session_info(
        session_id
    )

    assert final.task_count == 0

    assert (
        final.runtime_identity
        != initial_identity
    )

    print(
        "Old runtime:",
        initial_identity,
    )

    print(
        "New runtime:",
        final.runtime_identity,
    )

    print(
        "Task count after recycle:",
        final.task_count,
    )

    await executor.close_session(
        session_id
    )

    print(
        "EXECUTOR RECYCLE OK"
    )


if __name__ == "__main__":
    asyncio.run(main())