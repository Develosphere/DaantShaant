"""Gemini-backed tools for dental product recommendation.

Tools:
  1. search_products_by_issue   — semantic search over product embeddings
  2. get_product_details        — fetch full product doc
  3. rank_recommendations       — Gemini reranking with reasons
  4. log_recommendation_session — persist session to MongoDB
"""

import json
import logging
from datetime import datetime, timezone

from bson import ObjectId

from orchestrator.dentist_portal.db import (
    get_portal_products_col,
    get_portal_recommendations_col,
    get_portal_sessions_col,
)
from orchestrator.recommendation_ai_system.embedding_service import (
    cosine_similarity,
    embed_text,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenAI Agents SDK decorator shim
# ---------------------------------------------------------------------------
# We are migrating to LangGraph and do not use the openai-agents SDK anymore.
# We define a dummy function_tool decorator to avoid schema errors and support direct function usage.
def function_tool(fn):
    return fn



# ---------------------------------------------------------------------------
# Tool 1: search_products_by_issue
# ---------------------------------------------------------------------------

@function_tool
async def search_products_by_issue(issue: str) -> list[dict]:
    """Search for dental products that address a specific dental issue.

    Use this FIRST when a patient describes their dental problem.

    Args:
        issue: Dental issue described by the patient (e.g. 'bleeding gums', 'tooth sensitivity')

    Returns:
        Top-10 matching products with similarity scores.
    """
    products = get_portal_products_col()
    issue_embedding = await embed_text(issue)

    cursor = products.find(
        {"status": "active", "embedding": {"$exists": True}},
        {
            "name": 1, "category": 1, "price": 1,
            "ai_description": 1, "problems_solved": 1,
            "images": 1, "embedding": 1, "dentist_id": 1,
        },
    )
    all_products = await cursor.to_list(length=500)

    scored = []
    for p in all_products:
        emb = p.get("embedding")
        if emb:
            score = cosine_similarity(issue_embedding, emb)
            scored.append({
                "product_id": str(p["_id"]),
                "name": p["name"],
                "category": p["category"],
                "price": p["price"],
                "ai_description": p.get("ai_description", ""),
                "problems_solved": p.get("problems_solved", []),
                "images": p.get("images", []),
                "similarity_score": round(score, 4),
            })

    scored.sort(key=lambda x: x["similarity_score"], reverse=True)
    logger.info("[TOOLS] search_products_by_issue: issue='%s', found %d products, top score=%.3f",
                issue, len(scored), scored[0]["similarity_score"] if scored else 0)
    return scored[:10]


# ---------------------------------------------------------------------------
# Tool 2: get_product_details
# ---------------------------------------------------------------------------

@function_tool
async def get_product_details(product_id: str) -> dict:
    """Fetch complete details for a specific product by its ID.

    Use after search_products_by_issue to get full information on a candidate.

    Args:
        product_id: MongoDB ObjectId string of the product.

    Returns:
        Full product document or error dict.
    """
    products = get_portal_products_col()
    try:
        doc = await products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        return {"error": "Invalid product_id"}

    if not doc:
        return {"error": "Product not found"}

    return {
        "product_id": str(doc["_id"]),
        "name": doc["name"],
        "category": doc["category"],
        "price": doc["price"],
        "raw_description": doc.get("raw_description", ""),
        "ai_description": doc.get("ai_description", ""),
        "problems_solved": doc.get("problems_solved", []),
        "images": doc.get("images", []),
        "dentist_id": str(doc.get("dentist_id", "")),
        "recommendation_count": doc.get("recommendation_count", 0),
        "created_at": str(doc.get("created_at", "")),
    }


# ---------------------------------------------------------------------------
# Tool 3: rank_recommendations
# ---------------------------------------------------------------------------

@function_tool
async def rank_recommendations(products: list[dict], patient_issue: str) -> list[dict]:
    """Rerank candidate products for a specific dental issue and add recommendation reasons.

    Use after search_products_by_issue to produce the final ordered list.

    Args:
        products: List of candidate products from search_products_by_issue.
        patient_issue: Original dental issue described by the patient.

    Returns:
        Top-5 reranked products each with a recommendation_reason.
    """
    from orchestrator.llm_provider import llm_provider

    product_summary = json.dumps(
        [
            {
                "product_id": p["product_id"],
                "name": p["name"],
                "ai_description": p["ai_description"],
                "problems_solved": p["problems_solved"],
                "price": p["price"],
                "similarity_score": p.get("similarity_score", 0),
            }
            for p in products[:10]
        ],
        indent=2,
    )

    prompt = (
        f"Patient Issue: {patient_issue}\n\n"
        f"Candidate Products:\n{product_summary}\n\n"
        "Rank the top 5 most relevant products. For each, write a short recommendation_reason "
        "(1-2 sentences) explaining specifically why it helps with the patient's issue.\n\n"
        'Return ONLY valid JSON — no markdown:\n'
        '[{"product_id":"...","rank":1,"recommendation_reason":"..."},...]'
    )

    try:
        raw = await llm_provider.gemini.generate(
            system_prompt="You are a dental product ranking expert. Return ONLY valid JSON arrays.",
            user_message=prompt,
            temperature=0.2,
            max_tokens=600,
        )
        # Strip markdown fences
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        ranked_raw = json.loads(text)
        ranked = ranked_raw if isinstance(ranked_raw, list) else list(ranked_raw.values())[0]
    except Exception as exc:
        logger.warning("[TOOLS] rank_recommendations LLM failed: %s — returning unranked", exc)
        # Fallback: return top 5 with generic reason
        return [
            {**p, "rank": i + 1, "recommendation_reason": f"Addresses {patient_issue} based on product description."}
            for i, p in enumerate(products[:5])
        ]

    product_map = {p["product_id"]: p for p in products}
    result = []
    for r in ranked:
        pid = r.get("product_id", "")
        if pid in product_map:
            result.append({**product_map[pid], **r})

    logger.info("[TOOLS] rank_recommendations: ranked %d products for issue='%s'", len(result), patient_issue)
    return result


# ---------------------------------------------------------------------------
# Tool 4: log_recommendation_session
# ---------------------------------------------------------------------------

@function_tool
async def log_recommendation_session(
    session_id: str,
    patient_id: str,
    issue: str,
    recommended_product_ids: list[str],
) -> dict:
    """Save the recommendation session to MongoDB for analytics.

    Always call this after producing final recommendations.

    Args:
        session_id: UUID of the current session.
        patient_id: ID of the patient.
        issue: The dental issue string.
        recommended_product_ids: List of product_id strings that were recommended.

    Returns:
        Confirmation dict with recommendation_id.
    """
    recs = get_portal_recommendations_col()
    products = get_portal_products_col()

    doc = {
        "session_id": session_id,
        "patient_id": patient_id,
        "issue": issue,
        "recommended_products": [
            {"product_id": pid, "was_purchased": False}
            for pid in recommended_product_ids
        ],
        "created_at": datetime.now(timezone.utc),
    }
    result = await recs.insert_one(doc)

    # Increment recommendation_count on each product
    for pid in recommended_product_ids:
        try:
            await products.update_one(
                {"_id": ObjectId(pid)},
                {"$inc": {"recommendation_count": 1}},
            )
        except Exception:
            pass

    logger.info("[TOOLS] Logged recommendation session %s with %d products", session_id, len(recommended_product_ids))
    return {"recommendation_id": str(result.inserted_id), "logged": True}


# ---------------------------------------------------------------------------
# LangChain / LangGraph Tools
# ---------------------------------------------------------------------------
from langchain_core.tools import tool

@tool
async def search_products_by_issue_tool(issue: str) -> list[dict]:
    """Search for dental products that address a specific dental issue.

    Args:
        issue: Dental issue described by the patient (e.g. 'bleeding gums', 'tooth sensitivity')
    """
    return await search_products_by_issue(issue)

@tool
async def get_product_details_tool(product_id: str) -> dict:
    """Fetch complete details for a specific product by its ID.

    Args:
        product_id: MongoDB ObjectId string of the product.
    """
    return await get_product_details(product_id)

@tool
async def rank_recommendations_tool(products: list[dict], patient_issue: str) -> list[dict]:
    """Rerank candidate products for a specific dental issue and add recommendation reasons.

    Args:
        products: List of candidate products.
        patient_issue: Original dental issue.
    """
    return await rank_recommendations(products, patient_issue)

@tool
async def log_recommendation_session_tool(
    session_id: str,
    patient_id: str,
    issue: str,
    recommended_product_ids: list[str],
) -> dict:
    """Save the recommendation session to MongoDB for analytics.

    Args:
        session_id: UUID of the current session.
        patient_id: ID of the patient.
        issue: The dental issue string.
        recommended_product_ids: List of product_id strings that were recommended.
    """
    return await log_recommendation_session(session_id, patient_id, issue, recommended_product_ids)

