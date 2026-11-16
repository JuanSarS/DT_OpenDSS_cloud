from __future__ import annotations

import argparse
import asyncio

from smoke_common import (
    add_common_args,
    open_authenticated_client,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke REST seguro de Snapshot y QSTS"
    )
    add_common_args(parser)
    return parser.parse_args()


async def run(
    args: argparse.Namespace,
) -> None:
    client, _ = await open_authenticated_client(
        base_url=args.base_url,
        username=args.username,
        ca_cert=args.ca_cert,
        insecure=args.insecure,
        timeout=300.0,
    )

    snapshot_id = None
    qsts_id = None

    try:
        health = await client.get(
            "/health"
        )
        health.raise_for_status()

        created = await client.post(
            "/simulations",
            json={"topology": "ieee123"},
        )
        created.raise_for_status()

        snapshot_id = (
            created.json()["session_id"]
        )

        snapshot = await client.post(
            f"/simulations/"
            f"{snapshot_id}/solve",
            json={
                "simulation_type":
                    "snapshot"
            },
        )
        snapshot.raise_for_status()

        assert (
            snapshot.json()["converged"]
            is True
        )

        created = await client.post(
            "/simulations",
            json={"topology": "ieee123"},
        )
        created.raise_for_status()

        qsts_id = (
            created.json()["session_id"]
        )

        qsts = await client.post(
            f"/simulations/{qsts_id}/solve",
            json={
                "simulation_type": "qsts",
                "qsts": {
                    "duration_hours": 24,
                    "step_minutes": 5,
                    "profile_source":
                        "synthetic_daily",
                },
            },
        )
        qsts.raise_for_status()

        summary = qsts.json()["summary"]

        assert (
            summary["total_steps"]
            == 288
        )

        assert (
            summary["converged_steps"]
            == 288
        )

        values = await client.post(
            f"/simulations/{qsts_id}/solve",
            json={
                "simulation_type": "qsts",
                "qsts": {
                    "duration_hours":
                        0.25,
                    "step_minutes": 5,
                    "profile_source":
                        "values",
                    "load_multipliers":
                        [0.8, 1.0, 1.2],
                },
            },
        )
        values.raise_for_status()

        results = await client.get(
            f"/simulations/"
            f"{qsts_id}/results"
        )
        results.raise_for_status()

        assert [
            step["load_multiplier"]
            for step
            in results.json()["steps"]
        ] == [0.8, 1.0, 1.2]

    finally:
        for session_id in (
            snapshot_id,
            qsts_id,
        ):
            if session_id:
                await client.delete(
                    f"/simulations/"
                    f"{session_id}"
                )

        await client.aclose()

    print("REST QSTS smoke OK")
    print("Snapshot: converged")
    print(
        "QSTS synthetic_daily: "
        "288/288 converged"
    )
    print(
        "QSTS values: "
        "[0.8, 1.0, 1.2]"
    )


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
