import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from packages.contracts.auth import UserRecord
from packages.contracts.models import QSTSConfig
from packages.simulation_core.engine import OpenDSSContextEngine
from packages.simulation_core.topology_catalog import resolve_builtin_topology
from services.api_manager.api.routes import interactive, simulations
from services.api_manager.auth import dependencies, routes
from services.api_manager.auth.constants import ACCESS_COOKIE_NAME
from services.api_manager.execution.remote_executor import RemoteSimulationExecutor
from services.api_manager.execution.worker_pool import WorkerPoolSimulationExecutor
from services.api_manager.main import app
from services.api_manager.orchestration import interactive_service
from services.api_manager.orchestration.simulation_service import SimulationService
from services.api_manager.platform.settings import settings
from services.simulation_worker import main as worker
from services.simulation_worker.executor import LocalSimulationExecutor


@pytest.fixture(params=["local", "pool-http"])
def lab(monkeypatch, request):
    users = {
        name: UserRecord(username=name, role="user", password_hash="unused")
        for name in ("owner", "operator", "viewer", "outsider")
    }
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "worker_retry_enabled", True)
    monkeypatch.delenv("JWT_SECRET_FILE", raising=False)
    monkeypatch.delenv("WORKER_SHARED_TOKEN_FILE", raising=False)
    monkeypatch.setenv("JWT_SECRET", "interactive-test-key-" * 3)
    monkeypatch.setenv("WORKER_SHARED_TOKEN", "interactive-worker-fixture")
    monkeypatch.setattr(dependencies, "load_users", lambda: users)
    monkeypatch.setattr(routes, "authenticate_user", lambda name, _: users.get(name))
    monkeypatch.setattr(interactive, "load_users", lambda: users)

    local = LocalSimulationExecutor(recycle_threshold=1)
    executor = local
    if request.param == "pool-http":
        monkeypatch.setattr(worker, "executor", local)
        executor = WorkerPoolSimulationExecutor(endpoints=["http://worker"], timeout_seconds=15)
        remote = RemoteSimulationExecutor(base_url="http://worker")
        monkeypatch.setattr(remote, "_client", lambda: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=worker.app, raise_app_exceptions=False),
            base_url="http://worker", headers={"Authorization": "Bearer interactive-worker-fixture"},
        ))
        executor._clients["http://worker"] = remote
    service = SimulationService(executor)
    monkeypatch.setattr(interactive, "simulation_service", service)
    monkeypatch.setattr(simulations, "simulation_service", service)

    with TestClient(app, base_url="https://testserver") as client:
        headers = {}
        for name in users:
            response = client.post("/auth/token", data={"username": name, "password": "fixture"})
            assert response.status_code == 200
            cookie = client.cookies.get(ACCESS_COOKIE_NAME)
            headers[name] = {"Cookie": f"{ACCESS_COOKIE_NAME}={cookie}"}
            client.cookies.clear()
        yield client, headers, local


def create(client, owner):
    response = client.post("/simulations", headers=owner, json={"topology": "ieee13"})
    assert response.status_code == 201, response.text
    return f"/simulations/{response.json()['session_id']}"


def initialize(client, path, owner, **options):
    response = client.post(path + "/qsts/interactive/start", headers=owner, json={
        "duration_hours": 1, "step_minutes": 10, **options,
    })
    assert response.status_code == 200, response.text
    return response.json()


def step_body(run_id, expected_step):
    return {"run_id": run_id, "expected_step": expected_step, "command_id": str(uuid4())}


def get_until(client, url, actor, ready, timeout=6):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        response = client.get(url, headers=actor)
        assert response.status_code == 200
        result = response.json()
        if ready(result):
            return result
        time.sleep(0.025)
    pytest.fail("No se alcanzó el estado esperado dentro del plazo de prueba.")


@pytest.mark.parametrize("topology", ["ieee13", "ieee34", "ieee123", "ieee8500"])
def test_batch_equivalence_in_one_context(topology):
    path = resolve_builtin_topology(topology)
    config = QSTSConfig(duration_hours=1, step_minutes=20, profile_source="synthetic_daily")
    batch_engine = OpenDSSContextEngine(path)
    interactive_engine = OpenDSSContextEngine(path)
    try:
        batch = batch_engine.solve_qsts(config)
        identity = interactive_engine.identity
        sequence = interactive_engine.begin_qsts(config)
        for expected in batch.steps:
            observed = interactive_engine.advance_interactive(sequence)
            assert interactive_engine.identity == identity
            assert observed.step == expected.step
            assert observed.converged == expected.converged
            for field in (
                "simulated_minutes", "opendss_hour", "load_multiplier", "total_kw", "total_kvar",
                "min_voltage_pu", "max_voltage_pu",
            ):
                assert getattr(observed, field) == pytest.approx(getattr(expected, field), abs=1e-8)
    finally:
        batch_engine.close()
        interactive_engine.close()


def test_switch_changes_electrical_results_and_is_broadcast(lab):
    client, users, local = lab
    owner, operator, viewer = (users[name] for name in ("owner", "operator", "viewer"))
    path = create(client, owner)
    assert client.put(path + "/participants/operator", headers=owner, json={"role": "operator"}).status_code == 200
    assert client.put(path + "/participants/viewer", headers=owner, json={"role": "viewer"}).status_code == 200
    assert client.get(path, headers=operator).json()["access_mode"] == "operator"
    assert client.post(path + "/solve", headers=operator).status_code == 403
    assert client.get(path + "/controls/history", headers=users["outsider"]).status_code == 403
    qsts = path + "/qsts/interactive"
    state = initialize(client, path, owner)
    run_id = state["run_id"]
    assert client.put(qsts + "/mode", json={"run_id": run_id, "execution_mode": "automatic"}, headers=operator).status_code == 403
    assert client.put(qsts + "/interval", json={"run_id": run_id, "interval_seconds": 1}, headers=operator).status_code == 403
    assert client.post(qsts + "/pause", json={"run_id": run_id}, headers=operator).json()["phase"] == "paused"
    assert client.post(qsts + "/resume", json={"run_id": run_id}, headers=operator).json()["phase"] == "ready"
    socket_url = "wss://testserver/ws" + path
    session_id = path.rsplit("/", 1)[-1]
    identity = client.portal.call(local.session_info, session_id).runtime_identity

    with client.websocket_connect(socket_url, headers=viewer) as observer:
        snapshot = observer.receive_json()
        assert snapshot["interactive"]["run_id"] == run_id
        switch = next(item for item in snapshot["switches"] if item["element"].lower() == "line.671692")
        assert switch["status"] == "closed"
        assert client.get(qsts + "/network", headers=viewer).status_code == 200
        assert client.post(qsts + "/step", json=step_body(run_id, 0), headers=viewer).status_code == 403

        first = client.post(qsts + "/step", json=step_body(run_id, 0), headers=operator)
        assert first.status_code == 200, first.text
        assert observer.receive_json()["type"] == "interactive_step"
        uri = path + "/controls/switches/" + switch["element"]
        open_command = {**step_body(run_id, 1), "action": "open"}
        assert client.post(uri, headers=viewer, json=open_command).status_code == 403
        assert client.post(path + "/controls/switches/Line.650632", headers=operator, json=open_command).status_code == 404
        opened = client.post(uri, headers=operator, json=open_command)
        assert opened.status_code == 200, opened.text
        assert opened.json()["effective_state"]["status"] == "open"
        event = observer.receive_json()
        assert event["type"] == "switch_operation"
        assert event["state"]["results_stale"] is True
        assert event["operation"] == opened.json()
        assert event["operation"]["actor"] == "operator" and event["operation"]["step"] == 1
        assert client.post(uri, headers=operator, json=open_command).json() == opened.json()
        assert client.get(uri, headers=viewer).json()["status"] == "open"

        second = client.post(qsts + "/step", json=step_body(run_id, 1), headers=operator).json()
        assert observer.receive_json()["state"]["completed_steps"] == 2
        assert abs(second["result"]["total_kw"]) < abs(first.json()["result"]["total_kw"]) - 100
        assert "loss_kw" in second["result"]
        assert second["state"]["results_stale"] is False
        assert client.post(uri, headers=operator, json={**step_body(run_id, 2), "action": "close"}).json()["effective_state"]["status"] == "closed"
        assert observer.receive_json()["operation"]["action"] == "close"
        third = client.post(qsts + "/step", json=step_body(run_id, 2), headers=operator).json()
        assert observer.receive_json()["type"] == "interactive_step"
        assert abs(third["result"]["total_kw"]) > abs(second["result"]["total_kw"]) + 100
        assert client.portal.call(local.session_info, session_id).runtime_identity == identity
        assert len(client.get(path + "/controls/history", headers=viewer).json()) == 2

        with client.websocket_connect(socket_url, headers=operator) as promoted:
            assert promoted.receive_json()["simulation"]["access_mode"] == "operator"
            assert client.put(path + "/participants/operator", headers=owner, json={"role": "viewer"}).status_code == 200
            assert promoted.receive_json()["access_mode"] == "viewer"
            assert client.post(qsts + "/pause", headers=operator, json={"run_id": run_id}).status_code == 403
            assert client.delete(path + "/participants/operator", headers=owner).status_code == 204
            assert promoted.receive_json()["type"] == "participants_changed"
            with pytest.raises(WebSocketDisconnect) as revoked:
                promoted.receive_json()
            assert revoked.value.code == 1008


def test_automatic_force_pause_modes_interval_and_restart(lab):
    client, users, _ = lab
    owner = users["owner"]
    path = create(client, owner)
    qsts = path + "/qsts/interactive"
    config = initialize(client, path, owner, execution_mode="automatic", interval_seconds=1.2)
    assert config["phase"] == "paused" and config["completed_steps"] == 0
    run = {"run_id": config["run_id"]}
    assert client.post(qsts + "/run", headers=owner, json=run).status_code == 200
    get_until(client, qsts + "/state", owner, lambda state: state["completed_steps"] == 1)
    body = step_body(run["run_id"], 1)
    prompted = client.post(qsts + "/step", headers=owner, json=body)
    assert prompted.status_code == 200, prompted.text
    assert prompted.json()["state"]["completed_steps"] == 2
    assert client.post(qsts + "/step", headers=owner, json=body).json()["result"]["step"] == 2
    assert client.post(qsts + "/step", headers=owner, json=step_body(run["run_id"], 1)).status_code == 409
    assert client.post(qsts + "/pause", headers=owner, json=run).json()["phase"] == "paused"
    time.sleep(1.35)
    assert client.get(qsts + "/state", headers=owner).json()["completed_steps"] == 2
    assert client.put(qsts + "/interval", headers=owner, json={**run, "interval_seconds": 0.1}).json()["interval_seconds"] == 0.1
    assert client.put(qsts + "/mode", headers=owner, json={**run, "execution_mode": "manual"}).json()["execution_mode"] == "manual"
    assert client.post(qsts + "/resume", headers=owner, json=run).json()["phase"] == "ready"
    time.sleep(0.2)
    assert client.get(qsts + "/state", headers=owner).json()["completed_steps"] == 2
    assert client.post(qsts + "/stop", headers=owner, json=run).json()["phase"] == "stopped"
    restarted = client.post(qsts + "/restart", headers=owner, json=run).json()
    assert restarted["run_id"] != run["run_id"] and restarted["completed_steps"] == 0
    assert client.post(qsts + "/step", headers=owner, json=step_body(run["run_id"], 0)).status_code == 409
    assert client.post(qsts + "/run", headers=owner, json={"run_id": restarted["run_id"]}).status_code == 200
    finished = get_until(client, qsts + "/state", owner, lambda state: state["phase"] == "completed")
    assert finished["completed_steps"] == 6 and finished["simulated_minutes"] == 60
    assert [step["step"] for step in client.get(qsts + "/results", headers=owner).json()] == [1, 2, 3, 4, 5, 6]
    assert client.post(path + "/solve", headers=owner).status_code == 200


def test_simultaneous_commands_and_worker_loss_without_replay(lab, monkeypatch):
    client, users, local = lab
    owner = users["owner"]
    monkeypatch.setattr(interactive_service, "WORKER_PROBE_SECONDS", 0.2)
    path = create(client, owner)
    qsts = path + "/qsts/interactive"
    opened = initialize(client, path, owner)
    run = {"run_id": opened["run_id"]}
    with ThreadPoolExecutor(max_workers=2) as callers:
        def request(_):
            return client.post(qsts + "/step", headers=owner, json=step_body(run["run_id"], 0)).status_code
        assert sorted(callers.map(request, range(2))) == [200, 409]
    assert client.post(path + "/solve", headers=owner).status_code == 409
    client.portal.call(local.close_session, path.rsplit("/", 1)[-1])
    interrupted = get_until(client, qsts + "/state", owner, lambda state: state["phase"] == "interrupted")
    assert interrupted["completed_steps"] == 1
    assert interrupted["next_step_at"] is None and "worker" in interrupted["message"]
    assert client.get(path + "/controls/switches", headers=owner).status_code == 503
    assert client.post(qsts + "/step", headers=owner, json=step_body(run["run_id"], 1)).status_code == 409
    restarted = client.post(qsts + "/restart", headers=owner, json=run)
    assert restarted.status_code == 200, restarted.text
    assert restarted.json()["completed_steps"] == 0


def test_interactive_endpoints_require_internal_worker_credentials(monkeypatch):
    monkeypatch.delenv("WORKER_SHARED_TOKEN_FILE", raising=False)
    monkeypatch.setenv("WORKER_SHARED_TOKEN", "interactive-worker-fixture")
    with TestClient(worker.app) as client:
        response = client.post("/internal/sessions/missing/interactive", json={
            "type": "probe", "run_id": str(uuid4()),
        })
        assert response.status_code == 401


def test_interactive_sessions_isolate_switches_and_steps(lab):
    client, users, local = lab
    owner = users["owner"]
    paths = (create(client, owner), create(client, owner))
    runs = [initialize(client, path, owner) for path in paths]
    identities = [client.portal.call(local.session_info, path.rsplit("/", 1)[-1]).runtime_identity for path in paths]
    assert identities[0] != identities[1]
    route = "/controls/switches/Line.671692"
    command = {**step_body(runs[0]["run_id"], 0), "action": "open"}
    assert client.post(paths[0] + route, headers=owner, json=command).json()["effective_state"]["status"] == "open"
    assert client.get(paths[1] + route, headers=owner).json()["status"] == "closed"

    def advance(index):
        return client.post(paths[index] + "/qsts/interactive/step", headers=owner, json=step_body(runs[index]["run_id"], 0))

    with ThreadPoolExecutor(max_workers=2) as callers:
        results = list(callers.map(advance, range(2)))
    assert [response.status_code for response in results] == [200, 200]
    assert all(response.json()["result"]["step"] == 1 for response in results)
    assert abs(results[0].json()["result"]["total_kw"]) < abs(results[1].json()["result"]["total_kw"])
