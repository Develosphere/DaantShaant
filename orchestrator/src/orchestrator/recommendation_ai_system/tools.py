"""PostgreSQL-backed tools for the existing product recommendation graph."""

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from langchain_core.tools import tool

from orchestrator.db.models import ProductRecommendation
from orchestrator.db.session import async_session_factory
from orchestrator.recommendation_ai_system.embedding_service import (
    cosine_similarity,
    embed_text,
)
from orchestrator.repositories import ProductRepository, RecommendationRepository

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps runtime import cheap
    from orchestrator.ai.gateway import AIGateway

logger = logging.getLogger(__name__)

# Module-level gateway handle; resolved lazily so no provider/HTTP client is
# composed at import time. Business code depends only on the shared AIGateway.
_gateway: "AIGateway | None" = None


def _get_gateway() -> "AIGateway":
    """Return the shared AI gateway, composing it on first use (never at import)."""
    global _gateway
    if _gateway is None:
        from orchestrator.ai.factory import get_ai_gateway

        _gateway = get_ai_gateway()
    return _gateway


def function_tool(fn):
    return fn


@function_tool
async def search_products_by_issue(issue: str) -> list[dict]:
    issue_embedding = await embed_text(issue)
    async with async_session_factory() as session:
        products = await ProductRepository(session).list_active(limit=500)

    scored = []
    for product in products:
        if product.embedding:
            score = cosine_similarity(issue_embedding, product.embedding)
            scored.append(
                {
                    "product_id": str(product.id),
                    "name": product.name,
                    "category": product.category,
                    "price": float(product.price or 0),
                    "ai_description": product.ai_description or "",
                    "problems_solved": product.problems_solved or [],
                    "images": product.images or [],
                    "similarity_score": round(score, 4),
                }
            )
    scored.sort(key=lambda item: item["similarity_score"], reverse=True)
    return scored[:10]


@function_tool
async def get_product_details(product_id: str) -> dict:
    try:
        parsed_id = UUID(product_id)
    except ValueError:
        return {"error": "Invalid product_id"}
    async with async_session_factory() as session:
        product = await ProductRepository(session).get(parsed_id)
        if not product:
            return {"error": "Product not found"}
        return {
            "product_id": str(product.id),
            "name": product.name,
            "category": product.category,
            "price": float(product.price or 0),
            "raw_description": product.raw_description or "",
            "ai_description": product.ai_description or "",
            "problems_solved": product.problems_solved or [],
            "images": product.images or [],
            "dentist_id": str(product.dentist_id),
            "recommendation_count": product.recommendation_count,
            "created_at": str(product.created_at),
        }


@function_tool
async def rank_recommendations(
    products: list[dict],
    patient_issue: str,
    *,
    gateway: "AIGateway | None" = None,
) -> list[dict]:
    from orchestrator.ai.exceptions import AllProvidersFailedError
    from orchestrator.ai.schemas import ChatMessage, TextRequest

    product_summary = json.dumps(
        [
            {
                "product_id": product["product_id"],
                "name": product["name"],
                "ai_description": product["ai_description"],
                "problems_solved": product["problems_solved"],
                "price": product["price"],
                "similarity_score": product.get("similarity_score", 0),
            }
            for product in products[:10]
        ],
        indent=2,
    )
    prompt = (
        f"Patient Issue: {patient_issue}\n\nCandidate Products:\n{product_summary}\n\n"
        "Rank the top 5 most relevant products. For each, write a short "
        "recommendation_reason. Return only a valid JSON array with product_id, "
        "rank, and recommendation_reason."
    )

    gw = gateway or _get_gateway()
    request = TextRequest(
        messages=[
            ChatMessage(
                role="system",
                content="You are a dental product ranking expert. Return only JSON.",
            ),
            ChatMessage(role="user", content=prompt),
        ],
        temperature=0.2,
        max_tokens=600,
    )

    def _deterministic_ranking() -> list[dict]:
        return [
            {
                **product,
                "rank": index + 1,
                "recommendation_reason": (
                    f"Addresses {patient_issue} based on the product description."
                ),
            }
            for index, product in enumerate(products[:5])
        ]

    try:
        result = await gw.generate_text(request)
    except AllProvidersFailedError as exc:
        # Technical double failure degrades to the existing deterministic ranking.
        logger.warning("Product reranking AI unavailable (%s): %s", type(exc).__name__, exc)
        return _deterministic_ranking()

    text = (result.content or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    try:
        parsed = json.loads(text)
        ranked = parsed if isinstance(parsed, list) else list(parsed.values())[0]
    except Exception as exc:  # noqa: BLE001 - malformed model output stays recoverable
        logger.warning("Product reranking failed: %s", exc)
        return _deterministic_ranking()

    product_map = {product["product_id"]: product for product in products}
    return [
        {**product_map[item["product_id"]], **item}
        for item in ranked
        if item.get("product_id") in product_map
    ]


@function_tool
async def log_recommendation_session(
    session_id: str,
    patient_id: str,
    issue: str,
    recommended_product_ids: list[str],
) -> dict:
    try:
        parsed_session_id = UUID(session_id)
        parsed_patient_id = UUID(patient_id)
    except ValueError:
        return {"error": "Invalid session or patient ID", "logged": False}

    async with async_session_factory() as session:
        async with session.begin():
            recommendation = await RecommendationRepository(session).add_product(
                ProductRecommendation(
                    session_id=parsed_session_id,
                    patient_user_id=parsed_patient_id,
                    issue=issue,
                    recommendations={
                        "products": [
                            {"product_id": product_id, "was_purchased": False}
                            for product_id in recommended_product_ids
                        ]
                    },
                )
            )
            for product_id in recommended_product_ids:
                try:
                    product = await ProductRepository(session).get(UUID(product_id))
                except ValueError:
                    product = None
                if product:
                    product.recommendation_count += 1
    return {"recommendation_id": str(recommendation.id), "logged": True}


@tool
async def search_products_by_issue_tool(issue: str) -> list[dict]:
    """Search for products relevant to a dental issue."""
    return await search_products_by_issue(issue)


@tool
async def get_product_details_tool(product_id: str) -> dict:
    """Fetch product details by UUID."""
    return await get_product_details(product_id)


@tool
async def rank_recommendations_tool(
    products: list[dict], patient_issue: str
) -> list[dict]:
    """Rerank candidate products for a patient issue."""
    return await rank_recommendations(products, patient_issue)


@tool
async def log_recommendation_session_tool(
    session_id: str,
    patient_id: str,
    issue: str,
    recommended_product_ids: list[str],
) -> dict:
    """Persist a product recommendation session."""
    return await log_recommendation_session(
        session_id, patient_id, issue, recommended_product_ids
    )
