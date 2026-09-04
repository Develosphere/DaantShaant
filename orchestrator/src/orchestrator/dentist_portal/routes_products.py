"""PostgreSQL-backed product and order routes."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import Order, Product
from orchestrator.db.session import get_db_session
from orchestrator.dentist_portal.auth import get_current_dentist, get_current_patient
from orchestrator.dentist_portal.description_generator import generate_product_description
from orchestrator.dentist_portal.models import ProductOut, ProductUpdateRequest, ProductUpload
from orchestrator.recommendation_ai_system.embedding_service import cosine_similarity, embed_text
from orchestrator.repositories import (
    DentistRepository,
    OrderRepository,
    ProductRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal/products", tags=["portal-products"])


def _product_to_out(product: Product) -> ProductOut:
    return ProductOut(
        product_id=str(product.id),
        name=product.name,
        category=product.category or "other",
        price=float(product.price or 0),
        ai_description=product.ai_description or "",
        problems_solved=product.problems_solved or [],
        images=product.images or [],
        dentist_id=str(product.dentist_id),
        status=product.status,
        view_count=product.view_count,
        recommendation_count=product.recommendation_count,
        created_at=product.created_at,
    )


async def _embed_product_in_faiss(product: Product) -> None:
    try:
        import numpy as np
        from orchestrator.rag.embeddings import embedding_service
        from orchestrator.rag.vector_store import vector_store

        text_to_embed = (
            f"Product: {product.name}. Category: {product.category}. "
            f"Price: ${float(product.price or 0):.2f}. "
            f"Description: {product.ai_description or ''}. "
            f"Problems solved: {', '.join(product.problems_solved or [])}."
        )
        embedding = embedding_service.generate_embedding(text_to_embed)
        if embedding is not None:
            vector_store.load()
            vector_store.add_chunks(
                [{
                    "source_file": "portal_products",
                    "text": text_to_embed,
                    "metadata": {
                        "product_id": str(product.id),
                        "name": product.name,
                        "category": product.category,
                        "price": float(product.price or 0),
                    },
                }],
                np.array([embedding]),
            )
            vector_store.save()
    except Exception as exc:
        logger.warning("[RAG SYNC] Product embedding sync failed: %s", exc)


@router.post("/upload", response_model=dict)
async def upload_product(
    product: ProductUpload,
    dentist_user: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
):
    dentist = await DentistRepository(session).get_by_owner(dentist_user["user_id"])
    if not dentist:
        raise HTTPException(status_code=404, detail="Dentist profile not found")
    ai_data = await generate_product_description(
        product.name, product.raw_description, product.category
    )
    embedding = await embed_text(
        ai_data["ai_description"] + " " + " ".join(ai_data["problems_solved"]),
        task_type="RETRIEVAL_DOCUMENT",
    )
    row = await ProductRepository(session).add(
        Product(
            dentist_id=dentist.id,
            name=product.name,
            category=product.category.value,
            price=Decimal(str(product.price)),
            raw_description=product.raw_description,
            ai_description=ai_data["ai_description"],
            problems_solved=ai_data["problems_solved"],
            images=product.images,
            embedding=embedding,
            status="active",
        )
    )
    await _embed_product_in_faiss(row)
    return {
        "product_id": str(row.id),
        "ai_description": row.ai_description,
        "problems_solved": row.problems_solved or [],
    }


@router.get("/", response_model=list[ProductOut])
async def list_products(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await ProductRepository(session).list_active(category=category, limit=200)
    if search:
        try:
            query_embedding = await embed_text(search)
            scored = [
                (cosine_similarity(query_embedding, row.embedding), row)
                for row in rows
                if row.embedding
            ]
            scored.sort(key=lambda item: item[0], reverse=True)
            rows = [item[1] for item in scored[:limit]]
        except Exception as exc:
            logger.warning("Semantic product search failed: %s", exc)
            rows = await ProductRepository(session).list_active(
                category=category, search=search, limit=limit
            )
    return [_product_to_out(row) for row in rows[:limit]]


@router.get("/my", response_model=list[ProductOut])
async def my_products(
    dentist: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await ProductRepository(session).list_owned(dentist["user_id"])
    return [_product_to_out(row) for row in rows]


@router.get("/orders", response_model=list)
async def list_dentist_orders(
    dentist: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await OrderRepository(session).list_for_dentist(dentist["user_id"])
    return [
        {
            "order_id": str(row.id),
            "product_id": str((row.items or {}).get("product_id", "")),
            "product_name": (row.items or {}).get("product_name", "Product"),
            "quantity": int((row.items or {}).get("quantity", 1)),
            "price": float(row.total),
            "patient_email": (row.items or {}).get("patient_email", ""),
            "patient_name": (row.items or {}).get("patient_name", "Anonymous"),
            "status": row.status,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/orders/notifications", response_model=list)
async def get_order_notifications(
    dentist: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await OrderRepository(session).list_for_dentist(dentist["user_id"])
    return [
        {
            "order_id": str(row.id),
            "product_id": str((row.items or {}).get("product_id", "")),
            "product_name": (row.items or {}).get("product_name", "Product"),
            "price": float(row.total),
            "patient_email": (row.items or {}).get("patient_email", ""),
            "patient_name": (row.items or {}).get("patient_name", "Anonymous"),
            "status": row.status,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/orders/{order_id}/status", response_model=dict)
async def update_order_status(
    order_id: UUID,
    payload: dict,
    dentist: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
):
    order = await OrderRepository(session).get_owned_by_dentist(
        order_id, dentist["user_id"]
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or not yours")
    new_status = str(payload.get("status", "shipped"))
    if new_status not in {"pending", "confirmed", "shipped", "completed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Invalid order status")
    order.status = new_status
    order.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return {"updated": True, "status": new_status}


@router.post("/{product_id}/buy", response_model=dict)
async def buy_product(
    product_id: UUID,
    patient: dict = Depends(get_current_patient),
    session: AsyncSession = Depends(get_db_session),
):
    product = await ProductRepository(session).get(product_id)
    if not product or product.status != "active":
        raise HTTPException(status_code=404, detail="Product not found")
    patient_user = await UserRepository(session).get(patient["user_id"])
    patient_name = f"{patient_user.first_name or ''} {patient_user.last_name or ''}".strip()
    order = await OrderRepository(session).add(
        Order(
            dentist_id=product.dentist_id,
            patient_user_id=patient["user_id"],
            items={
                "product_id": str(product.id),
                "product_name": product.name,
                "patient_email": patient_user.email,
                "patient_name": patient_name,
                "quantity": 1,
            },
            total=product.price or Decimal("0"),
            status="pending",
        )
    )
    return {
        "order_id": str(order.id),
        "product_name": product.name,
        "price": float(order.total),
        "status": order.status,
    }


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: UUID, session: AsyncSession = Depends(get_db_session)
):
    product = await ProductRepository(session).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.view_count += 1
    await session.flush()
    return _product_to_out(product)


@router.patch("/{product_id}", response_model=dict)
async def update_product(
    product_id: UUID,
    update: ProductUpdateRequest,
    dentist: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
):
    product = await ProductRepository(session).get_owned(product_id, dentist["user_id"])
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or not yours")
    changes = {key: value for key, value in update.model_dump().items() if value is not None}
    if not changes:
        return {"updated": False}
    if "status" in changes:
        changes["status"] = changes["status"].value
    if "price" in changes:
        changes["price"] = Decimal(str(changes["price"]))
    if "raw_description" in changes:
        ai_data = await generate_product_description(
            changes.get("name", product.name), changes["raw_description"], product.category
        )
        changes["ai_description"] = ai_data["ai_description"]
        changes["problems_solved"] = ai_data["problems_solved"]
        changes["embedding"] = await embed_text(
            ai_data["ai_description"] + " " + " ".join(ai_data["problems_solved"]),
            task_type="RETRIEVAL_DOCUMENT",
        )
    for key, value in changes.items():
        setattr(product, key, value)
    await session.flush()
    await _embed_product_in_faiss(product)
    return {"updated": True}


@router.delete("/{product_id}", response_model=dict)
async def delete_product(
    product_id: UUID,
    dentist: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
):
    repository = ProductRepository(session)
    product = await repository.get_owned(product_id, dentist["user_id"])
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or not yours")
    await repository.delete(product)
    return {"deleted": True}


@router.post("/webhook/embed", response_model=dict, include_in_schema=False)
async def webhook_embed_product(
    payload: dict,
    dentist: dict = Depends(get_current_dentist),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        product_id = UUID(str(payload.get("product_id", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid product_id") from exc
    product = await ProductRepository(session).get_owned(product_id, dentist["user_id"])
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or not yours")
    await _embed_product_in_faiss(product)
    return {"embedded": True, "product_id": str(product.id)}
