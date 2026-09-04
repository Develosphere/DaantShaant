"""Scan, finding, and clinical-report persistence with patient ownership."""

from uuid import UUID

from sqlalchemy import func, select
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

        urgency = None
        recommended_specialist = None
        if hasattr(diagnosis, "triage") and diagnosis.triage is not None:
            t_urgency = getattr(diagnosis.triage, "urgency_level", None)
            urgency = getattr(t_urgency, "value", str(t_urgency)) if t_urgency else None
            recommended_specialist = getattr(diagnosis.triage, "recommended_specialist", None)
        if not urgency:
            urgency = getattr(diagnosis.severity, "value", str(diagnosis.severity))

        report = ClinicalReport(
            scan_id=scan.id,
            patient_user_id=patient_user_id,
            verdict=diagnosis.condition_label.value,
            urgency_level=urgency,
            summary=(
                f"AI screening observed {diagnosis.condition_label.value} "
                f"with {diagnosis.confidence:.0%} confidence."
            ),
            possible_concerns={
                "findings": [finding.model_dump(mode="json") for finding in analysis.findings]
            },
            recommended_actions={"action_trigger": diagnosis.action_trigger.value},
            recommended_specialist=recommended_specialist or "General Dentist",
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

    async def count_scans(self, patient_user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(Scan.id)).where(Scan.patient_user_id == patient_user_id)
        )
        return int(result.scalar_one_or_none() or 0)

    async def get_latest_screening(
        self, patient_user_id: UUID
    ) -> tuple[Scan, ClinicalReport | None] | None:
        result = await self.session.execute(
            select(Scan, ClinicalReport)
            .outerjoin(ClinicalReport, ClinicalReport.scan_id == Scan.id)
            .where(Scan.patient_user_id == patient_user_id)
            .order_by(Scan.created_at.desc())
            .limit(1)
        )
        row = result.first()
        if not row:
            return None
        return row[0], row[1]

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
