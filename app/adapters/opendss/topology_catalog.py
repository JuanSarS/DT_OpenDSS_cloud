from pathlib import Path

from app.orchestration.custom_models import custom_model_manager
from packages.contracts.errors import TopologyNotFoundError
from packages.simulation_core.topology_catalog import (
    NETWORKS_ROOT,
    TOPOLOGIES,
    resolve_builtin_topology,
)


def resolve_topology(name: str) -> Path:
    key = name.strip().lower()

    if key.startswith("custom:"):
        _, model_id, master = name.split(":", 2)

        try:
            return custom_model_manager.master_path(model_id, master)
        except (FileNotFoundError, ValueError) as exc:
            raise TopologyNotFoundError(
                f"Modelo personalizado inválido: {name}"
            ) from exc

    return resolve_builtin_topology(name)