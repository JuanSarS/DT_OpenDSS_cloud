from __future__ import annotations

import argparse
import asyncio
import json

import websockets

from smoke_common import (
    add_common_args,
    open_authenticated_client,
    websocket_base,
    websocket_ssl_context,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke WSS seguro de QSTS"
    )
    add_common_args(parser)
    return parser.parse_args()


async def run(
    args: argparse.Namespace,
) -> None:
    client, token = await open_authenticated_client(
        base_url=args.base_url,
        username=args.username,
        ca_cert=args.ca_cert,
        insecure=args.insecure,
        timeout=180.0,
    )

    session_id = None

    try:
        created = await client.post(
            "/simulations",
            json={"topology": "ieee123"},
        )
        created.raise_for_status()

        session_id = (
            created.json()["session_id"]
        )

        ws_url = (
            f"{websocket_base(args.base_url)}"
            f"/ws/simulations/{session_id}"
        )

        async with websockets.connect(
            ws_url,
            ssl=websocket_ssl_context(
                args.base_url,
                args.ca_cert,
                args.insecure,
            ),
            subprotocols=[
                "opendss.jwt",
                token,
            ],
            max_size=16 * 1024 * 1024,
        ) as websocket:
            snapshot = json.loads(
                await websocket.recv()
            )

            assert (
                snapshot["type"]
                == "snapshot"
            )

            solve_task = (
                asyncio.create_task(
                    client.post(
                        f"/simulations/"
                        f"{session_id}/solve",
                        json={
                            "simulation_type":
                                "qsts",
                            "qsts": {
                                "duration_hours":
                                    0.25,
                                "step_minutes":
                                    5,
                                "profile_source":
                                    "values",
                                "load_multipliers":
                                    [
                                        0.8,
                                        1.0,
                                        1.2,
                                    ],
                            },
                        },
                    )
                )
            )

            steps: list[int] = []
            result_received = False
            completed = False

            while not completed:
                event = json.loads(
                    await asyncio.wait_for(
                        websocket.recv(),
                        timeout=30,
                    )
                )

                if (
                    event["type"]
                    == "qsts_progress"
                ):
                    steps.append(
                        event["step"]
                    )

                    print(
                        f"[{event['step']}/3] "
                        f"{event['progress_pct']:.1f}%"
                    )

                elif (
                    event["type"]
                    == "result"
                ):
                    result_received = True

                elif (
                    event["type"]
                    == "completed"
                ):
                    completed = True

            response = await solve_task
            response.raise_for_status()

            assert steps == [1, 2, 3]
            assert result_received

        results = await client.get(
            f"/simulations/"
            f"{session_id}/results"
        )
        results.raise_for_status()

        assert (
            len(results.json()["steps"])
            == 3
        )

    finally:
        if session_id:
            await client.delete(
                f"/simulations/"
                f"{session_id}"
            )

        await client.aclose()

    print("QSTS WSS SMOKE OK")


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
