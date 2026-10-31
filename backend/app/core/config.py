"""Application settings loaded from environment variables (`.env` supported).

Secrets never live in code; `JWT_SECRET` is validated at startup (see
`jwt_secret_effective`). Relative paths (`STORAGE_DIR`, `CLASSIFIER_WEIGHTS_PATH`)
are resolved against the backend directory — never against the current working
directory of the terminal (addendum correction #10).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Development-only fallback so the app runs from a fresh clone without `.env`.
# Production (`SEVA_ENV != development`) refuses to start without a real secret.
_DEV_JWT_FALLBACK = "dev-only-insecure-secret-do-not-use-outside-development"
_PLACEHOLDER = "replace-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    seva_env: str = "development"
    database_url: str = "sqlite:///./seva.db"
    jwt_secret: str = ""
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"
    storage_dir: str = "./storage"
    classifier_weights_path: str = "../ml/models/image_classifier_v1.pt"
    service_radius_km: float = 50.0
    rate_limit_login: str = "5/minute"

    @property
    def is_development(self) -> bool:
        return self.seva_env.strip().lower() == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @staticmethod
    def _resolve(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def storage_path(self) -> Path:
        """Absolute path of the upload storage directory (outside the web root)."""
        return self._resolve(self.storage_dir)

    @property
    def classifier_weights_file(self) -> Path:
        """Absolute resolved path of the classifier weights file."""
        return self._resolve(self.classifier_weights_path)

    @property
    def jwt_secret_effective(self) -> str:
        if self.jwt_secret and self.jwt_secret != _PLACEHOLDER:
            return self.jwt_secret
        if self.is_development:
            return _DEV_JWT_FALLBACK
        raise RuntimeError(
            "JWT_SECRET is not set to a real value. refusing to start outside "
            "development without a configured secret (see .env.example)."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
