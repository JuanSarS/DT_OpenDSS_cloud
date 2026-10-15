from __future__ import annotations

import asyncio
import json

import httpx


async def main() -> None:
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=300.0
    ) as client:
        metrics_before = (await client.get("/metrics")).json()
        snapshot_session = await client.post(
            "/simulations", json={"topology": "ieee8500"}
        )
        snapshot_session.raise_for_status()
        snapshot_data = await client.post(
            f"/simulations/{snapshot_session.json()['session_id']}/solve",
            json={"simulation_type": "snapshot"},
        )
        snapshot_data.raise_for_status()
        snapshot = snapshot_data.json()
        snapshot_results = await client.get(
            f"/simulations/{snapshot['session_id']}/results"
        )
        snapshot_results.raise_for_status()
        snapshot_id = snapshot["session_id"]
        snapshot_detail = await client.get(f"/simulations/{snapshot_id}")
        snapshot_detail.raise_for_status()

        qsts_session = await client.post(
            "/simulations", json={"topology": "ieee8500"}
        )
        qsts_session.raise_for_status()
        qsts_id = qsts_session.json()["session_id"]
        short = await client.post(
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
        short.raise_for_status()
        short_results = (await client.get(f"/simulations/{qsts_id}/results")).json()

        one_hour = await client.post(
            f"/simulations/{qsts_id}/solve",
            json={
                "simulation_type": "qsts",
                "qsts": {
                    "duration_hours": 1,
                    "step_minutes": 5,
                    "profile_source": "synthetic_daily",
                },
            },
        )
        one_hour.raise_for_status()
        one_hour_results = (await client.get(f"/simulations/{qsts_id}/results")).json()
        metrics_after = (await client.get("/metrics")).json()
        await client.delete(f"/simulations/{snapshot_id}")
        await client.delete(f"/simulations/{qsts_id}")

    print(
        json.dumps(
            {
                "snapshot": {
                    "converged": snapshot["converged"],
                    "buses": snapshot_detail.json()["model_summary"]["num_buses"],
                    "nodes": snapshot_detail.json()["model_summary"]["num_nodes"],
                    "elapsed_ms": snapshot["elapsed_ms"],
                    "total_power_kw": snapshot["total_power_kw"],
                    "total_power_kvar": snapshot["total_power_kvar"],
                },
                "qsts_short": {
                    "steps": len(short_results["steps"]),
                    "converged_steps": short.json()["summary"]["converged_steps"],
                    "load_multipliers": [
                        step["load_multiplier"] for step in short_results["steps"]
                    ],
                },
                "qsts_one_hour": {
                    "steps": len(one_hour_results["steps"]),
                    "converged_steps": one_hour.json()["summary"]["converged_steps"],
                    "failed_steps": one_hour.json()["summary"]["failed_steps"],
                    "elapsed_ms": one_hour.json()["summary"]["elapsed_ms"],
                    "min_voltage_pu": min(
                        step["min_voltage_pu"] for step in one_hour_results["steps"]
                    ),
                    "max_voltage_pu": max(
                        step["max_voltage_pu"] for step in one_hour_results["steps"]
                    ),
                },
                "metrics": {
                    "before": metrics_before["process"],
                    "after": metrics_after["process"],
                },
            },
            indent=2,
        )
    )
    print("IEEE8500 REST SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
