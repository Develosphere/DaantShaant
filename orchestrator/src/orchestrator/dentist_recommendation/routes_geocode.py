"""Geocoding + address autocomplete routes (public read-only)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from orchestrator.dentist_recommendation.autocomplete_service import (
    resolve_suggestion,
    search_address_suggestions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal/geocode", tags=["geocode"])


class AddressSuggestion(BaseModel):
    place_id: str = ""
    label: str
    lat: float | None = None
    lng: float | None = None


class AutocompleteResponse(BaseModel):
    suggestions: list[AddressSuggestion]


class ResolveLocationResponse(BaseModel):
    lat: float
    lng: float
    label: str


@router.get("/autocomplete", response_model=AutocompleteResponse)
async def autocomplete_address(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(6, ge=1, le=10),
    lang: str = Query("en", max_length=10),
):
    suggestions = await search_address_suggestions(q, limit=limit, lang=lang)
    return AutocompleteResponse(
        suggestions=[AddressSuggestion(**s) for s in suggestions]
    )


@router.get("/resolve", response_model=ResolveLocationResponse)
async def resolve_address(
    label: str = Query(..., min_length=1, max_length=300),
    place_id: str | None = Query(None, max_length=200),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    lang: str = Query("en", max_length=10),
):
    resolved = await resolve_suggestion(place_id, label, lat=lat, lng=lng, lang=lang)
    if not resolved:
        raise HTTPException(status_code=404, detail="Could not resolve that address")
    return ResolveLocationResponse(**resolved)

