from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPOSITORY_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATOR_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    teeth_analyzer_url: str = "http://127.0.0.1:8001"
    diagnosis_url: str = "http://127.0.0.1:8002"
    request_timeout_seconds: float = 60.0
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )
    session_log_dir: str = "data/sessions"
    live_max_fps: float = 1.0
    live_max_analyses_per_session: int = 8
    live_max_duration_seconds: int = 120
    live_stable_frames_for_partial: int = 2

    def get_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


class PostgresSettings(BaseSettings):
    """PostgreSQL configuration — reads DATABASE_URL / DATABASE_MIGRATION_URL from .env"""
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = ""
    database_migration_url: str = ""
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 1800

    def get_migration_url(self) -> str:
        """Return DATABASE_MIGRATION_URL, falling back to DATABASE_URL."""
        return self.database_migration_url or self.database_url

    def get_runtime_url(self) -> str:
        """Return a normalized SQLAlchemy async URL or fail clearly."""
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for application persistence")
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise RuntimeError(
                "DATABASE_URL must use postgresql:// or postgresql+asyncpg://"
            )
        return self.database_url


class AuthSettings(BaseSettings):
    """Application-owned access/refresh authentication configuration."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    auth_refresh_cookie_name: str = "daantshaant_refresh"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_cookie_path: str = "/"
    auth_cookie_domain: str | None = None

    def require_jwt_secret(self) -> str:
        if not self.jwt_secret:
            raise RuntimeError("JWT_SECRET is required for authentication")
        return self.jwt_secret


class GoogleMapsSettings(BaseSettings):
    """Google Maps / Places / Geocoding — reads GOOGLE_MAPS_API_KEY from .env"""
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_maps_api_key: str = ""


# Combine service, PostgreSQL, authentication, and map settings.
class CombinedSettings(Settings, PostgresSettings, AuthSettings, GoogleMapsSettings):
    pass


settings = CombinedSettings()

