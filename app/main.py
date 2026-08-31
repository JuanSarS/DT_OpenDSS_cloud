from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.simulations import router as simulations_router
from app.platform.logging_config import configure_logging

configure_logging()

app = FastAPI(
    title="OpenDSS Cloud API",
    version="0.1.0",
    description="Semana 4: backend FastAPI con contextos OpenDSS aislados.",
)

app.include_router(health_router)
app.include_router(simulations_router)
