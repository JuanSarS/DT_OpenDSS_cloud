from pathlib import Path

from app.adapters.opendss.model_catalog import builtin_models
from app.domain.errors import TopologyNotFoundError
from app.orchestration.custom_models import custom_model_manager


PROJECT_ROOT = Path(__file__).resolve().parents[3]
NETWORKS_ROOT = PROJECT_ROOT / "data" / "networks"
TOPOLOGIES = {
    key: model.master for key, model in builtin_models(NETWORKS_ROOT).items()
}


def resolve_topology(name: str) -> Path:
    key = name.strip().lower()
    path = TOPOLOGIES.get(key)
    if key.startswith("custom:"):
        _, model_id, master = name.split(":", 2)
        try:
            return custom_model_manager.master_path(model_id, master)
        except (FileNotFoundError, ValueError) as exc:
            raise TopologyNotFoundError(f"Modelo personalizado inválido: {name}") from exc
    if path is None:
        raise TopologyNotFoundError(
            f"Topología '{name}' no registrada. Disponibles: {sorted(TOPOLOGIES)}"
        )
    if not path.exists():
        raise TopologyNotFoundError(
            f"La topología '{name}' está registrada pero falta el archivo: {path}. "
            "Ejecuta: python scripts/bootstrap_ieee_models.py"
        )
    return path
