"""HTTP clients for inter-service calls (orchestrator → models)."""

import httpx

from dantshaant_common.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DiagnoseRequest,
    DiagnoseResponse,
)


class TeethAnalyzerClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(f"{self._base_url}/health")
            r.raise_for_status()
            return r.json()

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base_url}/v1/analyze",
                json=request.model_dump(mode="json"),
            )
            r.raise_for_status()
            return AnalyzeResponse.model_validate(r.json())


class DiagnosisClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(f"{self._base_url}/health")
            r.raise_for_status()
            return r.json()

    async def diagnose(self, request: DiagnoseRequest) -> DiagnoseResponse:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base_url}/v1/diagnose",
                json=request.model_dump(mode="json"),
            )
            r.raise_for_status()
            return DiagnoseResponse.model_validate(r.json())
