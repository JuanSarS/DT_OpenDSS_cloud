from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import UploadFile


from services.api_manager.platform.settings  import get_settings

ALLOWED_EXTENSIONS = {".dss", ".csv", ".txt", ".dat", ".dbl", ".json"}


class CustomModelError(ValueError):
    pass


def _safe_relative(name: str) -> Path:
    if not name or Path(name).is_absolute() or re.match(r"^[A-Za-z]:", name):
        raise CustomModelError("La ruta del archivo no es relativa")
    path = PurePosixPath(name.replace("\\", "/"))
    if any(part in {"", ".", ".."} for part in path.parts):
        raise CustomModelError("La ruta contiene segmentos no permitidos")
    result = Path(*path.parts)
    if result.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise CustomModelError(f"Extensión no permitida: {result.suffix}")
    return result


class CustomModelManager:
    def __init__(self) -> None:
        self.root = get_settings().custom_models_dir

    def _workspace(self, model_id: str) -> Path:
        workspace = (self.root / model_id).resolve()
        if workspace.parent != self.root.resolve():
            raise CustomModelError("Workspace inválido")
        if not workspace.is_dir():
            raise FileNotFoundError(model_id)
        return workspace

    async def upload(self, upload: UploadFile) -> dict:
        if not get_settings().allow_custom_models:
            raise CustomModelError("Los modelos personalizados están deshabilitados")
        filename = upload.filename or ""
        suffix = Path(filename).suffix.lower()
        if suffix not in {".dss", ".zip"}:
            raise CustomModelError("Solo se aceptan archivos .dss o .zip")
        model_id = uuid4().hex
        workspace = (self.root / model_id).resolve()
        workspace.mkdir(parents=True, exist_ok=False)
        try:
            data = await upload.read()
            if len(data) > get_settings().max_upload_mb * 1024 * 1024:
                raise CustomModelError("La carga excede MAX_UPLOAD_MB")
            if suffix == ".dss":
                (workspace / "model.dss").write_bytes(data)
            else:
                self._extract_zip(data, workspace)
            masters = sorted(workspace.rglob("*.dss"))
            if not masters:
                raise CustomModelError("El modelo no contiene archivos .dss")
            return self._metadata(model_id, workspace, masters)
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    def _extract_zip(self, data: bytes, workspace: Path) -> None:
        import io

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) > get_settings().max_upload_files:
                raise CustomModelError("El ZIP excede MAX_UPLOAD_FILES")
            for member in members:
                relative = _safe_relative(member.filename)
                target = (workspace / relative).resolve()
                if workspace not in target.parents:
                    raise CustomModelError("ZIP Slip detectado")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))

    def _metadata(self, model_id: str, workspace: Path, masters: list[Path]) -> dict:
        return {
            "model_id": model_id,
            "source": "custom",
            "masters": [str(path.relative_to(workspace)) for path in masters],
            "workspace": str(workspace),
        }

    def metadata(self, model_id: str) -> dict:
        workspace = self._workspace(model_id)
        masters = sorted(workspace.rglob("*.dss"))
        return self._metadata(model_id, workspace, masters)

    def master_path(self, model_id: str, master: str) -> Path:
        workspace = self._workspace(model_id)
        relative = _safe_relative(master)
        target = (workspace / relative).resolve()
        if workspace not in target.parents or not target.is_file() or target.suffix.lower() != ".dss":
            raise CustomModelError("Master DSS inválido")
        return target

  
    def list_files(self, model_id: str) -> list[str]:
        workspace = self._workspace(model_id)
        return [str(path.relative_to(workspace)) for path in workspace.rglob("*.dss")]

    def read_file(self, model_id: str, relative: str) -> str:
        path = self._file_path(model_id, relative)
        return path.read_text(encoding="utf-8")

    def write_file(self, model_id: str, relative: str, content: str) -> None:
        path = self._file_path(model_id, relative)
        path.write_text(content, encoding="utf-8")

    def _file_path(self, model_id: str, relative: str) -> Path:
        workspace = self._workspace(model_id)
        safe = _safe_relative(relative)
        path = (workspace / safe).resolve()
        if workspace not in path.parents or not path.is_file() or path.suffix.lower() != ".dss":
            raise CustomModelError("Archivo DSS inválido")
        return path


custom_model_manager = CustomModelManager()
