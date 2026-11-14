import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    recycle_threshold: int = 162
    max_active_simulations: int = 32
    max_upload_mb: int = 25
    max_upload_files: int = 500
    execution_backend: str = "local"
    allow_custom_models: bool = True
    custom_models_dir: Path = Path("data/runtime/custom_models")
    cors_origins: str = ""
    simulation_worker_url: str = (
    "http://127.0.0.1:8100"
    )
    simulation_worker_urls: str = ""

    simulation_worker_timeout_seconds: float = (
        600.0
    )
    jwt_expire_minutes: int = 30

    jwt_issuer: str = "opendss-cloud"

    jwt_audience: str = "opendss-api"

    auth_enabled: bool = True

    security_event_buffer_size: int = 1000
    max_concurrent_simulations_per_user: int = 2
    max_concurrent_jobs: int = 8
    admission_control_enabled: bool = True
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    login_rate_limit_requests: int = 10
    login_rate_limit_window_seconds: int = 60
    worker_max_retries: int = 1
    worker_retry_backoff_seconds: float = 2.0
    worker_retry_enabled: bool = True
    worker_test_progress_delay_ms: int = 0
    def __init__(self, **values: object) -> None:
        defaults = {
            "app_host": "0.0.0.0",
            "app_port": 8000,
            "log_level": "INFO",
            "recycle_threshold": 162,
            "max_active_simulations": 32,
            "max_upload_mb": 25,
            "max_upload_files": 500,
            "execution_backend": "local",
            "allow_custom_models": True,
            "custom_models_dir": Path("data/runtime/custom_models"),
            "cors_origins": "",
            "simulation_worker_url": "http://127.0.0.1:8100",
            "simulation_worker_urls": "",
            "simulation_worker_timeout_seconds": 600.0,
            "jwt_expire_minutes": 30,
            "jwt_issuer": "opendss-cloud",
            "jwt_audience": "opendss-api",
            "auth_enabled": True,
            "security_event_buffer_size": 1000,
            "max_concurrent_simulations_per_user": 2,
            "max_concurrent_jobs": 8,
            "admission_control_enabled": True,
            "rate_limit_enabled": True,
            "rate_limit_requests": 120,
            "rate_limit_window_seconds": 60,
            "login_rate_limit_requests": 10,
            "login_rate_limit_window_seconds": 60,
            "worker_max_retries": 1,
            "worker_retry_backoff_seconds": 2.0,
            "worker_retry_enabled": True,
            "worker_test_progress_delay_ms": 0,
        }
        names = {
            "app_host": "APP_HOST", "app_port": "APP_PORT", "log_level": "LOG_LEVEL",
            "recycle_threshold": "RECYCLE_THRESHOLD", "max_active_simulations": "MAX_ACTIVE_SIMULATIONS",
            "max_upload_mb": "MAX_UPLOAD_MB", "max_upload_files": "MAX_UPLOAD_FILES",
            "execution_backend": "EXECUTION_BACKEND",
            "allow_custom_models": "ALLOW_CUSTOM_MODELS", "custom_models_dir": "CUSTOM_MODELS_DIR",
            "cors_origins": "CORS_ORIGINS",
            "simulation_worker_url": "SIMULATION_WORKER_URL",
            "simulation_worker_urls": "SIMULATION_WORKER_URLS",
            "simulation_worker_timeout_seconds": "SIMULATION_WORKER_TIMEOUT_SECONDS",
            "jwt_expire_minutes": "JWT_EXPIRE_MINUTES", "jwt_issuer": "JWT_ISSUER", "jwt_audience": "JWT_AUDIENCE",
            "auth_enabled": "AUTH_ENABLED",
            "security_event_buffer_size": "SECURITY_EVENT_BUFFER_SIZE",
            "max_concurrent_simulations_per_user": "MAX_CONCURRENT_SIMULATIONS_PER_USER",
            "max_concurrent_jobs": "MAX_CONCURRENT_JOBS",
            "admission_control_enabled": "ADMISSION_CONTROL_ENABLED",
            "rate_limit_enabled": "RATE_LIMIT_ENABLED",
            "rate_limit_requests": "RATE_LIMIT_REQUESTS",
            "rate_limit_window_seconds": "RATE_LIMIT_WINDOW_SECONDS",
            "login_rate_limit_requests": "LOGIN_RATE_LIMIT_REQUESTS",
            "login_rate_limit_window_seconds": "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
            "worker_max_retries": "WORKER_MAX_RETRIES",
            "worker_retry_backoff_seconds": "WORKER_RETRY_BACKOFF_SECONDS",
            "worker_retry_enabled": "WORKER_RETRY_ENABLED",
            "worker_test_progress_delay_ms": "WORKER_TEST_PROGRESS_DELAY_MS",
        }
        for field_name, env_name in names.items():
            if env_name in os.environ:
                defaults[field_name] = os.environ[env_name]
        defaults.update(values)
        for field_name in (
            "app_port",
            "recycle_threshold",
            "max_active_simulations",
            "max_upload_mb",
            "max_upload_files",
            "security_event_buffer_size",
            "max_concurrent_simulations_per_user",
            "max_concurrent_jobs",
            "rate_limit_requests",
            "rate_limit_window_seconds",
            "login_rate_limit_requests",
            "login_rate_limit_window_seconds",
            "worker_max_retries",
            "worker_test_progress_delay_ms",
        ):
            defaults[field_name] = int(defaults[field_name])
        defaults["allow_custom_models"] = str(defaults["allow_custom_models"]).lower() not in {"0", "false", "no"}
        for field_name in ("auth_enabled", "admission_control_enabled", "rate_limit_enabled", "worker_retry_enabled"):
            defaults[field_name] = str(defaults[field_name]).lower() not in {"0", "false", "no"}
        defaults["worker_retry_backoff_seconds"] = float(defaults["worker_retry_backoff_seconds"])
        defaults["custom_models_dir"] = Path(defaults["custom_models_dir"])
        super().__init__(**defaults)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
