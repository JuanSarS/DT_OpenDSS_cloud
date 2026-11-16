from __future__ import annotations

import argparse
import asyncio
import json

import websockets

from smoke_common import add_common_args, open_authenticated_client, websocket_base, websocket_ssl_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke integral Snapshot + WebSocket seguro")
    add_common_args(parser)
    return parser.parse_args()


async def receive_json(socket, timeout: float = 20.0) -> dict:
    return json.loads(await asyncio.wait_for(socket.recv(), timeout=timeout))


async def main(args: argparse.Namespace) -> None:
    client, token = await open_authenticated_client(
        base_url=args.base_url,
        username=args.username,
        ca_cert=args.ca_cert,
        insecure=args.insecure,
        timeout=180.0,
    )
    session_id: str | None = None
    try:
        health = await client.get("/health")
        health.raise_for_status()
        print("[OK] health")

        me = await client.get("/auth/me")
        me.raise_for_status()
        print(f"[OK] auth -> {me.json()['username']} · {me.json()['role']}")

        models = await client.get("/models")
        models.raise_for_status()
        ids = {item["id"] for item in models.json()}
        assert {"ieee13", "ieee34", "ieee123", "ieee8500"} <= ids
        print("[OK] models")

        created = await client.post("/simulations", json={"topology": "ieee13"})
        created.raise_for_status()
        session_id = created.json()["session_id"]
        print(f"[OK] session {session_id}")

        ws_url = f"{websocket_base(args.base_url)}/ws/simulations/{session_id}"
        ws_ssl = websocket_ssl_context(args.base_url, args.ca_cert, args.insecure)
        async with websockets.connect(
            ws_url,
            ssl=ws_ssl,
            subprotocols=["opendss.jwt", token],
            max_size=16 * 1024 * 1024,
        ) as socket:
            snapshot = await receive_json(socket)
            assert snapshot.get("type") == "snapshot"
            print("[OK] websocket authenticated")

            solve_task = asyncio.create_task(
                client.post(
                    f"/simulations/{session_id}/solve",
                    json={"simulation_type": "snapshot", "load_multiplier": 1.0},
                )
            )
            event_types: list[str] = []
            for _ in range(12):
                event = await receive_json(socket)
                event_types.append(event.get("type", ""))
                if event.get("type") == "completed":
                    break
            solve = await solve_task
            solve.raise_for_status()
            assert solve.json()["converged"] is True
            assert "result" in event_types and "completed" in event_types
            print("[OK] snapshot + WS events")

        results = await client.get(f"/simulations/{session_id}/results")
        results.raise_for_status()
        print("[OK] results")
    finally:
        if session_id:
            response = await client.delete(f"/simulations/{session_id}")
            if response.status_code not in {204, 404}:
                response.raise_for_status()
        await client.aclose()

    print("SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
