from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import ssl
from pathlib import Path

import httpx
import websockets

from tools.evidence.common import ensure_run_dir, write_json


def password_for(label: str, env_name: str) -> str:
    value = os.getenv(env_name)
    if value:
        return value
    return getpass.getpass(f"Password de {label}: ")


async def login(base_url: str, username: str, password: str) -> tuple[httpx.AsyncClient, str]:
    client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=300.0)
    response = await client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client, token


async def user_qsts_flow(
    base_url: str,
    username: str,
    password: str,
    topology: str,
) -> dict:
    client, token = await login(base_url, username, password)
    session_id = None
    events: list[dict] = []
    try:
        created = await client.post("/simulations", json={"topology": topology})
        created.raise_for_status()
        session_id = created.json()["session_id"]
        detail = await client.get(f"/simulations/{session_id}")
        detail.raise_for_status()
        ws_url = (
            base_url.rstrip("/")
            .replace("https://", "wss://")
            .replace("http://", "ws://")
            + f"/ws/simulations/{session_id}"
        )
        async with websockets.connect(
            ws_url,
            ssl=ssl.create_default_context() if ws_url.startswith("wss://") else None,
            subprotocols=["opendss.jwt", token],
            max_size=16 * 1024 * 1024,
        ) as websocket:
            initial = json.loads(await websocket.recv())
            events.append(initial)
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
            completed = False
            while not completed:
                event = json.loads(await asyncio.wait_for(websocket.recv(), timeout=120))
                events.append(event)
                completed = event.get("type") == "completed"
            solve = await solve_task
            solve.raise_for_status()
        results = await client.get(f"/simulations/{session_id}/results")
        results.raise_for_status()
        return {
            "username": username,
            "session_id": session_id,
            "worker_identity": detail.json().get("worker_identity"),
            "topology": detail.json().get("topology"),
            "event_types": [event.get("type") for event in events],
            "progress_steps": [
                event.get("step") for event in events if event.get("type") == "qsts_progress"
            ],
            "result_steps": len(results.json().get("steps", [])),
            "status": "PASS",
        }
    finally:
        if session_id:
            await client.delete(f"/simulations/{session_id}")
        await client.aclose()


async def main_async(args: argparse.Namespace) -> None:
    run_dir = ensure_run_dir(args.output_root, "cloud_mvp")
    admin_password = password_for(args.admin, "OPENDSS_ADMIN_PASSWORD")
    user1_password = password_for(args.user1, "OPENDSS_USER1_PASSWORD")
    user2_password = password_for(args.user2, "OPENDSS_USER2_PASSWORD")

    admin, _ = await login(args.base_url, args.admin, admin_password)
    try:
        health = await admin.get("/health")
        health.raise_for_status()
        models = await admin.get("/models")
        models.raise_for_status()
        metrics_before = await admin.get("/metrics")
        metrics_before.raise_for_status()
        write_json(run_dir / "health.json", health.json())
        write_json(run_dir / "models.json", models.json())
        write_json(run_dir / "metrics_before.json", metrics_before.json())

        flows = await asyncio.gather(
            user_qsts_flow(args.base_url, args.user1, user1_password, "ieee123"),
            user_qsts_flow(args.base_url, args.user2, user2_password, "ieee8500"),
        )
        write_json(run_dir / "multiuser_flows.json", flows)

        metrics_after = await admin.get("/metrics")
        metrics_after.raise_for_status()
        write_json(run_dir / "metrics_after.json", metrics_after.json())

        passed = all(
            flow["status"] == "PASS"
            and flow["progress_steps"] == [1, 2, 3]
            and flow["result_steps"] == 3
            for flow in flows
        )
        summary = {
            "passed": passed,
            "base_url": args.base_url,
            "users": [args.user1, args.user2],
            "flows": flows,
            "models_available": [item["id"] for item in models.json()],
            "worker_metrics": metrics_after.json().get("sessions", {}),
        }
        write_json(run_dir / "summary.json", summary)
        (run_dir / "REPORT.md").write_text(
            "# Evidencia Entregable 2 — MVP cloud\n\n"
            f"Resultado: **{'PASS' if passed else 'FAIL'}**\n\n"
            f"URL probada: `{args.base_url}`\n\n"
            "Se ejecutaron dos usuarios autenticados de forma concurrente, con REST y WSS, "
            "sobre IEEE123 e IEEE8500. Los archivos JSON de esta carpeta contienen los "
            "resultados y métricas observadas.\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2))
        print(f"Evidence: {run_dir}")
        raise SystemExit(0 if passed else 2)
    finally:
        await admin.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin", default="admin")
    parser.add_argument("--user1", default="user1")
    parser.add_argument("--user2", default="user2")
    parser.add_argument("--output-root", default="docs/evidence/deliverable_2")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
