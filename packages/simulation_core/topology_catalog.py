from pathlib import Path

from packages.contracts.errors import TopologyNotFoundError
from packages.simulation_core.model_catalog import builtin_models


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NETWORKS_ROOT = PROJECT_ROOT / "data" / "networks"

TOPOLOGIES = {
    key: model.master
    for key, model in builtin_models(NETWORKS_ROOT).items()
}


def resolve_builtin_topology(name: str) -> Path:
    key = name.strip().lower()
    path = TOPOLOGIES.get(key)

    if path is None:
        raise TopologyNotFoundError(
            f"Topología '{name}' no registrada. "
            f"Disponibles: {sorted(TOPOLOGIES)}"
        )

    if not path.exists():
        raise TopologyNotFoundError(
            f"La topología '{name}' está registrada pero falta el archivo: {path}. "
            "Ejecuta: python scripts/bootstrap_ieee_models.py"
        )

    return path