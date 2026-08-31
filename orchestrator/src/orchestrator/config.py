from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    teeth_analyzer_url: str = "http://127.0.0.1:8001"
    diagnosis_url: str = "http://127.0.0.1:8002"
    request_timeout_seconds: float = 60.0
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    session_log_dir: str = "data/sessions"
    live_max_fps: float = 1.0
    live_max_analyses_per_session: int = 8
    live_max_duration_seconds: int = 120
    live_stable_frames_for_partial: int = 2


class MongoDBSettings(BaseSettings):
    """MongoDB configuration - no prefix, reads directly from .env"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "dantshaant"


class GoogleMapsSettings(BaseSettings):
    """Google Maps / Places / Geocoding — reads GOOGLE_MAPS_API_KEY from .env"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_maps_api_key: str = ""


# Merge MongoDB settings into main settings
class CombinedSettings(Settings, MongoDBSettings, GoogleMapsSettings):
    pass


settings = CombinedSettings()

