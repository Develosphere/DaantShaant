from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    # services/teeth_analyzer/src/teeth_analyzer/config.py → repo root
    return Path(__file__).resolve().parents[4]


def _env_files() -> tuple[str, ...]:
    root = _repo_root()
    files: list[str] = []
    for candidate in (root / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            files.append(str(candidate))
    return tuple(files)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TEETH_ANALYZER_",
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8001
    backend: str = "stub"  # stub | gemini | openrouter
    model_id: str = "stub-v0"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.0-flash-exp:free"
    fallback_to_stub: bool = False
    reject_low_quality: bool = False
    quality_gate_threshold: float = 0.45
    min_blur_variance: float = 80.0
    min_edge_px: int = 320
    max_edge_px: int = 1024


settings = Settings()
