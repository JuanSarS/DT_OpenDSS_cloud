from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import websockets

from smoke_common import (
    add_common_args,
    open_authenticated_client,
    websocket_base,
    websocket_ssl_context,
)


def percentile(values: list[float], level: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * level
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def statistics(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "mean": 0, "min": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0}
    return {
        "count": len(values),
        "mean": round(mean(values), 3),
        "min": round(min(values), 3),
        "p50": round(percentile(values, 0.50), 3),
        "p95": round(percentile(values, 0.95), 3),
        "p99": round(percentile(values, 0.99), 3),
        "max": round(max(values), 3),
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Campaña reproducible REST/WebSocket autenticada.")
    add_common_args(parser)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--model", default="ieee123")
    parser.add_argument("--simulation", choices=("snapshot", "qsts"), default="qsts")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--duration-hours", type=float, default=24.0)
    parser.add_argument("--step-minutes", type=float, default=5.0)
    parser.add_argument("--profile", default="synthetic_daily")
    parser.add_argument("--output-root", default="docs/evidence/performance")
    return parser.parse_args()


async def campaign(args: argparse.Namespace) -> None:
    if args.iterations < 1:
        raise ValueError("--iterations debe ser mayor que cero")
    base_url = args.base_url.rstrip("/")
    ws_base_url = websocket_base(base_url)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}_{args.environment}_{args.model}_{args.simulation}"
    evidence_dir = Path(args.output_root) / run_id
    evidence_dir.mkdir(parents=True, exist_ok=False)
    config = {
        "timestamp": timestamp,
        "run_id": run_id,
        "environment": args.environment,
        "base_url": base_url,
        "model": args.model,
        "simulation": args.simulation,
        "iterations": args.iterations,
        "duration_hours": args.duration_hours,
        "step_minutes": args.step_minutes,
        "profile": args.profile,
        "username": args.username,
    }
    (evidence_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    client, token = await open_authenticated_client(
        base_url=base_url,
        username=args.username,
        ca_cert=args.ca_cert,
        insecure=args.insecure,
        timeout=300.0,
    )
    try:
        metrics_before = (await client.get("/metrics")).json()
        (evidence_dir / "metrics_before.json").write_text(
            json.dumps(metrics_before, indent=2), encoding="utf-8"
        )
        rows: list[dict] = []
        for iteration in range(1, args.iterations + 1):
            row: dict = {"iteration": iteration, "status": "ok", "errors": 0}
            session_id: str | None = None
            try:
                started = time.perf_counter()
                health = await client.get("/health")
                row["health_ms"] = (time.perf_counter() - started) * 1000
                health.raise_for_status()

                started = time.perf_counter()
                created = await client.post("/simulations", json={"topology": args.model})
                row["create_ms"] = (time.perf_counter() - started) * 1000
                created.raise_for_status()
                session_id = created.json()["session_id"]

                ws_started = time.perf_counter()
                async with websockets.connect(
                    f"{ws_base_url}/ws/simulations/{session_id}",
                    ssl=websocket_ssl_context(base_url, args.ca_cert, args.insecure),
                    subprotocols=["opendss.jwt", token],
                    max_size=16 * 1024 * 1024,
                ) as websocket:
                    await websocket.recv()
                    row["ws_connect_ms"] = (time.perf_counter() - ws_started) * 1000
                    payload: dict = {"simulation_type": args.simulation}
                    if args.simulation == "qsts":
                        payload["qsts"] = {
                            "duration_hours": args.duration_hours,
                            "step_minutes": args.step_minutes,
                            "profile_source": args.profile,
                        }
                    solve_started = time.perf_counter()
                    solve_task = asyncio.create_task(
                        client.post(f"/simulations/{session_id}/solve", json=payload)
                    )
                    first_progress = None
                    result_time = None
                    completed_time = None
                    while completed_time is None:
                        event = json.loads(await websocket.recv())
                        now = time.perf_counter()
                        if event["type"] == "qsts_progress" and first_progress is None:
                            first_progress = now
                        elif event["type"] == "result" and result_time is None:
                            result_time = now
                            if args.simulation == "qsts":
                                row["engine_elapsed_ms"] = event["summary"].get("elapsed_ms")
                                row["solve_p50_ms"] = event["summary"].get("solve_p50_ms")
                                row["solve_p95_ms"] = event["summary"].get("solve_p95_ms")
                                row["rss_start_mb"] = event["summary"].get("rss_start_mb")
                                row["rss_peak_mb"] = event["summary"].get("rss_peak_mb")
                                row["total_steps"] = event["summary"].get("total_steps")
                                row["converged_steps"] = event["summary"].get("converged_steps")
                        elif event["type"] == "completed":
                            completed_time = now
                    solve_response = await solve_task
                    row["solve_http_ms"] = (time.perf_counter() - solve_started) * 1000
                    solve_response.raise_for_status()
                    row["ws_first_progress_ms"] = (
                        (first_progress - solve_started) * 1000 if first_progress else None
                    )
                    row["ws_result_ms"] = (
                        (result_time - solve_started) * 1000 if result_time else None
                    )
                    row["ws_completed_ms"] = (
                        (completed_time - solve_started) * 1000 if completed_time else None
                    )

                started = time.perf_counter()
                results = await client.get(f"/simulations/{session_id}/results")
                row["get_results_ms"] = (time.perf_counter() - started) * 1000
                results.raise_for_status()
            except Exception as exc:
                row["status"] = "error"
                row["errors"] = 1
                row["error"] = str(exc)
            finally:
                if session_id is not None:
                    started = time.perf_counter()
                    deleted = await client.delete(f"/simulations/{session_id}")
                    row["delete_ms"] = (time.perf_counter() - started) * 1000
                    if deleted.status_code not in {204, 404}:
                        row["status"] = "error"
                        row["errors"] = 1
            rows.append(row)
            print(f"[{iteration}/{args.iterations}] {row['status']}")

        metrics_after = (await client.get("/metrics")).json()
        (evidence_dir / "metrics_after.json").write_text(
            json.dumps(metrics_after, indent=2), encoding="utf-8"
        )
    finally:
        await client.aclose()

    fields = sorted({key for row in rows for key in row})
    with (evidence_dir / "raw_results.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        **config,
        "errors": sum(row["errors"] for row in rows),
        "operations": {
            key: statistics([float(row[key]) for row in rows if row.get(key) is not None])
            for key in (
                "health_ms",
                "create_ms",
                "ws_connect_ms",
                "solve_http_ms",
                "ws_first_progress_ms",
                "ws_result_ms",
                "ws_completed_ms",
                "get_results_ms",
                "delete_ms",
            )
        },
    }
    (evidence_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Evidence: {evidence_dir}")


if __name__ == "__main__":
    asyncio.run(campaign(arguments()))
