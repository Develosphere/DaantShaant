"""Scan, finding, and clinical-report persistence with patient ownership."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import ClinicalReport, Scan, ScanFinding


class ScanRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_result(
        self,
        *,
        patient_user_id: UUID,
        input_mode: str,
        analysis: object,
        diagnosis: object,
        relevance: object | None = None,
    ) -> tuple[Scan, ClinicalReport]:
        scan = Scan(
            patient_user_id=patient_user_id,
            input_mode=input_mode,
            status="clinical_complete",
            mechanical_quality_score=analysis.overall_quality_score,
            ai_model=analysis.model_id,
        )
        # Persist the provider-neutral relevance verdict when available (columns
        # relevance_score / relevance_result already exist in the schema).
        if relevance is not None:
            scan.relevance_score = getattr(relevance, "relevance_score", None)
            dump = getattr(relevance, "model_dump", None)
            scan.relevance_result = (
                dump(mode="json") if callable(dump) else dict(relevance)
            )
        self.session.add(scan)
        await self.session.flush()

        for finding in analysis.findings:
            self.session.add(
                ScanFinding(
                    scan_id=scan.id,
                    finding_code=finding.label,
                    region=finding.region,
                    observation=finding.label.replace("_", " "),
                    confidence=finding.confidence,
                    raw_ai_metadata=finding.model_dump(mode="json"),
                )
            )

        report = ClinicalReport(
            scan_id=scan.id,
            patient_user_id=patient_user_id,
            verdict=diagnosis.condition_label.value,
            urgency_level=diagnosis.severity.value,
            summary=(
                f"AI screening observed {diagnosis.condition_label.value} "
                f"with {diagnosis.confidence:.0%} confidence."
            ),
            possible_concerns={
                "findings": [finding.model_dump(mode="json") for finding in analysis.findings]
            },
            recommended_actions={"action_trigger": diagnosis.action_trigger.value},
            limitations={"disclaimer": diagnosis.disclaimer},
            agent_trace_summary={"confidence": diagnosis.confidence},
        )
        self.session.add(report)
        await self.session.flush()
        return scan, report

    async def get_owned(self, scan_id: UUID, patient_user_id: UUID) -> Scan | None:
        result = await self.session.execute(
            select(Scan).where(
                Scan.id == scan_id, Scan.patient_user_id == patient_user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_owned(self, patient_user_id: UUID, limit: int = 50) -> list[Scan]:
        result = await self.session.execute(
            select(Scan)
            .where(Scan.patient_user_id == patient_user_id)
            .order_by(Scan.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def recent_reports(
        self, patient_user_id: UUID, limit: int = 5
    ) -> list[ClinicalReport]:
        result = await self.session.execute(
            select(ClinicalReport)
            .where(ClinicalReport.patient_user_id == patient_user_id)
            .order_by(ClinicalReport.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())
