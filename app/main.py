from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.routes.health import router as health_router
from app.api.routes.simulations import router as simulations_router
from app.api.routes.simulations import websocket_router
from app.platform.logging_config import configure_logging

configure_logging()

app = FastAPI(
    title="OpenDSS Cloud API",
    version="0.1.0",
    description="Gemelo digital híbrido con sesiones OpenDSS aisladas y observadores WebSocket.",
)

app.include_router(health_router)
app.include_router(simulations_router)
app.include_router(websocket_router)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")
