from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import websockets

from scripts.smoke_common import open_authenticated_client, websocket_base, websocket_ssl_context


async def main_async(args: argparse.Namespace) -> None:
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    client, token = await open_authenticated_client(
        base_url=args.base_url,
        username=args.username,
        ca_cert=args.ca_cert,
        insecure=args.insecure,
        timeout=900.0,
    )
    session_id = None
    events: list[dict] = []
    try:
        created = await client.post("/simulations", json={"topology": args.topology})
        created.raise_for_status()
        session_id = created.json()["session_id"]
        detail = await client.get(f"/simulations/{session_id}")
        detail.raise_for_status()
        metadata = {
            "session_id": session_id,
            "worker_identity": detail.json().get("worker_identity"),
            "topology": args.topology,
        }
        (output / "resilience_session.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        ws_url = f"{websocket_base(args.base_url)}/ws/simulations/{session_id}"
        async with websockets.connect(
            ws_url,
            ssl=websocket_ssl_context(args.base_url, args.ca_cert, args.insecure),
            subprotocols=["opendss.jwt", token],
            max_size=16 * 1024 * 1024,
        ) as websocket:
            events.append(json.loads(await websocket.recv()))
            solve_task = asyncio.create_task(
                client.post(
                    f"/simulations/{session_id}/solve",
                    json={
                        "simulation_type": "qsts",
                        "qsts": {
                            "duration_hours": args.duration_hours,
                            "step_minutes": args.step_minutes,
                            "profile_source": "synthetic_daily",
                        },
                    },
                )
            )
            first_progress_seen = False
            completed = False
            while not completed:
                event = json.loads(await asyncio.wait_for(websocket.recv(), timeout=900))
                events.append(event)
                if event.get("type") == "qsts_progress" and not first_progress_seen:
                    first_progress_seen = True
                    (output / "ready_to_kill.flag").write_text("ready\n", encoding="utf-8")
                completed = event.get("type") == "completed"
            response = await solve_task
            response.raise_for_status()

        progress = [event.get("step") for event in events if event.get("type") == "qsts_progress"]
        restarted = any(b < a for a, b in zip(progress, progress[1:]))
        result = {
            "passed": completed and response.status_code == 200,
            "session_id": session_id,
            "initial_worker": metadata["worker_identity"],
            "progress_steps": progress,
            "observed_restart": restarted,
            "event_types": [event.get("type") for event in events],
        }
        (output / "ws_events.jsonl").write_text(
            "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
            encoding="utf-8",
        )
        (output / "resilience_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if session_id:
            await client.delete(f"/simulations/{session_id}")
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--ca-cert", default="")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--topology", default="ieee123")
    parser.add_argument("--duration-hours", type=float, default=24.0)
    parser.add_argument("--step-minutes", type=float, default=1.0)
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
