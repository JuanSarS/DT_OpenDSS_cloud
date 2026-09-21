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
    allow_custom_models: bool = True
    custom_models_dir: Path = Path("data/runtime/custom_models")
    cors_origins: str = ""
    def __init__(self, **values: object) -> None:
        defaults = {
            "app_host": "0.0.0.0",
            "app_port": 8000,
            "log_level": "INFO",
            "recycle_threshold": 162,
            "max_active_simulations": 32,
            "max_upload_mb": 25,
            "max_upload_files": 500,
            "allow_custom_models": True,
            "custom_models_dir": Path("data/runtime/custom_models"),
            "cors_origins": "",
        }
        names = {
            "app_host": "APP_HOST", "app_port": "APP_PORT", "log_level": "LOG_LEVEL",
            "recycle_threshold": "RECYCLE_THRESHOLD", "max_active_simulations": "MAX_ACTIVE_SIMULATIONS",
            "max_upload_mb": "MAX_UPLOAD_MB", "max_upload_files": "MAX_UPLOAD_FILES",
            "allow_custom_models": "ALLOW_CUSTOM_MODELS", "custom_models_dir": "CUSTOM_MODELS_DIR",
            "cors_origins": "CORS_ORIGINS",
        }
        for field_name, env_name in names.items():
            if env_name in os.environ:
                defaults[field_name] = os.environ[env_name]
        defaults.update(values)
        for field_name in ("app_port", "recycle_threshold", "max_active_simulations", "max_upload_mb", "max_upload_files"):
            defaults[field_name] = int(defaults[field_name])
        defaults["allow_custom_models"] = str(defaults["allow_custom_models"]).lower() not in {"0", "false", "no"}
        defaults["custom_models_dir"] = Path(defaults["custom_models_dir"])
        super().__init__(**defaults)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
