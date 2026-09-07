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


# Canonical DentalTensor Brand Identity
# Developed by Nathan Asif
DENTALTENSOR_MODEL_NAME = "DentalTensor Vision"
DENTALTENSOR_MODEL_VERSION = "1.0"
DENTALTENSOR_MODEL_DISPLAY_NAME = "DentalTensor Vision v1.0"
DENTALTENSOR_DEVELOPER = "Nathan Asif"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TEETH_ANALYZER_",
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
        populate_by_name=True,
    )

    host: str = "0.0.0.0"
    port: int = 8001

    # DentalTensor Model Identity Metadata
    dentaltensor_model_name: str = DENTALTENSOR_MODEL_NAME
    dentaltensor_model_version: str = DENTALTENSOR_MODEL_VERSION
    dentaltensor_model_display_name: str = DENTALTENSOR_MODEL_DISPLAY_NAME
    dentaltensor_developer: str = DENTALTENSOR_DEVELOPER

    # "yolo" runs the local DentalTensor Vision oral disease pathology detector (Phase 11A/B).
    # "qwen" runs legacy clinical-vision policy (Qwen primary -> Gemini fallback).
    # "stub" forces the offline deterministic backend.
    vision_provider: str = Field(
        default="yolo",
        validation_alias=AliasChoices("VISION_PROVIDER", "TEETH_ANALYZER_VISION_PROVIDER"),
    )
    backend: str = "yolo"
    model_id: str = "dentaltensor-vision-v1.0"

    # --- DentalTensor Vision Pathology Model (Primary Perception Engine) ---
    # Developed by Nathan Asif
    yolo_dental_model_path: str = Field(
        default="services/teeth_analyzer/models/oral_disease/dentaltensor_nathan_asif_v1.pt",
        validation_alias=AliasChoices(
            "YOLO_DENTAL_MODEL_PATH", "TEETH_ANALYZER_YOLO_DENTAL_MODEL_PATH"
        ),
    )
    # Global fallback threshold
    yolo_dental_confidence_threshold: float = Field(
        default=0.50,
        validation_alias=AliasChoices(
            "YOLO_DENTAL_CONFIDENCE_THRESHOLD",
            "TEETH_ANALYZER_YOLO_DENTAL_CONFIDENCE_THRESHOLD",
        ),
    )
    # Class-specific threshold overrides (Phase 11B-1)
    yolo_calculus_confidence_threshold: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "YOLO_CALCULUS_CONFIDENCE_THRESHOLD",
            "TEETH_ANALYZER_YOLO_CALCULUS_CONFIDENCE_THRESHOLD",
        ),
    )
    yolo_caries_confidence_threshold: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "YOLO_CARIES_CONFIDENCE_THRESHOLD",
            "TEETH_ANALYZER_YOLO_CARIES_CONFIDENCE_THRESHOLD",
        ),
    )
    yolo_gingivitis_confidence_threshold: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "YOLO_GINGIVITIS_CONFIDENCE_THRESHOLD",
            "TEETH_ANALYZER_YOLO_GINGIVITIS_CONFIDENCE_THRESHOLD",
        ),
    )
    yolo_discoloration_confidence_threshold: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "YOLO_DISCOLORATION_CONFIDENCE_THRESHOLD",
            "TEETH_ANALYZER_YOLO_DISCOLORATION_CONFIDENCE_THRESHOLD",
        ),
    )
    yolo_ulcer_confidence_threshold: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "YOLO_ULCER_CONFIDENCE_THRESHOLD",
            "TEETH_ANALYZER_YOLO_ULCER_CONFIDENCE_THRESHOLD",
        ),
    )
    yolo_allow_qwen_technical_fallback: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "YOLO_ALLOW_QWEN_TECHNICAL_FALLBACK",
            "TEETH_ANALYZER_YOLO_ALLOW_QWEN_TECHNICAL_FALLBACK",
        ),
    )
    yolo_debug_annotations: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "YOLO_DEBUG_ANNOTATIONS",
            "TEETH_ANALYZER_YOLO_DEBUG_ANNOTATIONS",
        ),
    )

    # --- Qwen (LEGACY/FALLBACK clinical vision) ---
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


def get_confidence_threshold(
    class_name: str, current_settings: Settings | None = None
) -> float:
    """Centralized resolver for class-specific confidence thresholds (Phase 11B-1).

    Accepts raw YOLO class names ('calculus', 'caries', 'gingivitis', 'tooth discoloration', 'ulcer')
    or normalized clinical codes ('tartar', 'cavity_suspect', 'gingivitis_signs', 'discoloration', 'oral_ulcer').
    Falls back to global yolo_dental_confidence_threshold (default: 0.50).
    """
    s = current_settings or settings
    key = class_name.strip().lower().replace("-", " ")

    if key in ("calculus", "tartar"):
        val = s.yolo_calculus_confidence_threshold
    elif key in ("caries", "cavity_suspect"):
        val = s.yolo_caries_confidence_threshold
    elif key in ("gingivitis", "gingivitis_signs"):
        val = s.yolo_gingivitis_confidence_threshold
    elif key in ("tooth discoloration", "discoloration"):
        val = s.yolo_discoloration_confidence_threshold
    elif key in ("ulcer", "oral_ulcer"):
        val = s.yolo_ulcer_confidence_threshold
    else:
        val = None

    if val is not None:
        return float(val)
    return float(s.yolo_dental_confidence_threshold)
