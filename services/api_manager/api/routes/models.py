import asyncio
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from packages.common.custom_model_paths import CustomModelError
from packages.contracts.errors import WorkerUnavailableError
from packages.contracts.model_catalog import BUILTIN_MODEL_SPECS
from services.api_manager.auth.dependencies import AdminUser, CurrentUser
from services.api_manager.execution.remote_executor import RemoteWorkerError
from services.api_manager.orchestration.container import simulation_executor
from services.api_manager.orchestration.custom_models import custom_model_manager

router = APIRouter(prefix="/models", tags=["models"])
_BACKEND_ERRORS = (httpx.HTTPError, RemoteWorkerError, WorkerUnavailableError, OSError)
_UNAVAILABLE = "El almacenamiento o el worker de modelos no está disponible."


class FileUpdate(BaseModel):
    content: str = Field(max_length=2_000_000)
    master: str | None = None


@router.get("")
async def list_models(_: CurrentUser) -> list[dict]:
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "source": "builtin",
            "available": True,
        }
        for spec in BUILTIN_MODEL_SPECS.values()
    ]


@router.post("/upload", status_code=201)
async def upload_model(current_user: AdminUser, file: UploadFile = File(...)) -> dict:
    try:
        return await custom_model_manager.upload(file, owner_id=current_user.username)
    except CustomModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc


@router.get("/custom")
async def list_custom_models(_: AdminUser) -> list[dict]:
    try:
        return custom_model_manager.list_models()
    except OSError as exc:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc


@router.get("/custom/{model_id}")
async def custom_model(model_id: str, _: AdminUser) -> dict:
    try:
        metadata = custom_model_manager.metadata(model_id)
        return {**metadata, "files": metadata["masters"]}
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc


async def _validate_with_worker(topology: str) -> dict:
    session_id = f"validation-{uuid4()}"
    info = await simulation_executor.prepare_session(
        session_id=session_id, topology=topology, load_multiplier=1.0,
    )
    try:
        return info.model_summary.model_dump()
    finally:
        await simulation_executor.close_session(session_id)


@router.post("/custom/{model_id}/validate")
async def validate_model(model_id: str, master: str, _: AdminUser) -> dict:
    try:
        topology = custom_model_manager.topology(model_id, master)
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc

    try:
        model = await _validate_with_worker(topology)
    except (CustomModelError, FileNotFoundError) as exc:
        return {"valid": False, "model_id": model_id, "master": master, "message": str(exc)}
    except _BACKEND_ERRORS as exc:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc
    return {"valid": True, "model_id": model_id, "master": master, "model": model}


@router.get("/custom/{model_id}/files/{file_path:path}")
async def read_custom_file(model_id: str, file_path: str, _: AdminUser) -> dict:
    try:
        content = custom_model_manager.read_file(model_id, file_path)
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc
    return {"path": file_path, "content": content}


@router.put("/custom/{model_id}/files/{file_path:path}")
async def update_custom_file(model_id: str, file_path: str, update: FileUpdate, _: AdminUser) -> dict:
    try:
        master = update.master if update.master is not None else file_path
        custom_model_manager.topology(model_id, master)
        lock = custom_model_manager.edit_locks.setdefault(model_id, asyncio.Lock())
        async with lock:
            with custom_model_manager.stage_edit(model_id, file_path, update.content, master) as topology:
                await _validate_with_worker(topology)
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except _BACKEND_ERRORS as exc:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc
    return {"path": file_path, "saved": True}
