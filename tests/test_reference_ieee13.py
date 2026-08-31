from pathlib import Path

import httpx
import pytest
from altdss import altdss

from app.main import app


@pytest.mark.anyio
async def test_api_matches_direct_altdss_ieee13() -> None:
    """
    Acceptance criterion:
    API result must be comparable with a direct OpenDSS/AltDSS execution.

    Instead of freezing a large version-sensitive snapshot, this test runs a
    clean direct reference context and compares representative electrical values.
    """
    project_root = Path(__file__).resolve().parents[1]
    master = project_root / "data" / "networks" / "ieee13" / "IEEE13Nodeckt.dss"

    direct = altdss.NewContext()
    direct.Settings.AllowChangeDir = True
    direct(f'Redirect "{master.resolve().as_posix()}"')
    direct("Set mode=snapshot")
    direct.Solution.LoadMult = 1.0
    direct.Solution.Solve()

    assert direct.Solution.Converged
    direct_power = direct.TotalPower()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/simulations",
            json={"topology": "ieee13", "load_multiplier": 1.0},
        )
        assert created.status_code == 201
        session_id = created.json()["session_id"]

        solved = await client.post(f"/simulations/{session_id}/solve")
        assert solved.status_code == 200

    result = solved.json()

    assert result["converged"] is True
    assert result["total_power_kw"] == pytest.approx(direct_power.real, rel=1e-8, abs=1e-6)
    assert result["total_power_kvar"] == pytest.approx(direct_power.imag, rel=1e-8, abs=1e-6)

    # Sanity checks for the standard consuming IEEE13 feeder.
    assert result["total_power_kw"] < 0
    assert 3000 < abs(result["total_power_kw"]) < 5000
    assert len(result["voltages"]) >= 30
    assert len(result["currents"]) >= 20
