import ntpath
import re
from pathlib import Path, PurePosixPath


CUSTOM_TOPOLOGY = "custom"
STAGED_CUSTOM_TOPOLOGY = "custom-stage"
STAGING_DIRECTORY = ".staging"
MODEL_ID = re.compile(r"[0-9a-f]{32}")
MODEL_EXTENSIONS = {".dss", ".csv", ".txt", ".dat", ".dbl", ".json"}


class CustomModelError(ValueError):
    pass


def relative_model_path(name: str, *, base: PurePosixPath | None = None) -> PurePosixPath:
    """Resolve a relative name lexically, before consulting the filesystem."""
    name = name.replace("\\", "/")
    if not name or name.startswith("/") or re.search(r'[:<>"|?*\x00-\x1f\x7f]', name):
        raise CustomModelError("La ruta debe ser relativa al modelo.")
    parts = list(base.parts) if base is not None else []
    for part in name.split("/"):
        if part == ".":
            continue
        if part == ".." and base is not None and parts:
            parts.pop()
            continue
        if (
            not part
            or part.startswith(".")
            or ntpath.isreserved(part)
        ):
            raise CustomModelError("La ruta contiene un segmento no permitido.")
        parts.append(part)
    if not parts:
        raise CustomModelError("Falta el nombre del archivo.")
    return PurePosixPath(*parts)


def model_workspace(root: Path, model_id: str) -> Path:
    if MODEL_ID.fullmatch(model_id) is None:
        raise CustomModelError("Identificador de modelo inválido.")
    workspace = root.resolve() / model_id
    if workspace.is_symlink() or workspace.is_junction():
        raise CustomModelError("El modelo contiene un enlace de directorio.")
    if not workspace.is_dir():
        raise FileNotFoundError("No se encontró el modelo personalizado.")
    return workspace


def model_file(workspace: Path, relative: PurePosixPath, extensions: set[str]) -> Path:
    if relative.suffix.lower() not in extensions:
        raise CustomModelError("Extensión de archivo no admitida.")
    path = workspace
    for part in relative.parts:
        if not path.is_dir() or not any(entry.name == part for entry in path.iterdir()):
            raise FileNotFoundError(f"No se encontró {relative.as_posix()}. Revise las mayúsculas y la ruta.")
        path /= part
        if path.is_symlink() or path.is_junction():
            raise CustomModelError(f"No se admiten enlaces en {relative.as_posix()}.")
    if not path.is_file():
        raise FileNotFoundError(f"No se encontró el archivo {relative.as_posix()}.")
    return path


def split_custom_topology(topology: str) -> tuple[str, str]:
    parts = topology.split(":", 2)
    if len(parts) != 3 or not MODEL_ID.fullmatch(parts[1]) or not parts[2]:
        raise CustomModelError("Se requiere un identificador de modelo y su archivo master DSS.")
    return parts[1], parts[2]


def staging_root(root: Path) -> Path:
    staging = root.resolve() / STAGING_DIRECTORY
    if staging.is_symlink() or staging.is_junction():
        raise CustomModelError("El directorio de validación no admite enlaces.")
    return staging
