"""Product routes for Dentist Portal."""

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from orchestrator.dentist_portal.auth import get_current_dentist, get_current_user
from orchestrator.dentist_portal.db import get_portal_products_col
from orchestrator.dentist_portal.description_generator import generate_product_description
from orchestrator.dentist_portal.models import ProductOut, ProductUpdateRequest, ProductUpload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal/products", tags=["portal-products"])


def _doc_to_out(doc: dict) -> ProductOut:
    from datetime import datetime, timezone
    return ProductOut(
        product_id=str(doc["_id"]),
        name=doc["name"],
        category=doc["category"],
        price=doc["price"],
        ai_description=doc.get("ai_description", ""),
        problems_solved=doc.get("problems_solved", []),
        images=doc.get("images", []),
        dentist_id=str(doc.get("dentist_id", "")),
        status=doc.get("status", "active"),
        view_count=doc.get("view_count", 0),
        recommendation_count=doc.get("recommendation_count", 0),
        created_at=doc.get("created_at") or datetime.now(timezone.utc),
    )


async def _embed_product_in_faiss(product_id: str, doc: dict) -> None:
    """Helper to embed a product in FAISS vector store at runtime."""
    try:
        import numpy as np
        from orchestrator.rag.embeddings import embedding_service
        from orchestrator.rag.vector_store import vector_store

        text_to_embed = (
            f"Product: {doc['name']}. "
            f"Category: {doc['category']}. "
            f"Price: ${doc['price']:.2f}. "
            f"Description: {doc.get('ai_description', '')}. "
            f"Problems solved: {', '.join(doc.get('problems_solved', []))}."
        )
        
        emb = embedding_service.generate_embedding(text_to_embed)
        if emb is not None:
            vector_store.load()
            chunk = {
                "source_file": "portal_products",
                "text": text_to_embed,
                "metadata": {
                    "product_id": str(product_id),
                    "name": doc["name"],
                    "category": doc["category"],
                    "price": doc["price"]
                }
            }
            vector_store.add_chunks([chunk], np.array([emb]))
            vector_store.save()
            logger.info("[RAG SYNC] Embedded product %s in vector store successfully", product_id)
    except Exception as e:
        logger.error("[RAG SYNC] Failed to embed product %s in FAISS: %s", product_id, e)


@router.post("/upload", response_model=dict)
async def upload_product(
    product: ProductUpload,
    dentist: dict = Depends(get_current_dentist),
):
    """Dentist uploads a product. AI description is auto-generated."""
    products = get_portal_products_col()

    # 1. Generate AI description
    ai_data = await generate_product_description(
        product.name, product.raw_description, product.category
    )

    # 2. Generate embedding (via recommendation system — Gemini)
    from orchestrator.recommendation_ai_system.embedding_service import embed_text
    text_to_embed = ai_data["ai_description"] + " " + " ".join(ai_data["problems_solved"])
    embedding = await embed_text(text_to_embed, task_type="RETRIEVAL_DOCUMENT")

    # 3. Store in MongoDB
    doc = {
        **product.model_dump(),
        "category": product.category.value,
        "dentist_id": dentist["sub"],
        "ai_description": ai_data["ai_description"],
        "problems_solved": ai_data["problems_solved"],
        "embedding": embedding,
        "status": "active",
        "view_count": 0,
        "recommendation_count": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await products.insert_one(doc)
    product_id = str(result.inserted_id)

    # Sync with FAISS vector store
    await _embed_product_in_faiss(product_id, doc)

    logger.info("[PORTAL] Product uploaded: %s by dentist %s", product.name, dentist["sub"])
    return {
        "product_id": product_id,
        "ai_description": ai_data["ai_description"],
        "problems_solved": ai_data["problems_solved"],
    }


@router.get("/", response_model=list[ProductOut])
async def list_products(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
):
    """Public product listing — no auth required. Uses semantic search if 'search' query is provided."""
    products = get_portal_products_col()
    query: dict = {"status": "active"}

    if category:
        query["category"] = category

    if search:
        try:
            from orchestrator.recommendation_ai_system.embedding_service import embed_text, cosine_similarity
            search_embedding = await embed_text(search)
            
            # Find active products with an embedding
            query["embedding"] = {"$exists": True}
            cursor = products.find(query)
            docs = await cursor.to_list(length=200)
            
            scored = []
            for doc in docs:
                emb = doc.get("embedding")
                if emb:
                    score = cosine_similarity(search_embedding, emb)
                    scored.append((score, doc))
            
            # Sort by similarity score descending
            scored.sort(key=lambda x: x[0], reverse=True)
            sorted_docs = [item[1] for item in scored[:limit]]
            return [_doc_to_out(d) for d in sorted_docs]
        except Exception as e:
            logger.warning("[PORTAL] Semantic search failed: %s — falling back to standard keyword search", e)
            # Remove embedding constraint and fall back to standard text search
            query.pop("embedding", None)
            query["$text"] = {"$search": search}
            cursor = products.find(query).sort("created_at", -1).limit(limit)
            docs = await cursor.to_list(length=limit)
            return [_doc_to_out(d) for d in docs]

    cursor = products.find(query).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_doc_to_out(d) for d in docs]


@router.get("/my", response_model=list[ProductOut])
async def my_products(dentist: dict = Depends(get_current_dentist)):
    """Dentist views their own products."""
    products = get_portal_products_col()
    cursor = products.find({"dentist_id": dentist["sub"]}).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    return [_doc_to_out(d) for d in docs]


@router.get("/orders/notifications", response_model=list)
async def get_order_notifications(dentist: dict = Depends(get_current_dentist)):
    """Dentist gets all order notifications for their products."""
    from orchestrator.dentist_portal.db import get_portal_orders_col
    orders_col = get_portal_orders_col()
    
    # Fetch all orders for products belonging to this dentist
    cursor = orders_col.find({"dentist_id": dentist["sub"]}).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    
    results = []
    for d in docs:
        results.append({
            "order_id": str(d["_id"]),
            "product_id": str(d["product_id"]),
            "product_name": d["product_name"],
            "price": d["price"],
            "patient_email": d["patient_email"],
            "patient_name": d.get("patient_name", "Anonymous"),
            "status": d.get("status", "pending"),
            "created_at": d["created_at"].isoformat() if isinstance(d["created_at"], datetime) else str(d["created_at"])
        })
    return results


@router.post("/orders/{order_id}/status", response_model=dict)
async def update_order_status(
    order_id: str,
    payload: dict,
    dentist: dict = Depends(get_current_dentist),
):
    """Dentist updates an order status (e.g. pending -> shipped)."""
    from orchestrator.dentist_portal.db import get_portal_orders_col
    orders_col = get_portal_orders_col()
    
    new_status = payload.get("status", "shipped")
    
    try:
        # Verify that the order belongs to this dentist
        order = await orders_col.find_one({"_id": ObjectId(order_id), "dentist_id": dentist["sub"]})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found or not yours")
            
        await orders_col.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc)}}
        )
        return {"updated": True, "status": new_status}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail="Invalid order_id")


@router.post("/{product_id}/buy", response_model=dict)
async def buy_product(product_id: str, payload: dict):
    """Patient purchases a product, creating an order notification for the dentist."""
    from orchestrator.dentist_portal.db import get_portal_products_col, get_portal_orders_col
    products_col = get_portal_products_col()
    orders_col = get_portal_orders_col()
    
    patient_email = payload.get("patient_email")
    patient_name = payload.get("patient_name", "Anonymous")
    
    if not patient_email:
        raise HTTPException(status_code=400, detail="Missing patient_email")
        
    try:
        product = await products_col.find_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product_id")
        
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Create the order document
    order_doc = {
        "product_id": ObjectId(product_id),
        "product_name": product["name"],
        "price": product["price"],
        "dentist_id": product["dentist_id"],
        "patient_email": patient_email,
        "patient_name": patient_name,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    result = await orders_col.insert_one(order_doc)
    
    logger.info("[PORTAL] Order placed for product %s (%s) by %s", product_id, product["name"], patient_email)
    return {
        "order_id": str(result.inserted_id),
        "product_name": product["name"],
        "price": product["price"],
        "status": "pending"
    }


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: str):
    """Get a single product and increment view count."""
    products = get_portal_products_col()
    doc = await products.find_one_and_update(
        {"_id": ObjectId(product_id)},
        {"$inc": {"view_count": 1}},
        return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return _doc_to_out(doc)


@router.patch("/{product_id}", response_model=dict)
async def update_product(
    product_id: str,
    update: ProductUpdateRequest,
    dentist: dict = Depends(get_current_dentist),
):
    """Dentist updates their product."""
    products = get_portal_products_col()
    doc = await products.find_one({"_id": ObjectId(product_id), "dentist_id": dentist["sub"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found or not yours")

    changes = {k: v for k, v in update.model_dump().items() if v is not None}
    if not changes:
        return {"updated": False}

    # If description changed, regenerate AI description
    if "raw_description" in changes:
        ai_data = await generate_product_description(
            doc["name"], changes["raw_description"], doc["category"]
        )
        changes["ai_description"] = ai_data["ai_description"]
        changes["problems_solved"] = ai_data["problems_solved"]
        from orchestrator.recommendation_ai_system.embedding_service import embed_text
        changes["embedding"] = await embed_text(
            ai_data["ai_description"] + " " + " ".join(ai_data["problems_solved"]),
            task_type="RETRIEVAL_DOCUMENT",
        )

    changes["updated_at"] = datetime.now(timezone.utc)
    await products.update_one({"_id": ObjectId(product_id)}, {"$set": changes})

    # Sync with FAISS vector store
    updated_doc = await products.find_one({"_id": ObjectId(product_id)})
    if updated_doc:
        await _embed_product_in_faiss(product_id, updated_doc)

    return {"updated": True}


@router.delete("/{product_id}", response_model=dict)
async def delete_product(
    product_id: str,
    dentist: dict = Depends(get_current_dentist),
):
    products = get_portal_products_col()
    result = await products.delete_one(
        {"_id": ObjectId(product_id), "dentist_id": dentist["sub"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found or not yours")
    return {"deleted": True}


@router.post("/webhook/embed", response_model=dict)
async def webhook_embed_product(payload: dict):
    """Webhook endpoint to embed a product in the vector database at runtime."""
    product_id = payload.get("product_id")
    if not product_id:
        raise HTTPException(status_code=400, detail="Missing product_id")

    products = get_portal_products_col()
    try:
        doc = await products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product_id")

    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")

    await _embed_product_in_faiss(product_id, doc)
    return {"embedded": True, "product_id": product_id}

