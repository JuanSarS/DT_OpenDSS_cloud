from pathlib import Path

from app.domain.errors import TopologyNotFoundError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
NETWORKS_ROOT = PROJECT_ROOT / "data" / "networks"

TOPOLOGIES = {
    "ieee13": NETWORKS_ROOT / "ieee13" / "IEEE13Nodeckt.dss",
}


def resolve_topology(name: str) -> Path:
    key = name.strip().lower()
    path = TOPOLOGIES.get(key)
    if path is None:
        raise TopologyNotFoundError(
            f"Topología '{name}' no registrada. Disponibles: {sorted(TOPOLOGIES)}"
        )

    if not path.exists():
        raise TopologyNotFoundError(
            f"La topología '{name}' está registrada pero falta el archivo: {path}. "
            "Ejecuta: python scripts/bootstrap_ieee13.py"
        )
    return path
