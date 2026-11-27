import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from packages.contracts.auth import UserRecord
from services.api_manager.api.routes import simulations
from services.api_manager.auth import dependencies, routes
from services.api_manager.auth.constants import ACCESS_COOKIE_NAME
from services.api_manager.main import app
from services.api_manager.orchestration.simulation_service import SimulationService
from services.api_manager.platform.settings import settings
from services.simulation_worker.executor import LocalSimulationExecutor


@pytest.fixture
def collaboration(monkeypatch):
    users = {
        name: UserRecord(username=name, role="user", password_hash="unused")
        for name in ("owner", "guest", "other")
    }
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.delenv("JWT_SECRET_FILE", raising=False)
    monkeypatch.setenv("JWT_SECRET", "collaboration-test-key-" * 3)
    monkeypatch.setattr(dependencies, "load_users", lambda: users)
    monkeypatch.setattr(routes, "authenticate_user", lambda name, _: users.get(name))
    monkeypatch.setattr(simulations, "load_users", lambda: users)
    monkeypatch.setattr(simulations, "simulation_service", SimulationService(LocalSimulationExecutor()))

    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as client:
        def login(username):
            response = client.post("/auth/token", data={"username": username, "password": "fixture"})
            assert response.status_code == 200
            cookie = client.cookies.get(ACCESS_COOKIE_NAME)
            assert cookie
            client.cookies.clear()
            return {"Cookie": f"{ACCESS_COOKIE_NAME}={cookie}"}

        owner, guest, other = (login(name) for name in users)
        created = client.post("/simulations", json={"topology": "ieee13"}, headers=owner)
        assert created.status_code == 201
        session_id = created.json()["session_id"]
        try:
            yield client, session_id, owner, guest, other
        finally:
            assert client.delete(f"/simulations/{session_id}", headers=owner).status_code == 204


def test_received_invitation_is_visible_only_to_its_recipient(collaboration):
    client, session_id, owner, guest, other = collaboration
    path = f"/simulations/{session_id}"
    assert client.get(path, headers=guest).status_code == 403
    invitation = client.post(f"{path}/viewers", json={"username": "guest"}, headers=owner)
    assert invitation.status_code == 200 and invitation.json() == ["guest"]
    assert client.get(f"{path}/viewers", headers=owner).json() == ["guest"]
    assert client.get(f"{path}/viewers?invited_only=true", headers=owner).json() == ["guest"]
    assert client.get(f"{path}/viewers?invited_only=true", headers=guest).status_code == 403
    assert client.get(path, headers=guest).json()["access_mode"] == "viewer"

    for actor, invited in ((guest, True), (other, False), (owner, False)):
        row = next(item for item in client.get("/simulations", headers=actor).json() if item["session_id"] == session_id)
        assert row["invited"] is invited

    assert client.post(f"{path}/solve", headers=guest).status_code == 403
    assert client.delete(path, headers=guest).status_code == 403


def test_requests_support_rejection_approval_and_duplicate_submission(collaboration):
    client, session_id, owner, guest, other = collaboration
    path = f"/simulations/{session_id}/access-requests"
    assert client.post(path, headers=guest).status_code == 202
    assert client.post(path, headers=guest).status_code == 202
    assert client.get(path, headers=owner).json() == ["guest"]
    assert client.delete(f"{path}/guest", headers=other).status_code == 403
    assert client.delete(f"{path}/guest", headers=owner).status_code == 204
    assert client.get(path, headers=owner).json() == []
    assert client.post(f"{path}/guest/approve", headers=owner).status_code == 409
    assert client.get("/simulations/missing/access-requests", headers=owner).status_code == 404

    assert client.post(path, headers=guest).status_code == 202
    assert client.post(f"{path}/guest/approve", headers=owner).json() == ["guest"]
    assert client.get(f"/simulations/{session_id}", headers=guest).status_code == 200
    assert client.get(f"/simulations/{session_id}/viewers?invited_only=true", headers=owner).json() == []
    row = next(item for item in client.get("/simulations", headers=guest).json() if item["session_id"] == session_id)
    assert row["invited"] is False


def test_removal_revokes_open_websocket_and_rest_access(collaboration):
    client, session_id, owner, guest, _ = collaboration
    path = f"/simulations/{session_id}"
    ws_path = f"wss://testserver/ws/simulations/{session_id}"
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(ws_path, headers=guest):
            pytest.fail("A user without membership connected")
    assert denied.value.code == 1008

    assert client.post(f"{path}/viewers", json={"username": "guest"}, headers=owner).status_code == 200
    with client.websocket_connect(ws_path, headers=guest) as socket:
        assert socket.receive_json()["type"] == "snapshot"
        assert client.post(f"{path}/solve", headers=owner).status_code == 200
        events = [socket.receive_json() for _ in range(5)]
        assert events[-1]["type"] == "completed"
        assert client.get(f"{path}/results", headers=guest).status_code == 200
        assert client.delete(f"{path}/viewers/guest", headers=owner).json() == []
        assert client.get(path, headers=guest).status_code == 403
        assert client.get(f"{path}/results", headers=guest).status_code == 403
        assert client.post(f"{path}/solve", headers=owner).status_code == 200
        with pytest.raises(WebSocketDisconnect) as revoked:
            socket.receive_json()
        assert revoked.value.code == 1008
