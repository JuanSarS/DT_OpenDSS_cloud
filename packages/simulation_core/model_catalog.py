from dataclasses import dataclass
from pathlib import Path

from packages.contracts.model_catalog import (
    BUILTIN_MODEL_SPECS,
)


@dataclass(frozen=True)
class BuiltinModel:
    id: str
    name: str
    master: Path


def builtin_models(
    networks_root: Path,
) -> dict[str, BuiltinModel]:
    return {
        key: BuiltinModel(
            id=spec.id,
            name=spec.name,
            master=(
                networks_root
                / Path(spec.master_relative)
            ),
        )
        for key, spec
        in BUILTIN_MODEL_SPECS.items()
    }