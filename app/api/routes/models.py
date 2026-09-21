from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.adapters.opendss.model_catalog import builtin_models
from app.adapters.opendss.topology_catalog import NETWORKS_ROOT
from app.orchestration.custom_models import CustomModelError, custom_model_manager

router = APIRouter(prefix="/models", tags=["models"])


class FileUpdate(BaseModel):
    content: str = Field(max_length=2_000_000)


@router.get("")
async def list_models() -> list[dict]:
    return [
        {"id": model.id, "name": model.name, "source": "builtin", "available": model.master.exists()}
        for model in builtin_models(NETWORKS_ROOT).values()
    ]


@router.post("/upload", status_code=201)
async def upload_model(file: UploadFile = File(...)) -> dict:
    try:
        return await custom_model_manager.upload(file)
    except (CustomModelError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/custom/{model_id}")
async def custom_model(model_id: str) -> dict:
    try:
        metadata = custom_model_manager.metadata(model_id)
        metadata["files"] = custom_model_manager.list_files(model_id)
        return metadata
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/custom/{model_id}/validate")
async def validate_model(model_id: str, master: str) -> dict:
    try:
        return custom_model_manager.validate(model_id, master)
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/custom/{model_id}/files/{file_path:path}")
async def read_custom_file(model_id: str, file_path: str) -> dict:
    try:
        return {"path": file_path, "content": custom_model_manager.read_file(model_id, file_path)}
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/custom/{model_id}/files/{file_path:path}")
async def update_custom_file(model_id: str, file_path: str, update: FileUpdate) -> dict:
    try:
        custom_model_manager.write_file(model_id, file_path, update.content)
        return {"path": file_path, "saved": True}
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
