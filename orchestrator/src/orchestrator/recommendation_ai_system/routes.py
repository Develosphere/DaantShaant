"""Product recommendation routes."""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.session import get_db_session
from orchestrator.dentist_portal.auth import get_current_patient
from orchestrator.dentist_portal.models import RecommendRequest, RecommendResponse
from orchestrator.recommendation_ai_system.recommendation_agent import run_recommendation
from orchestrator.repositories import RecommendationRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal/recommend", tags=["recommendation-ai"])


@router.post("/", response_model=RecommendResponse)
async def recommend(
    req: RecommendRequest, user: dict = Depends(get_current_patient)
):
    session_id = req.session_id or str(uuid4())
    result = await run_recommendation(req.issue, str(user["user_id"]), session_id)
    return RecommendResponse(session_id=session_id, recommendations=result)


@router.get("/history", response_model=list[dict])
async def recommendation_history(
    user: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
):
    recommendations = await RecommendationRepository(session).list_product_for_patient(
        user["user_id"], 20
    )
    return [
        {
            "recommendation_id": str(item.id),
            "session_id": str(item.session_id),
            "issue": item.issue,
            "product_count": len((item.recommendations or {}).get("products", [])),
            "created_at": item.created_at.isoformat(),
        }
        for item in recommendations
    ]
