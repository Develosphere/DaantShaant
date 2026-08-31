"""Recommendation AI routes — exposed under /portal/recommend."""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends

from orchestrator.dentist_portal.auth import get_current_user
from orchestrator.dentist_portal.models import RecommendRequest, RecommendResponse
from orchestrator.recommendation_ai_system.recommendation_agent import run_recommendation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal/recommend", tags=["recommendation-ai"])


@router.post("/", response_model=RecommendResponse)
async def recommend(
    req: RecommendRequest,
    user: dict = Depends(get_current_user),
):
    """Run DentAssist agent for a dental issue and return product recommendations."""
    session_id = req.session_id or str(uuid4())
    patient_id = user["sub"]

    logger.info("[RECOMMEND] issue='%s' patient=%s session=%s", req.issue, patient_id, session_id)
    result = await run_recommendation(req.issue, patient_id, session_id)

    return RecommendResponse(session_id=session_id, recommendations=result)


@router.get("/history", response_model=list[dict])
async def recommendation_history(user: dict = Depends(get_current_user)):
    """Get past recommendation sessions for the current user."""
    from orchestrator.dentist_portal.db import get_portal_recommendations_col

    recs = get_portal_recommendations_col()
    cursor = recs.find({"patient_id": user["sub"]}).sort("created_at", -1).limit(20)
    docs = await cursor.to_list(length=20)
    return [
        {
            "recommendation_id": str(d["_id"]),
            "session_id": d["session_id"],
            "issue": d["issue"],
            "product_count": len(d.get("recommended_products", [])),
            "created_at": d["created_at"].isoformat() if d.get("created_at") else None,
        }
        for d in docs
    ]
