from __future__ import annotations

import asyncio
import json
import os

import httpx
import websockets


async def receive_json(socket, timeout: float = 10.0) -> dict:
    """
    Recibe un mensaje WebSocket y lo convierte de JSON a diccionario.
    """
    raw_message = await asyncio.wait_for(
        socket.recv(),
        timeout=timeout,
    )

    return json.loads(raw_message)


async def main() -> None:
    # ---------------------------------------------------------
    # Configuración
    # ---------------------------------------------------------

    base = os.getenv(
        "BASE_URL",
        "http://127.0.0.1:8000",
    ).rstrip("/")

    ws_base = os.getenv(
        "WS_BASE_URL",
        base.replace("https://", "wss://").replace(
            "http://",
            "ws://",
        ),
    ).rstrip("/")

    print()
    print("========================================")
    print(" OpenDSS Cloud - Smoke Test")
    print("========================================")
    print(f"HTTP: {base}")
    print(f"WS:   {ws_base}")
    print()

    session_id: str | None = None

    async with httpx.AsyncClient(
        base_url=base,
        timeout=30.0,
    ) as client:

        # -----------------------------------------------------
        # 1. Health
        # -----------------------------------------------------

        response = await client.get("/health")

        assert response.status_code == 200, (
            f"/health respondió {response.status_code}: "
            f"{response.text}"
        )

        print("[OK] /health")

        # -----------------------------------------------------
        # 2. Swagger
        # -----------------------------------------------------

        response = await client.get("/docs")

        assert response.status_code == 200, (
            f"/docs respondió {response.status_code}"
        )

        print("[OK] /docs")

        # -----------------------------------------------------
        # 3. Catálogo de modelos
        # -----------------------------------------------------

        response = await client.get("/models")

        assert response.status_code == 200, (
            f"/models respondió {response.status_code}: "
            f"{response.text}"
        )

        models = response.json()

        available_models = {
            model["id"]
            for model in models
        }

        required_models = {
            "ieee13",
            "ieee34",
            "ieee123",
        }

        assert required_models <= available_models, (
            "Faltan modelos IEEE. "
            f"Disponibles: {available_models}"
        )

        print(
            "[OK] /models -> "
            + ", ".join(sorted(available_models))
        )

        # -----------------------------------------------------
        # 4. Crear simulación
        # -----------------------------------------------------

        response = await client.post(
            "/simulations",
            json={
                "topology": "ieee13",
            },
        )

        assert response.status_code == 201, (
            "No se pudo crear la simulación. "
            f"HTTP {response.status_code}: {response.text}"
        )

        created = response.json()

        session_id = created["session_id"]

        print(f"[OK] Simulación creada: {session_id}")

        # -----------------------------------------------------
        # 5. Consultar simulación
        # -----------------------------------------------------

        response = await client.get(
            f"/simulations/{session_id}"
        )

        assert response.status_code == 200, (
            "No se pudo consultar la simulación. "
            f"HTTP {response.status_code}: {response.text}"
        )

        print("[OK] GET /simulations/{session_id}")

        # -----------------------------------------------------
        # 6. WebSocket
        # -----------------------------------------------------

        websocket_url = (
            f"{ws_base}/ws/simulations/{session_id}"
        )

        print(f"[INFO] Conectando WebSocket: {websocket_url}")

        async with websockets.connect(
            websocket_url
        ) as socket:

            # -------------------------------------------------
            # Snapshot inicial
            # -------------------------------------------------

            snapshot = await receive_json(socket)

            assert snapshot.get("type") == "snapshot", (
                "El primer mensaje WebSocket no fue snapshot. "
                f"Recibido: {snapshot}"
            )

            assert snapshot.get("session_id") == session_id, (
                "El snapshot pertenece a otra sesión. "
                f"Recibido: {snapshot.get('session_id')}"
            )

            print("[OK] Snapshot WebSocket inicial")

            # -------------------------------------------------
            # 7. Ejecutar solve
            # -------------------------------------------------

            response = await client.post(
                f"/simulations/{session_id}/solve"
            )

            assert response.status_code == 200, (
                "Solve falló. "
                f"HTTP {response.status_code}: {response.text}"
            )

            result = response.json()

            assert result["converged"] is True, (
                "La simulación OpenDSS no convergió."
            )

            print("[OK] Solve OpenDSS converged=True")

            # -------------------------------------------------
            # 8. Recibir eventos WebSocket
            # -------------------------------------------------

            received_events: list[dict] = []

            # No dependemos de que sean exactamente 5 mensajes.
            # Seguimos hasta recibir "completed".
            for _ in range(10):

                event = await receive_json(
                    socket,
                    timeout=10.0,
                )

                received_events.append(event)

                event_type = event.get("type")

                print(
                    f"[WS] {event_type}"
                )

                # Todos los eventos deben pertenecer
                # a nuestra simulación.
                assert event.get("session_id") == session_id, (
                    "Se recibió un evento perteneciente "
                    "a otra simulación: "
                    f"{event}"
                )

                if event_type == "completed":
                    break

            # -------------------------------------------------
            # 9. Validar eventos
            # -------------------------------------------------

            event_types = [
                event.get("type")
                for event in received_events
            ]

            print()
            print(
                "Eventos WebSocket recibidos:",
                event_types,
            )

            assert "simulation_started" in event_types, (
                "No se recibió simulation_started. "
                f"Recibidos: {event_types}"
            )

            assert "model_loaded" in event_types, (
                "No se recibió model_loaded. "
                f"Recibidos: {event_types}"
            )

            assert "solving" in event_types, (
                "No se recibió solving. "
                f"Recibidos: {event_types}"
            )

            assert "result" in event_types, (
                "No se recibió result. "
                f"Recibidos: {event_types}"
            )

            assert "completed" in event_types, (
                "No se recibió completed. "
                f"Recibidos: {event_types}"
            )

            print("[OK] Broadcast WebSocket completo")

        # -----------------------------------------------------
        # 10. Cerrar simulación
        # -----------------------------------------------------

        response = await client.delete(
            f"/simulations/{session_id}"
        )

        assert response.status_code == 204, (
            "No se pudo cerrar la simulación. "
            f"HTTP {response.status_code}: {response.text}"
        )

        print("[OK] DELETE simulación")

        # -----------------------------------------------------
        # 11. Confirmar eliminación
        # -----------------------------------------------------

        response = await client.get(
            f"/simulations/{session_id}"
        )

        assert response.status_code == 404, (
            "La simulación debería haber sido eliminada, "
            f"pero respondió {response.status_code}"
        )

        print("[OK] Sesión eliminada -> 404")

    print()
    print("========================================")
    print(" SMOKE OK")
    print("========================================")
    print()


if __name__ == "__main__":
    asyncio.run(main())