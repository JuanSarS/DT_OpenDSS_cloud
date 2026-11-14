import pytest

from packages.contracts.errors import AccessDeniedError
from services.api_manager.orchestration.simulation_service import SimulationService


def test_session_ownership_is_enforced() -> None:
    service = object.__new__(SimulationService)
    service._sessions = {}
    service._sessions["session"] = type("Session", (), {"owner_id": "user1"})()
    with pytest.raises(AccessDeniedError):
        service._authorize_session("session", "user2", False)


def test_admin_bypasses_ownership() -> None:
    service = object.__new__(SimulationService)
    service._sessions = {}
    service._sessions["session"] = type("Session", (), {"owner_id": "user1"})()
    service._authorize_session("session", "admin", True)