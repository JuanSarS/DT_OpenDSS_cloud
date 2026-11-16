from __future__ import annotations

import os
from pathlib import Path

from packages.simulation_core.topology_catalog import (
    resolve_builtin_topology,
)


def resolve_worker_topology(
    topology: str,
) -> Path:
    name = topology.strip()

    if not name.lower().startswith("custom:"):
        return resolve_builtin_topology(name)

    parts = name.split(":", 2)

    if len(parts) != 3:
        raise ValueError(
            f"Invalid custom topology: {topology}"
        )

    _, model_id, master = parts

    root = Path(
        os.getenv(
            "CUSTOM_MODELS_DIR",
            "data/runtime/custom_models",
        )
    ).resolve()

    candidate = (
        root
        / model_id
        / master
    ).resolve()

    if candidate != root and root not in candidate.parents:
        raise ValueError(
            "Custom topology escapes model directory"
        )

    if not candidate.exists():
        raise FileNotFoundError(
            f"Custom topology not found: {candidate}"
        )

    return candidate