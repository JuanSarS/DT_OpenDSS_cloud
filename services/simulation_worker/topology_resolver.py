import os
from pathlib import Path

from packages.common.custom_model_paths import (
    CUSTOM_TOPOLOGY,
    STAGED_CUSTOM_TOPOLOGY,
    model_file,
    model_workspace,
    relative_model_path,
    split_custom_topology,
    staging_root,
)
from packages.simulation_core.topology_catalog import PROJECT_ROOT, resolve_builtin_topology


def resolve_worker_topology(topology: str) -> tuple[Path, Path | None]:
    name = topology.strip()
    namespace = name.partition(":")[0].lower()
    if namespace not in {CUSTOM_TOPOLOGY, STAGED_CUSTOM_TOPOLOGY}:
        return resolve_builtin_topology(name), None

    model_id, master = split_custom_topology(name)
    root = PROJECT_ROOT / os.getenv("CUSTOM_MODELS_DIR", "data/runtime/custom_models")
    if namespace == STAGED_CUSTOM_TOPOLOGY:
        root = staging_root(root)
    workspace = model_workspace(root, model_id)
    path = model_file(workspace, relative_model_path(master), {".dss"})
    return path, workspace
