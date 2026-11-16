from __future__ import annotations

import argparse
import asyncio
import json

from smoke_common import (
    add_common_args,
    open_authenticated_client,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke seguro IEEE8500 via API"
    )
    add_common_args(parser)
    return parser.parse_args()


async def main(
    args: argparse.Namespace,
) -> None:
    client, _ = await open_authenticated_client(
        base_url=args.base_url,
        username=args.username,
        ca_cert=args.ca_cert,
        insecure=args.insecure,
        timeout=600.0,
    )

    snapshot_id = None
    qsts_id = None

    try:
        metrics_before = await client.get(
            "/metrics"
        )
        metrics_before.raise_for_status()

        created = await client.post(
            "/simulations",
            json={"topology": "ieee8500"},
        )
        created.raise_for_status()

        snapshot_id = (
            created.json()["session_id"]
        )

        snapshot_response = (
            await client.post(
                f"/simulations/"
                f"{snapshot_id}/solve",
                json={
                    "simulation_type":
                        "snapshot"
                },
            )
        )
        snapshot_response.raise_for_status()

        snapshot = (
            snapshot_response.json()
        )

        detail = await client.get(
            f"/simulations/{snapshot_id}"
        )
        detail.raise_for_status()

        created = await client.post(
            "/simulations",
            json={"topology": "ieee8500"},
        )
        created.raise_for_status()

        qsts_id = (
            created.json()["session_id"]
        )

        short = await client.post(
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
        short.raise_for_status()

        short_results = await client.get(
            f"/simulations/"
            f"{qsts_id}/results"
        )
        short_results.raise_for_status()

        one_hour = await client.post(
            f"/simulations/{qsts_id}/solve",
            json={
                "simulation_type": "qsts",
                "qsts": {
                    "duration_hours": 1,
                    "step_minutes": 5,
                    "profile_source":
                        "synthetic_daily",
                },
            },
        )
        one_hour.raise_for_status()

        one_hour_results = (
            await client.get(
                f"/simulations/"
                f"{qsts_id}/results"
            )
        )
        one_hour_results.raise_for_status()

        metrics_after = await client.get(
            "/metrics"
        )
        metrics_after.raise_for_status()

        print(
            json.dumps(
                {
                    "snapshot": {
                        "converged":
                            snapshot[
                                "converged"
                            ],
                        "buses":
                            detail.json()[
                                "model_summary"
                            ]["num_buses"],
                        "nodes":
                            detail.json()[
                                "model_summary"
                            ]["num_nodes"],
                        "elapsed_ms":
                            snapshot[
                                "elapsed_ms"
                            ],
                    },
                    "qsts_short": {
                        "steps":
                            len(
                                short_results
                                .json()["steps"]
                            ),
                        "converged_steps":
                            short.json()[
                                "summary"
                            ][
                                "converged_steps"
                            ],
                    },
                    "qsts_one_hour": {
                        "steps":
                            len(
                                one_hour_results
                                .json()["steps"]
                            ),
                        "converged_steps":
                            one_hour.json()[
                                "summary"
                            ][
                                "converged_steps"
                            ],
                    },
                    "metrics_workers":
                        metrics_after
                        .json()
                        .get("workers", {}),
                },
                indent=2,
            )
        )

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

    print("IEEE8500 API SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
