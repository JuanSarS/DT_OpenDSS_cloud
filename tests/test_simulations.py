import asyncio

import httpx
import pytest

from app.main import app
from app.orchestration.container import simulation_service


@pytest.mark.anyio
async def test_parallel_creation_has_distinct_isolated_contexts() -> None:
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        r_low, r_high = await asyncio.gather(
            client.post(
                "/simulations",
                json={"topology": "ieee13", "load_multiplier": 0.8},
            ),
            client.post(
                "/simulations",
                json={"topology": "ieee13", "load_multiplier": 1.2},
            ),
        )

        assert r_low.status_code == 201
        assert r_high.status_code == 201

        low = r_low.json()
        high = r_high.json()

        assert low["session_id"] != high["session_id"]

        # Stronger than checking IDs only: the underlying native contexts differ.
        assert (
            simulation_service.get_engine_identity(low["session_id"])
            != simulation_service.get_engine_identity(high["session_id"])
        )

        # Different state stays attached to the right context.
        assert simulation_service.get_load_multiplier(low["session_id"]) == pytest.approx(0.8)
        assert simulation_service.get_load_multiplier(high["session_id"]) == pytest.approx(1.2)

        s_low, s_high = await asyncio.gather(
            client.post(f"/simulations/{low['session_id']}/solve"),
            client.post(f"/simulations/{high['session_id']}/solve"),
        )

        assert s_low.status_code == 200
        assert s_high.status_code == 200

        low_result = s_low.json()
        high_result = s_high.json()

        assert low_result["converged"] is True
        assert high_result["converged"] is True
        assert low_result["load_multiplier"] == pytest.approx(0.8)
        assert high_result["load_multiplier"] == pytest.approx(1.2)

        # Same feeder + different load multiplier => different electrical result.
        assert low_result["total_power_kw"] != pytest.approx(
            high_result["total_power_kw"]
        )

        assert len(low_result["voltages"]) > 0
        assert len(low_result["currents"]) > 0


@pytest.mark.anyio
async def test_unknown_session_returns_404() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post("/simulations/does-not-exist/solve")

    assert response.status_code == 404
