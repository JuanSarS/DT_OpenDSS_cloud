from __future__ import annotations

import argparse
import asyncio
import json

import httpx
import websockets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test WebSocket de QSTS.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    return parser.parse_args()


async def run(base_url: str) -> None:
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    async with httpx.AsyncClient(base_url=base_url, timeout=180.0) as client:
        health = await client.get("/health")
        health.raise_for_status()
        created = await client.post("/simulations", json={"topology": "ieee123"})
        created.raise_for_status()
        session_id = created.json()["session_id"]

        try:
            async with websockets.connect(
                f"{ws_url}/ws/simulations/{session_id}"
            ) as websocket:
                snapshot = await websocket.recv()
                assert '"type": "snapshot"' in snapshot or '"type":"snapshot"' in snapshot

                solve_task = asyncio.create_task(
                    client.post(
                        f"/simulations/{session_id}/solve",
                        json={
                            "simulation_type": "qsts",
                            "qsts": {
                                "duration_hours": 0.25,
                                "step_minutes": 5,
                                "profile_source": "values",
                                "load_multipliers": [0.8, 1.0, 1.2],
                            },
                        },
                    )
                )
                progress_steps: list[int] = []
                result_received = False
                completed = False
                while not completed:
                    message = await websocket.recv()
                    event = json.loads(message)
                    if event["type"] == "qsts_progress":
                        progress_steps.append(event["step"])
                        print(
                            f"[{event['step']}/3] "
                            f"{event['progress_pct']:.1f}% "
                            f"LoadMult={event['load_multiplier']}"
                        )
                    elif event["type"] == "result":
                        result_received = True
                        print("Result received")
                    elif event["type"] == "completed":
                        completed = True
                        print("Completed")

                response = await solve_task
                response.raise_for_status()
                results = await client.get(f"/simulations/{session_id}/results")
                results.raise_for_status()
                assert progress_steps == [1, 2, 3]
                assert result_received
                assert len(results.json()["steps"]) == 3
                print(f"REST steps: {len(results.json()['steps'])}")
        finally:
            await client.delete(f"/simulations/{session_id}")

    print("QSTS WS SMOKE OK")


if __name__ == "__main__":
    asyncio.run(run(parse_args().base_url))
