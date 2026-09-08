import asyncio
import threading

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.adapters.opendss.engine import OpenDSSContextEngine
from app.orchestration import simulation_service as service_module
from app.orchestration.container import simulation_service


def test_registry_openapi_last_result_and_close() -> None:
    with TestClient(app) as client:
        created = [
            client.post("/simulations", json={"topology": "ieee13"}).json()
            for _ in range(3)
        ]
        listed = client.get("/simulations")
        assert listed.status_code == 200
        listed_by_id = {item["session_id"]: item for item in listed.json()}
        assert set(listed_by_id) >= {item["session_id"] for item in created}
        for item in created:
            listed_item = listed_by_id[item["session_id"]]
            assert listed_item["session_id"] == item["session_id"]
            assert listed_item["status"] == "READY"
            assert listed_item["created_at"] == item["created_at"]

        session_id = created[0]["session_id"]
        solved = client.post(f"/simulations/{session_id}/solve")
        assert solved.status_code == 200
        detail = client.get(f"/simulations/{session_id}")
        assert detail.status_code == 200
        assert detail.json()["last_result"]["session_id"] == session_id

        assert client.delete(f"/simulations/{session_id}").status_code == 204
        assert client.get(f"/simulations/{session_id}").status_code == 404


def test_docs_and_invalid_topology() -> None:
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        assert "/simulations" in openapi.json()["paths"]
        invalid = client.post("/simulations", json={"topology": "missing"})
        assert invalid.status_code == 400


def test_websocket_snapshot_and_broadcast() -> None:
    with TestClient(app) as client:
        session_id = client.post(
            "/simulations", json={"topology": "ieee13"}
        ).json()["session_id"]
        with client.websocket_connect(f"/ws/simulations/{session_id}") as websocket:
            snapshot = websocket.receive_json()
            assert snapshot["type"] == "snapshot"
            assert snapshot["last_result"] is None
            client.post(f"/simulations/{session_id}/solve")
            events = [websocket.receive_json() for _ in range(5)]
            assert [event["type"] for event in events] == [
                "simulation_started",
                "model_loaded",
                "solving",
                "result",
                "completed",
            ]
            assert events[3]["result"]["session_id"] == session_id
        client.delete(f"/simulations/{session_id}")


def test_recycle_preserves_session_id(monkeypatch) -> None:
    monkeypatch.setattr(service_module, "RECYCLE_THRESHOLD", 1)
    with TestClient(app) as client:
        session_id = client.post(
            "/simulations", json={"topology": "ieee13"}
        ).json()["session_id"]
        old_identity = simulation_service.get_engine_identity(session_id)
        assert client.post(f"/simulations/{session_id}/solve").status_code == 200
        assert simulation_service.get_engine_identity(session_id) != old_identity
        detail = client.get(f"/simulations/{session_id}").json()
        assert detail["session_id"] == session_id
        assert detail["task_count"] == 0
        client.delete(f"/simulations/{session_id}")


def test_ieee13_model_summary() -> None:
    with TestClient(app) as client:
        session_id = client.post(
            "/simulations", json={"topology": "ieee13"}
        ).json()["session_id"]
        detail = client.get(f"/simulations/{session_id}").json()
        assert detail["model_summary"]["num_buses"] == 16
        assert detail["model_summary"]["num_nodes"] == 41
        client.delete(f"/simulations/{session_id}")


def test_late_websocket_viewer_receives_last_result() -> None:
    with TestClient(app) as client:
        session_id = client.post(
            "/simulations", json={"topology": "ieee13"}
        ).json()["session_id"]
        solved = client.post(f"/simulations/{session_id}/solve")
        assert solved.status_code == 200
        result = solved.json()

        with client.websocket_connect(f"/ws/simulations/{session_id}") as websocket:
            snapshot = websocket.receive_json()
            assert snapshot["type"] == "snapshot"
            assert snapshot["last_result"] == result

        detail = client.get(f"/simulations/{session_id}").json()
        assert detail["task_count"] == 1
        client.delete(f"/simulations/{session_id}")


def test_multiple_viewers_are_isolated_per_simulation() -> None:
    with TestClient(app) as client:
        session_a = client.post(
            "/simulations", json={"topology": "ieee13", "load_multiplier": 0.8}
        ).json()["session_id"]
        session_b = client.post(
            "/simulations", json={"topology": "ieee13", "load_multiplier": 1.2}
        ).json()["session_id"]
        with (
            client.websocket_connect(f"/ws/simulations/{session_a}") as a1,
            client.websocket_connect(f"/ws/simulations/{session_a}") as a2,
            client.websocket_connect(f"/ws/simulations/{session_b}") as b1,
            client.websocket_connect(f"/ws/simulations/{session_b}") as b2,
        ):
            for websocket, session_id in ((a1, session_a), (a2, session_a), (b1, session_b), (b2, session_b)):
                snapshot = websocket.receive_json()
                assert snapshot["session_id"] == session_id

            result_a = client.post(f"/simulations/{session_a}/solve").json()
            result_b = client.post(f"/simulations/{session_b}/solve").json()
            received = {}
            for websocket, session_id in ((a1, session_a), (a2, session_a), (b1, session_b), (b2, session_b)):
                events = [websocket.receive_json() for _ in range(5)]
                assert all(event["session_id"] == session_id for event in events)
                received[session_id] = received.get(session_id, []) + [events[-2]["result"]]
            assert received[session_a] == [result_a, result_a]
            assert received[session_b] == [result_b, result_b]
            assert all(event["session_id"] != session_b for event in [*received[session_a]])
            assert all(event["session_id"] != session_a for event in [*received[session_b]])
        client.delete(f"/simulations/{session_a}")
        client.delete(f"/simulations/{session_b}")


def test_health_is_available_during_solve(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()
    original_solve = OpenDSSContextEngine.solve

    def controlled_solve(self, session_id: str, topology: str):
        started.set()
        if not release.wait(timeout=2):
            raise TimeoutError("controlled solve was not released")
        return original_solve(self, session_id, topology)

    monkeypatch.setattr(OpenDSSContextEngine, "solve", controlled_solve)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/simulations", json={"topology": "ieee13"})
            session_id = created.json()["session_id"]
            solve_task = asyncio.create_task(
                client.post(f"/simulations/{session_id}/solve")
            )
            assert await asyncio.to_thread(started.wait, 2)
            health = await client.get("/health")
            assert health.status_code == 200
            release.set()
            solved = await solve_task
            assert solved.status_code == 200
            assert (await client.delete(f"/simulations/{session_id}")).status_code == 204

    try:
        asyncio.run(scenario())
    finally:
        release.set()
