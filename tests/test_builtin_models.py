import httpx
import pytest

from services.api_manager.main import app


@pytest.mark.anyio
@pytest.mark.parametrize("model_id", ["ieee13", "ieee34", "ieee123"])
async def test_builtin_model_can_solve(model_id: str) -> None:

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        created = await client.post("/simulations", json={"topology": model_id})

        assert created.status_code == 201

        session_id = created.json()["session_id"]

        solved = await client.post(f"/simulations/{session_id}/solve")

        assert solved.status_code == 200

        assert solved.json()["converged"] is True

        await client.delete(f"/simulations/{session_id}")

