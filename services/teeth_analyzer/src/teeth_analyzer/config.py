from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    # services/teeth_analyzer/src/teeth_analyzer/config.py -> repo root
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
    # "qwen" runs the locked clinical-vision policy (Qwen primary -> Gemini
    # technical fallback). "stub" forces the offline deterministic backend.
    backend: str = "qwen"
    model_id: str = "stub-v0"

    # --- Qwen (PRIMARY clinical vision) ---
    # Shared project env is read first; a TEETH_ANALYZER_ alias is preserved for
    # backward compatibility. Unknown or legacy provider keys are ignored
    # (extra="ignore").
    dashscope_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DASHSCOPE_API_KEY", "TEETH_ANALYZER_DASHSCOPE_API_KEY"),
    )
    qwen_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("QWEN_BASE_URL", "TEETH_ANALYZER_QWEN_BASE_URL"),
    )
    qwen_vision_model: str = Field(
        default="qwen3.7-plus",
        validation_alias=AliasChoices(
            "QWEN_VISION_MODEL", "QWEN_DEFAULT_MODEL", "TEETH_ANALYZER_QWEN_VISION_MODEL"
        ),
    )

    # --- Gemini (TECHNICAL FALLBACK clinical vision) ---
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "TEETH_ANALYZER_GEMINI_API_KEY"),
    )
    gemini_model: str = Field(
        default="gemini-flash-lite-latest",
        validation_alias=AliasChoices("GEMINI_MODEL", "TEETH_ANALYZER_GEMINI_MODEL"),
    )
    gemini_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_BASE_URL", "TEETH_ANALYZER_GEMINI_BASE_URL"),
    )

    # Shared AI request timeout (seconds).
    ai_request_timeout_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices(
            "AI_REQUEST_TIMEOUT_SECONDS", "TEETH_ANALYZER_AI_REQUEST_TIMEOUT_SECONDS"
        ),
    )

    fallback_to_stub: bool = False
    reject_low_quality: bool = False
    quality_gate_threshold: float = 0.45
    min_blur_variance: float = 80.0
    min_edge_px: int = 320
    max_edge_px: int = 1024


settings = Settings()
