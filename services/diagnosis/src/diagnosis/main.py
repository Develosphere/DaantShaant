from fastapi import FastAPI

from dantshaant_common.schemas import DiagnoseRequest, DiagnoseResponse
from diagnosis.classifier import diagnose
from diagnosis.config import settings

app = FastAPI(
    title="DantShaant Diagnosis",
    version="0.1.0",
    description="Clinical classification — see specs/diagnosis.openapi.yaml",
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "diagnosis",
        "version": "0.1.0",
    }


@app.post("/v1/diagnose", response_model=DiagnoseResponse)
def diagnose_endpoint(request: DiagnoseRequest) -> DiagnoseResponse:
    return diagnose(request)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "diagnosis.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    run()
