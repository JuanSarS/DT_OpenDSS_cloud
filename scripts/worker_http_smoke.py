from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import asyncio
import json
from uuid import uuid4

import httpx

from packages.contracts.jobs import (
    SimulationJob,
)
from packages.contracts.models import (
    QSTSConfig,
)


BASE_URL = "http://127.0.0.1:8100"


async def main() -> None:
    session_id = str(uuid4())

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=300.0,
    ) as client:

        health = await client.get(
            "/internal/health"
        )

        health.raise_for_status()

        print(
            "Health:",
            health.json()
        )

        created = await client.post(
            "/internal/sessions",
            json={
                "session_id": session_id,
                "topology": "ieee123",
                "load_multiplier": 1.0,
            },
        )

        created.raise_for_status()

        print(
            "Session prepared"
        )

        snapshot_job = SimulationJob(
            job_id=str(uuid4()),
            session_id=session_id,
            topology="ieee123",
            simulation_type="snapshot",
            load_multiplier=1.0,
        )

        async with client.stream(
            "POST",
            "/internal/jobs/execute",
            json={
                "job":
                    snapshot_job.model_dump(
                        mode="json"
                    )
            },
        ) as response:

            response.raise_for_status()

            snapshot_result = False

            async for line in (
                response.aiter_lines()
            ):
                if not line:
                    continue

                event = json.loads(line)

                if event["type"] == "result":
                    snapshot_result = True

        assert snapshot_result

        print(
            "Snapshot worker OK"
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

        steps = []
        qsts_result = False

        async with client.stream(
            "POST",
            "/internal/jobs/execute",
            json={
                "job":
                    qsts_job.model_dump(
                        mode="json"
                    )
            },
        ) as response:

            response.raise_for_status()

            async for line in (
                response.aiter_lines()
            ):
                if not line:
                    continue

                event = json.loads(line)

                if event["type"] == "progress":
                    step = (
                        event["payload"]["step"]
                    )

                    steps.append(step)

                    print(
                        f"Progress: {step}/3"
                    )

                elif event["type"] == "result":
                    qsts_result = True

        assert steps == [1, 2, 3]
        assert qsts_result

        print("QSTS worker OK")

        deleted = await client.delete(
            f"/internal/sessions/"
            f"{session_id}"
        )

        deleted.raise_for_status()

    print(
        "WORKER HTTP SMOKE OK"
    )


if __name__ == "__main__":
    asyncio.run(main())