from pathlib import Path

PROJECT_ROOT = (
    Path(__file__).resolve()
    .parents[2]
)

FRONTEND_ROOT = (
    PROJECT_ROOT
    / "services"
    / "frontend"
)

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from services.api_manager.api.routes.health import (
    router as health_router,
)
from services.api_manager.api.routes.metrics import (
    router as metrics_router,
)
from services.api_manager.api.routes.models import (
    router as models_router,
)
from services.api_manager.api.routes.simulations import (
    router as simulations_router,
)
from services.api_manager.api.routes.simulations import (
    websocket_router,
)

from services.api_manager.platform.logging_config import (
    configure_logging,
)
from services.api_manager.platform.settings import (
    get_settings,
)

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
app.include_router(metrics_router)
app.include_router(models_router)
app.include_router(simulations_router)
app.include_router(websocket_router)
app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_ROOT / "static"),
    name="static",
)

@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(FRONTEND_ROOT / "templates" / "index.html")
