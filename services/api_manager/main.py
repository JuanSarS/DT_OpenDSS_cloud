from contextlib import asynccontextmanager
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
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from services.api_manager.api.routes.health import (
    router as health_router,
)
from services.api_manager.api.routes import interactive as interactive_routes
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
from services.api_manager.auth.routes import (
    router as auth_router,
)
from services.api_manager.security.routes import (
    router as security_router,
)

from services.api_manager.platform.logging_config import (
    configure_logging,
)
from services.api_manager.platform.settings import (
    get_settings,
)
from services.api_manager.security.events import (
    SecurityEvent,
    record_security_event,
)
from services.api_manager.security.rate_limit import rate_limiter
from services.api_manager.security.proxy import external_client_ip

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await interactive_routes.simulation_service.interactive.shutdown()


app = FastAPI(
    title="OpenDSS Cloud API",
    version="0.1.0",
    description="Gemelo digital híbrido con sesiones OpenDSS aisladas y observadores WebSocket.",
    lifespan=lifespan,
)


@app.middleware("http")
async def rate_limit_requests(request: Request, call_next):
    settings = get_settings()
    if (
        not settings.rate_limit_enabled
        or request.url.path == "/health"
        or request.url.path.startswith("/static")
    ):
        return await call_next(request)
    key = external_client_ip(
        request.headers,
        request.client.host if request.client else "unknown",
    )
    retry_after = rate_limiter.check(
        f"request:{key}",
        settings.rate_limit_requests,
        settings.rate_limit_window_seconds,
    )
    if retry_after is not None:
        record_security_event(
            SecurityEvent.RATE_LIMITED.value,
            client_ip=key,
            path=request.url.path,
            status_code=429,
            detail="request rate limit",
        )
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)
if get_settings().cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(security_router)
app.include_router(metrics_router)
app.include_router(models_router)
app.include_router(simulations_router)
app.include_router(interactive_routes.router)
app.include_router(websocket_router)
app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_ROOT / "static"),
    name="static",
)

@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(FRONTEND_ROOT / "templates" / "index.html")
