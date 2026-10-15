from __future__ import annotations

import argparse
import asyncio

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test REST de Snapshot y QSTS.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    return parser.parse_args()


async def run(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=180.0) as client:
        health = await client.get("/health")
        health.raise_for_status()

        snapshot_session = await client.post(
            "/simulations",
            json={"topology": "ieee123"},
        )
        snapshot_session.raise_for_status()
        snapshot_id = snapshot_session.json()["session_id"]

        qsts_id: str | None = None
        try:
            snapshot = await client.post(f"/simulations/{snapshot_id}/solve")
            snapshot.raise_for_status()
            assert snapshot.json()["converged"] is True

            qsts_session = await client.post(
                "/simulations",
                json={"topology": "ieee123"},
            )
            qsts_session.raise_for_status()
            qsts_id = qsts_session.json()["session_id"]

            qsts = await client.post(
                f"/simulations/{qsts_id}/solve",
                json={
                    "simulation_type": "qsts",
                    "qsts": {
                        "duration_hours": 24,
                        "step_minutes": 5,
                        "profile_source": "synthetic_daily",
                    },
                },
            )
            qsts.raise_for_status()
            summary = qsts.json()["summary"]
            assert summary["total_steps"] == 288
            assert summary["converged_steps"] == 288

            detail = await client.get(f"/simulations/{qsts_id}")
            detail.raise_for_status()
            results = await client.get(f"/simulations/{qsts_id}/results")
            results.raise_for_status()
            result_data = results.json()
            assert len(result_data["steps"]) == 288

            values = await client.post(
                f"/simulations/{qsts_id}/solve",
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
            values.raise_for_status()
            values_result = await client.get(f"/simulations/{qsts_id}/results")
            values_result.raise_for_status()
            assert [
                step["load_multiplier"] for step in values_result.json()["steps"]
            ] == [0.8, 1.0, 1.2]
        finally:
            await client.delete(f"/simulations/{snapshot_id}")
            if qsts_id is not None:
                await client.delete(f"/simulations/{qsts_id}")

    print("REST QSTS smoke OK")
    print("Snapshot: converged")
    print("QSTS synthetic_daily: 288/288 converged")
    print("QSTS values: [0.8, 1.0, 1.2]")


if __name__ == "__main__":
    asyncio.run(run(parse_args().base_url))
