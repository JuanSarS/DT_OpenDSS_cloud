from __future__ import annotations
import traceback

import asyncio
import csv
import json
import math
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import websockets


BASE_URL = os.getenv(
    "BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

WS_BASE_URL = os.getenv(
    "WS_BASE_URL",
    BASE_URL.replace("https://", "wss://").replace(
        "http://",
        "ws://",
    ),
).rstrip("/")

RUNS = int(os.getenv("LATENCY_RUNS", "10"))
TOPOLOGY = os.getenv("LATENCY_TOPOLOGY", "ieee13")

OUTPUT_DIR = Path(
    os.getenv(
        "LATENCY_OUTPUT_DIR",
        "docs/evidence",
    )
)

HTTP_TIMEOUT = float(
    os.getenv(
        "LATENCY_HTTP_TIMEOUT",
        "30",
    )
)

WS_TIMEOUT = float(
    os.getenv(
        "LATENCY_WS_TIMEOUT",
        "15",
    )
)

WS_CONNECT_TIMEOUT = float(
    os.getenv(
        "LATENCY_WS_CONNECT_TIMEOUT",
        "30",
    )
)

WS_CONNECT_RETRIES = int(
    os.getenv(
        "LATENCY_WS_CONNECT_RETRIES",
        "2",
    )
)

PAUSE_BETWEEN_RUNS = float(
    os.getenv(
        "LATENCY_PAUSE_SECONDS",
        "0.5",
    )
)

def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


async def timed_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> tuple[httpx.Response, float]:

    start = time.perf_counter()

    response = await client.request(
        method,
        url,
        **kwargs,
    )

    return response, elapsed_ms(start)


async def receive_json(
    websocket,
) -> dict:

    raw = await asyncio.wait_for(
        websocket.recv(),
        timeout=WS_TIMEOUT,
    )

    return json.loads(raw)

async def connect_websocket_with_retry(
    websocket_url: str,
):

    last_error = None

    total_attempts = WS_CONNECT_RETRIES + 1

    for attempt in range(
        1,
        total_attempts + 1,
    ):

        start = time.perf_counter()

        try:

            websocket = await websockets.connect(
                websocket_url,
                open_timeout=WS_CONNECT_TIMEOUT,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            )

            connect_ms = elapsed_ms(start)

            return (
                websocket,
                connect_ms,
                attempt,
            )

        except (TimeoutError, OSError) as exc:

            last_error = exc

            print(
                f"    [WS] intento "
                f"{attempt}/{total_attempts} falló: "
                f"{type(exc).__name__}: {exc}"
            )

            if attempt >= total_attempts:
                raise

            await asyncio.sleep(
                min(attempt, 3)
            )

    raise last_error

async def run_iteration(
    client: httpx.AsyncClient,
    iteration: int,
) -> dict:

    session_id: str | None = None
    websocket = None
    solve_task = None

    row = {
        "iteration": iteration,
        "topology": TOPOLOGY,
        "status": "RUNNING",
        "error": None,
    }

    try:

        # -----------------------------------------------------
        # 1. HEALTH
        # -----------------------------------------------------

        response, health_ms = await timed_request(
            client,
            "GET",
            "/health",
        )

        assert response.status_code == 200, (
            f"/health HTTP {response.status_code}: "
            f"{response.text}"
        )

        row["health_ms"] = health_ms

        # -----------------------------------------------------
        # 2. CREATE SIMULATION
        # -----------------------------------------------------

        response, create_ms = await timed_request(
            client,
            "POST",
            "/simulations",
            json={
                "topology": TOPOLOGY,
            },
        )

        assert response.status_code == 201, (
            f"Create HTTP {response.status_code}: "
            f"{response.text}"
        )

        created = response.json()

        session_id = created["session_id"]

        row["session_id"] = session_id
        row["create_ms"] = create_ms

        # -----------------------------------------------------
        # 3. WEBSOCKET CONNECTION
        # -----------------------------------------------------

        websocket_url = (
            f"{WS_BASE_URL}/ws/simulations/{session_id}"
        )

        (
            websocket,
            ws_connect_ms,
            ws_connect_attempts,
        ) = await connect_websocket_with_retry(
            websocket_url
        )

        row["ws_connect_ms"] = ws_connect_ms
        row["ws_connect_attempts"] = ws_connect_attempts

        # -----------------------------------------------------
        # 4. INITIAL SNAPSHOT
        # -----------------------------------------------------

        snapshot_start = time.perf_counter()

        snapshot = await receive_json(
            websocket
        )

        row["ws_snapshot_ms"] = elapsed_ms(
            snapshot_start
        )

        assert snapshot.get("type") == "snapshot", (
            "El primer mensaje WebSocket no fue snapshot. "
            f"Recibido: {snapshot}"
        )

        assert snapshot.get("session_id") == session_id, (
            "El snapshot pertenece a otra sesión. "
            f"Esperado={session_id}, "
            f"recibido={snapshot.get('session_id')}"
        )

        # -----------------------------------------------------
        # 5. SOLVE
        # -----------------------------------------------------

        

        solve_start = time.perf_counter()

        async def execute_solve():
            return await timed_request(
                            client,
                            "POST",
                            f"/simulations/{session_id}/solve",
            )
        solve_task = asyncio.create_task(
            execute_solve()
        )

        ws_result_ms = None
        ws_completed_ms = None

        event_types: list[str] = []

        i = 0
        max_iter = 20

        # -----------------------------------------------------
        # 6. RECEIVE WEBSOCKET EVENTS
        # -----------------------------------------------------

        while (
            "completed" not in event_types
            and i < max_iter
        ):

            event = await receive_json(
                websocket
            )

            event_type = event.get("type")

            event_types.append(
                str(event_type)
            )

            assert (
                event.get("session_id")
                == session_id
            ), (
                "Se recibió un evento de otra sesión. "
                f"Esperado={session_id}, "
                f"recibido={event.get('session_id')}"
            )

            current_ms = elapsed_ms(
                solve_start
            )

            if (
                event_type == "result"
                and ws_result_ms is None
            ):
                ws_result_ms = current_ms

            if event_type == "completed":
                ws_completed_ms = current_ms

            i += 1

        # -----------------------------------------------------
        # 7. VALIDATE EVENT COMPLETION
        # -----------------------------------------------------

        if "completed" not in event_types:
            raise TimeoutError(
                "No se recibió el evento 'completed'. "
                f"Eventos recibidos: {event_types}"
            )

        # -----------------------------------------------------
        # 8. WAIT FOR HTTP SOLVE RESULT
        # -----------------------------------------------------

        response, solve_http_ms = await solve_task

        solve_task = None

        assert response.status_code == 200, (
            f"Solve HTTP {response.status_code}: "
            f"{response.text}"
        )

        solve_result = response.json()

        assert solve_result.get("converged") is True, (
            "La simulación OpenDSS no convergió."
        )

        row["solve_http_ms"] = solve_http_ms

        row["engine_elapsed_ms"] = (
            solve_result.get("elapsed_ms")
        )

        row["ws_result_ms"] = ws_result_ms

        row["ws_completed_ms"] = (
            ws_completed_ms
        )

        row["events"] = ",".join(
            event_types
        )

        # -----------------------------------------------------
        # 9. CLOSE WEBSOCKET
        # -----------------------------------------------------

        if websocket is not None:

            await websocket.close()

            websocket = None

        # -----------------------------------------------------
        # 10. DELETE SIMULATION
        # -----------------------------------------------------

        response, delete_ms = await timed_request(
            client,
            "DELETE",
            f"/simulations/{session_id}",
        )

        assert response.status_code == 204, (
            "No se pudo cerrar la simulación. "
            f"HTTP {response.status_code}: "
            f"{response.text}"
        )

        row["delete_ms"] = delete_ms

        # Ya fue eliminada correctamente.
        # Esto evita intentar borrarla otra vez en finally.
        session_id = None

        # -----------------------------------------------------
        # 11. SUCCESS
        # -----------------------------------------------------

        row["status"] = "OK"
        row["error"] = None

        return row

    finally:

        # -----------------------------------------------------
        # CLEANUP: SOLVE TASK
        # -----------------------------------------------------

        if solve_task is not None:

            if not solve_task.done():

                solve_task.cancel()

                try:
                    await solve_task
                except asyncio.CancelledError:
                    pass

        # -----------------------------------------------------
        # CLEANUP: WEBSOCKET
        # -----------------------------------------------------

        if websocket is not None:

            try:
                await websocket.close()
            except Exception:
                pass

        # -----------------------------------------------------
        # CLEANUP: SIMULATION
        # -----------------------------------------------------

        # Si ocurrió una excepción antes del DELETE normal,
        # intentamos eliminar la sesión para no dejar recursos
        # activos en el servidor.
        if session_id is not None:

            try:

                await client.delete(
                    f"/simulations/{session_id}"
                )

            except Exception:
                pass


def percentile(
    values: list[float],
    percentile_value: float,
) -> float:

    if not values:
        return float("nan")

    ordered = sorted(values)

    index = math.ceil(
        percentile_value
        * len(ordered)
    ) - 1

    index = max(
        0,
        min(
            index,
            len(ordered) - 1,
        ),
    )

    return ordered[index]


def calculate_statistics(
    rows: list[dict],
) -> dict:

    metrics = [
        "health_ms",
        "create_ms",
        "ws_connect_ms",
        "ws_snapshot_ms",
        "solve_http_ms",
        "engine_elapsed_ms",
        "ws_result_ms",
        "ws_completed_ms",
        "delete_ms",
    ]

    summary = {}

    for metric in metrics:

        values = [
            float(row[metric])
            for row in rows
            if row.get(metric) is not None
        ]

        if not values:
            continue

        summary[metric] = {
            "count": len(values),
            "min_ms": min(values),
            "mean_ms": statistics.mean(values),
            "median_ms": statistics.median(values),
            "p95_ms": percentile(
                values,
                0.95,
            ),
            "max_ms": max(values),
        }

    return summary


async def main() -> None:

    print()
    print(
        "========================================"
    )
    print(
        " OpenDSS Cloud - AWS Latency Test"
    )
    print(
        "========================================"
    )

    print(f"HTTP:      {BASE_URL}")
    print(f"WebSocket: {WS_BASE_URL}")
    print(f"Topology:  {TOPOLOGY}")
    print(f"Runs:      {RUNS}")
    print()

    rows: list[dict] = []

    total_start = time.perf_counter()

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=HTTP_TIMEOUT,
    ) as client:

        for iteration in range(
            1,
            RUNS + 1,
        ):

            print(
                f"[{iteration}/{RUNS}] Ejecutando..."
            )

            try:
                result = await run_iteration(
                    client,
                    iteration,
                )
                if result is None:
                    
                    raise RuntimeError(
                        "run_iteration() terminó sin devolver resultados"
                    )
                
                rows.append(result)

                print(
                    "    "
                    f"health={result['health_ms']:.2f} ms | "
                    f"create={result['create_ms']:.2f} ms | "
                    f"solve={result['solve_http_ms']:.2f} ms | "
                    f"engine={result['engine_elapsed_ms']:.2f} ms | "
                    f"ws-result={result['ws_result_ms']:.2f} ms"
                )
            except (RuntimeError, TypeError) as exc:
                print(
                    f"[ERROR] Iteración "
                    f"{iteration}: "
                    f"{type(exc).__name__}: {exc}"
                )
                traceback.print_exc()
                raise     
            except Exception as exc:

                print(
                    f"[ERROR] Iteración "
                    f"{iteration}: "
                    f"{type(exc).__name__}: {exc}"
                )
                

                rows.append(
                    {
                        "iteration": iteration,
                        "topology": TOPOLOGY,
                        "status": "ERROR",
                        "error": (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    }
                )
            await asyncio.sleep(
                    PAUSE_BETWEEN_RUNS
                )

    total_ms = elapsed_ms(
        total_start
    )

    summary = calculate_statistics(
        rows
    )

    # ---------------------------------------------------------
    # GUARDAR EVIDENCIA
    # ---------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d_%H%M%S_UTC"
    )

    csv_path = (
        OUTPUT_DIR
        / f"aws_latency_{timestamp}.csv"
    )

    json_path = (
        OUTPUT_DIR
        / f"aws_latency_{timestamp}.json"
    )

    fieldnames = [
        "iteration",
        "topology",
        "session_id",
        "health_ms",
        "create_ms",
        "ws_connect_ms",
        "ws_snapshot_ms",
        "solve_http_ms",
        "engine_elapsed_ms",
        "ws_result_ms",
        "ws_completed_ms",
        "delete_ms",
        "events",
        "status",
        "ws_connect_attempts",
        "error",
    ]

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    report = {
        "timestamp_utc": timestamp,
        "base_url": BASE_URL,
        "ws_base_url": WS_BASE_URL,
        "topology": TOPOLOGY,
        "runs": RUNS,
        "total_test_ms": total_ms,
        "statistics": summary,
    }

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # MOSTRAR RESUMEN
    # ---------------------------------------------------------

    print()
    print(
        "========================================"
    )
    print(
        " RESUMEN DE LATENCIAS"
    )
    print(
        "========================================"
    )

    for metric, stats in summary.items():

        print()
        print(metric)

        print(
            f"  min:    "
            f"{stats['min_ms']:.2f} ms"
        )

        print(
            f"  media:  "
            f"{stats['mean_ms']:.2f} ms"
        )

        print(
            f"  mediana:"
            f" {stats['median_ms']:.2f} ms"
        )

        print(
            f"  p95:    "
            f"{stats['p95_ms']:.2f} ms"
        )

        print(
            f"  max:    "
            f"{stats['max_ms']:.2f} ms"
        )

    print()
    print(
        f"Tiempo total: "
        f"{total_ms / 1000:.2f} s"
    )

    print()
    print(
        f"CSV:  {csv_path}"
    )

    print(
        f"JSON: {json_path}"
    )

    print()
    print(
        "========================================"
    )
    print(
        " LATENCY TEST OK"
    )
    print(
        "========================================"
    )


if __name__ == "__main__":
    asyncio.run(main())