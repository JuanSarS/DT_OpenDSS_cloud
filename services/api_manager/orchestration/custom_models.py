from __future__ import annotations

import asyncio
import io
import json
import shutil
import stat
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import UploadFile

from packages.common.custom_model_paths import (
    CUSTOM_TOPOLOGY,
    MODEL_EXTENSIONS,
    MODEL_ID,
    STAGED_CUSTOM_TOPOLOGY,
    CustomModelError,
    model_file,
    model_workspace,
    relative_model_path,
    staging_root,
)
from services.api_manager.platform.settings import get_settings

_METADATA_FILE = ".opendss-model"


class CustomModelManager:
    def __init__(self) -> None:
        self.root = get_settings().custom_models_dir.resolve()
        self.edit_locks: dict[str, asyncio.Lock] = {}

    def check_enabled(self) -> None:
        if not get_settings().allow_custom_models:
            raise CustomModelError("Los modelos personalizados están deshabilitados.")

    @contextmanager
    def _staged_workspace(self):
        workspace = staging_root(self.root) / uuid4().hex
        workspace.mkdir(parents=True, exist_ok=False)
        try:
            yield workspace
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    async def upload(self, upload: UploadFile, *, owner_id: str) -> dict:
        self.check_enabled()
        filename = PurePosixPath((upload.filename or "").replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".dss", ".zip"}:
            raise CustomModelError("Solo se aceptan archivos .dss o .zip.")
        limit = get_settings().max_upload_mb * 1024 * 1024
        data = await upload.read(limit + 1)
        if len(data) > limit:
            raise CustomModelError("La carga excede MAX_UPLOAD_MB.")

        with self._staged_workspace() as workspace:
            if suffix == ".dss":
                (workspace / "model.dss").write_bytes(data)
            else:
                self._extract_zip(data, workspace, limit)
            record = {"name": Path(filename).stem[:120], "owner_id": owner_id}
            (workspace / _METADATA_FILE).write_text(json.dumps(record), encoding="utf-8")
            metadata = self._metadata(workspace)
            if not metadata["masters"]:
                raise CustomModelError("El modelo no contiene archivos DSS.")
            workspace.rename(self.root.resolve() / workspace.name)
            return metadata

    def _extract_zip(self, data: bytes, workspace: Path, limit: int) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = archive.infolist()
                if len(members) > get_settings().max_upload_files:
                    raise CustomModelError("El ZIP excede MAX_UPLOAD_FILES.")
                if sum(member.file_size for member in members) > limit:
                    raise CustomModelError("El contenido descomprimido excede MAX_UPLOAD_MB.")

                names: dict[str, tuple[PurePosixPath, bool]] = {}
                files = []
                for member in members:
                    is_dir = member.is_dir()
                    mode = stat.S_IFMT(member.external_attr >> 16)
                    if mode not in (0, stat.S_IFDIR if is_dir else stat.S_IFREG):
                        raise CustomModelError("El ZIP contiene enlaces o archivos especiales.")
                    name = member.orig_filename
                    relative = relative_model_path(name[:-1] if is_dir and name.endswith("/") else name)
                    if not is_dir and relative.suffix.lower() not in MODEL_EXTENSIONS:
                        raise CustomModelError(f"Extensión no admitida en {relative.as_posix()}.")

                    for path in (*reversed(relative.parents[:-1]), relative):
                        directory = path != relative or is_dir
                        key = path.as_posix().casefold()
                        existing = names.get(key)
                        if existing is not None and (existing != (path, directory) or not directory):
                            raise CustomModelError(f"El ZIP contiene rutas incompatibles: {relative.as_posix()}.")
                        names[key] = (path, directory)

                    if not is_dir:
                        files.append((member, relative))

                for member, relative in files:
                    target = workspace.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output, length=64 * 1024)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise CustomModelError("No se pudo leer el ZIP. Revise su formato y cifrado.") from exc

    def _files(self, workspace: Path):
        for directory, folders, files in workspace.walk():
            for folder in folders:
                path = directory / folder
                if folder.startswith(".") or path.is_symlink() or path.is_junction():
                    raise CustomModelError("El modelo contiene directorios no admitidos.")
            for filename in files:
                if filename == _METADATA_FILE and directory == workspace:
                    continue
                path = directory / filename
                if path.is_symlink() or path.is_junction() or not path.is_file():
                    raise CustomModelError("El modelo contiene enlaces o archivos especiales.")
                if path.suffix.lower() in MODEL_EXTENSIONS:
                    relative = relative_model_path(path.relative_to(workspace).as_posix())
                    yield relative, path

    def _metadata(self, workspace: Path) -> dict:
        masters = sorted(
            (relative.as_posix() for relative, path in self._files(workspace) if path.suffix.lower() == ".dss"),
            key=str.casefold,
        )
        conventional = [
            name for name in masters
            if PurePosixPath(name).name.casefold() in {"master.dss", "main.dss"}
        ]
        record_path = workspace / _METADATA_FILE
        record = {}
        if record_path.is_symlink() or record_path.is_junction():
            raise CustomModelError("Los metadatos del modelo contienen un enlace.")
        if record_path.is_file():
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise CustomModelError("Los metadatos del modelo no se pueden leer.") from exc
            if not isinstance(record, dict):
                raise CustomModelError("Los metadatos del modelo no son válidos.")
        recommended = conventional or masters
        name = record.get("name")
        owner_id = record.get("owner_id")
        return {
            "model_id": workspace.name,
            "name": name if isinstance(name, str) and name else f"Modelo {workspace.name[:8]}",
            "owner_id": owner_id if isinstance(owner_id, str) else None,
            "source": "custom",
            "masters": masters,
            "recommended_master": recommended[0] if len(recommended) == 1 else None,
        }

    def list_models(self) -> list[dict]:
        if not get_settings().allow_custom_models or not self.root.is_dir():
            return []
        models = []
        for path in self.root.iterdir():
            if MODEL_ID.fullmatch(path.name) is None:
                continue
            try:
                metadata = self.metadata(path.name)
            except (CustomModelError, FileNotFoundError):
                continue
            if metadata["masters"]:
                models.append(metadata)
        return sorted(models, key=lambda model: (model["name"].casefold(), model["model_id"]))

    def metadata(self, model_id: str) -> dict:
        self.check_enabled()
        return self._metadata(model_workspace(self.root, model_id))

    def topology(self, model_id: str, master: str) -> str:
        self.check_enabled()
        workspace = model_workspace(self.root, model_id)
        relative = relative_model_path(master)
        model_file(workspace, relative, {".dss"})
        return f"{CUSTOM_TOPOLOGY}:{model_id}:{relative.as_posix()}"

    def read_file(self, model_id: str, name: str) -> str:
        self.check_enabled()
        workspace = model_workspace(self.root, model_id)
        path = model_file(workspace, relative_model_path(name), {".dss"})
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CustomModelError("El archivo DSS debe estar codificado en UTF-8.") from exc

    @contextmanager
    def stage_edit(self, model_id: str, name: str, content: str, master: str):
        self.check_enabled()
        workspace = model_workspace(self.root, model_id)
        relative = relative_model_path(name)
        entrypoint = relative_model_path(master)
        target = model_file(workspace, relative, {".dss"})
        model_file(workspace, entrypoint, {".dss"})

        files = list(self._files(workspace))
        size = len(content.encode("utf-8")) + sum(path.stat().st_size for key, path in files if key != relative)
        settings = get_settings()
        if len(files) > settings.max_upload_files or size > settings.max_upload_mb * 1024 * 1024:
            raise CustomModelError("El modelo editado excede los límites de carga.")

        with self._staged_workspace() as staged:
            for key, source in files:
                destination = staged.joinpath(*key.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if key == relative:
                    destination.write_text(content, encoding="utf-8", newline="\n")
                else:
                    shutil.copyfile(source, destination)

            yield f"{STAGED_CUSTOM_TOPOLOGY}:{staged.name}:{entrypoint.as_posix()}"
            staged.joinpath(*relative.parts).replace(target)


custom_model_manager = CustomModelManager()
