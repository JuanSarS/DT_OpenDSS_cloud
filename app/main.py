from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.models import router as models_router
from app.api.routes.simulations import router as simulations_router
from app.api.routes.simulations import websocket_router
from app.platform.logging_config import configure_logging
from app.platform.settings import get_settings

configure_logging()

app = FastAPI(
    title="OpenDSS Cloud API",
    version="0.1.0",
    description="Gemelo digital híbrido con sesiones OpenDSS aisladas y observadores WebSocket.",
)
if get_settings().cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_router)
app.include_router(models_router)
app.include_router(simulations_router)
app.include_router(websocket_router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")
