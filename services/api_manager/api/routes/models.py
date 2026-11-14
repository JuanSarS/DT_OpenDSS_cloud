from uuid import uuid4

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field

from packages.contracts.model_catalog import (
    BUILTIN_MODEL_SPECS,
)
from services.api_manager.orchestration.container import (
    simulation_executor,
)
from services.api_manager.orchestration.custom_models import (
    CustomModelError,
    custom_model_manager,
)
from services.api_manager.auth.dependencies import AdminUser, CurrentUser
router = APIRouter(prefix="/models", tags=["models"])


class FileUpdate(BaseModel):
    content: str = Field(max_length=2_000_000)


@router.get("")
async def list_models(_: CurrentUser) -> list[dict]:
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "source": "builtin",
            "available": True,
        }
        for spec
        in BUILTIN_MODEL_SPECS.values()
    ]

@router.post("/upload", status_code=201)
async def upload_model(
    _: AdminUser,
    file: UploadFile = File(...),
) -> dict:
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


@router.post(
    "/custom/{model_id}/validate"
)
async def validate_model(
    model_id: str,
    master: str,
    _: AdminUser,
) -> dict:
    try:
        custom_model_manager.master_path(
            model_id,
            master,
        )
    except (
        CustomModelError,
        FileNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    session_id = (
        f"validation-{uuid4()}"
    )

    prepared = False

    try:
        info = (
            await simulation_executor
            .prepare_session(
                session_id=session_id,
                topology=(
                    f"custom:{model_id}:{master}"
                ),
                load_multiplier=1.0,
            )
        )

        prepared = True

        return {
            "valid": True,
            "model_id": model_id,
            "master": master,
            "model": (
                info.model_summary.model_dump()
            ),
        }

    except Exception as exc:
        return {
            "valid": False,
            "model_id": model_id,
            "master": master,
            "message": str(exc),
        }

    finally:
        if prepared:
            await (
                simulation_executor
                .close_session(session_id)
            )

@router.get("/custom/{model_id}/files/{file_path:path}")
async def read_custom_file(
    model_id: str,
    file_path: str,
    _: AdminUser,
) -> dict:
    try:
        return {"path": file_path, "content": custom_model_manager.read_file(model_id, file_path)}
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/custom/{model_id}/files/{file_path:path}")
async def update_custom_file(
    model_id: str,
    file_path: str,
    update: FileUpdate,
    _: AdminUser,
) -> dict:
    try:
        custom_model_manager.write_file(model_id, file_path, update.content)
        return {"path": file_path, "saved": True}
    except (CustomModelError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
