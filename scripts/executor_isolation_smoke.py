from __future__ import annotations

from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


import asyncio
from uuid import uuid4


from packages.contracts.jobs import (
    SimulationJob,
)
from services.api_manager.execution.local_executor import (
    LocalSimulationExecutor,
)


async def main() -> None:
    executor = LocalSimulationExecutor()

    topology = "ieee123"


    session_a = str(uuid4())
    session_b = str(uuid4())

    info_a = await executor.prepare_session(
        session_id=session_a,
        topology=topology,
        load_multiplier=0.8,
    )

    info_b = await executor.prepare_session(
        session_id=session_b,
        topology=topology,
        load_multiplier=1.2,
    )

    assert (
        info_a.runtime_identity
        != info_b.runtime_identity
    )

    job_a = SimulationJob(
        job_id=str(uuid4()),
        session_id=session_a,
        topology=topology,
        simulation_type="snapshot",
        load_multiplier=0.8,
    )

    job_b = SimulationJob(
        job_id=str(uuid4()),
        session_id=session_b,
        topology=topology,
        simulation_type="snapshot",
        load_multiplier=1.2,
    )

    result_a, result_b = await asyncio.gather(
        executor.submit(job_a),
        executor.submit(job_b),
    )

    assert result_a.snapshot is not None
    assert result_b.snapshot is not None

    assert result_a.snapshot.converged
    assert result_b.snapshot.converged

    assert (
        result_a.snapshot.load_multiplier
        == 0.8
    )

    assert (
        result_b.snapshot.load_multiplier
        == 1.2
    )

    await executor.close_session(
        session_a
    )

    await executor.close_session(
        session_b
    )

    print(
        "Independent runtime identities:",
        info_a.runtime_identity,
        info_b.runtime_identity,
    )

    print(
        "EXECUTOR ISOLATION OK"
    )


if __name__ == "__main__":
    asyncio.run(main())