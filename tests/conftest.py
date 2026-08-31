from pathlib import Path
import pytest


@pytest.fixture(scope="session", autouse=True)
def ieee13_files_present() -> None:
    root = Path(__file__).resolve().parents[1]
    master = root / "data" / "networks" / "ieee13" / "IEEE13Nodeckt.dss"
    if not master.exists():
        pytest.fail(
            "Falta IEEE13Nodeckt.dss. Ejecuta primero: "
            "python scripts/bootstrap_ieee13.py"
        )
