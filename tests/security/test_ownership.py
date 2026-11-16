import pytest

from packages.contracts.errors import (
    AccessDeniedError,
)
from services.api_manager.orchestration.simulation_service import (
    SimulationService,
)


def _service_with_session():
    service = object.__new__(
        SimulationService
    )

    service._sessions = {}

    service._sessions["session"] = type(
        "Session",
        (),
        {
            "owner_id": "user1",
            "viewer_ids": set(),
        },
    )()

    return service


def test_session_ownership_is_enforced() -> None:
    service = _service_with_session()

    with pytest.raises(
        AccessDeniedError
    ):
        service._authorize_session(
            "session",
            "user2",
            False,
            control=True,
        )


def test_admin_bypasses_ownership() -> None:
    service = _service_with_session()

    service._authorize_session(
        "session",
        "admin",
        True,
        control=True,
    )

def test_viewer_can_read_session() -> None:
    service = _service_with_session()

    service._sessions[
        "session"
    ].viewer_ids.add(
        "user2"
    )

    service._authorize_session(
        "session",
        "user2",
        False,
        control=False,
    )


def test_viewer_cannot_control_session() -> None:
    service = _service_with_session()

    service._sessions[
        "session"
    ].viewer_ids.add(
        "user2"
    )

    with pytest.raises(
        AccessDeniedError
    ):
        service._authorize_session(
            "session",
            "user2",
            False,
            control=True,
        )