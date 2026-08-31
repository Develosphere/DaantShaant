from fastapi import FastAPI, HTTPException

from dantshaant_common.schemas import AnalyzeRequest, AnalyzeResponse
from teeth_analyzer.config import settings
from teeth_analyzer.inference import ImageQualityError, VisionBackendError, analyze_image

app = FastAPI(
    title="DantShaant Teeth Analyzer",
    version="0.1.0",
    description="Vision inference — see specs/teeth_analyzer.openapi.yaml",
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "teeth-analyzer",
        "version": "0.2.0",
        "backend": settings.backend,
        "model_id": settings.model_id,
        "gemini_configured": bool(settings.gemini_api_key),
        "fallback_to_stub": settings.fallback_to_stub,
        "env_files": list(settings.model_config.get("env_file") or []),
    }


@app.post("/v1/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return analyze_image(request)
    except ImageQualityError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "low_quality", "hint": exc.hint, "quality_score": exc.quality_score},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except VisionBackendError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "vision_backend_error", "message": str(exc)},
        ) from exc


def run() -> None:
    import uvicorn

    uvicorn.run(
        "teeth_analyzer.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    run()
