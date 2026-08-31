"""Embedding service for product semantic search.

Uses Google Gemini text embeddings (same API key as teeth analyzer).
Falls back to a keyword vector if Gemini is unavailable.
"""

import logging
import os
from pathlib import Path
from typing import Literal

import httpx
import numpy as np

logger = logging.getLogger(__name__)

EmbedTask = Literal["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"]


def _load_env_var(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if val:
        return val
    try:
        root = Path(__file__).resolve().parents[4]
        env_path = root / ".env"
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    except Exception as exc:
        logger.debug("[EMBEDDING] Could not read .env for %s: %s", key, exc)
    return default


async def embed_text(
    text: str,
    *,
    task_type: EmbedTask = "RETRIEVAL_QUERY",
) -> list[float]:
    """Embed text with Gemini. Use RETRIEVAL_QUERY for searches, RETRIEVAL_DOCUMENT for indexing."""
    api_key = _load_env_var("TEETH_ANALYZER_GEMINI_API_KEY")
    if not api_key:
        logger.warning("[EMBEDDING] TEETH_ANALYZER_GEMINI_API_KEY not set — using keyword fallback")
        return _keyword_vector(text)

    model = _load_env_var("TEETH_ANALYZER_GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={api_key}"
    payload = {
        "model": f"models/{model}",
        "content": {"parts": [{"text": text}]},
        "taskType": task_type,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini embed error: {resp.status_code} - {resp.text[:200]}")
            data = resp.json()
            embedding = data.get("embedding", {}).get("values")
            if not embedding:
                raise RuntimeError("Gemini returned empty embedding")
            logger.debug("[EMBEDDING] Gemini embed ok (%d dims, task=%s)", len(embedding), task_type)
            return embedding
    except Exception as exc:
        logger.warning("[EMBEDDING] Gemini embed failed: %s — using fallback", exc)
        return _keyword_vector(text)


def _keyword_vector(text: str) -> list[float]:
    """Deterministic 128-dim keyword vector from dental vocabulary."""
    VOCAB = [
        "plaque", "tartar", "cavity", "decay", "gingivitis", "gum", "bleed", "sensitive",
        "sensitivity", "whitening", "yellow", "stain", "discolor", "brush", "floss",
        "mouthwash", "fluoride", "enamel", "toothpaste", "toothbrush", "antibacterial",
        "charcoal", "whitening", "pain", "ache", "sore", "swollen", "inflamed", "fresh",
        "breath", "halitosis", "dry", "mouth", "orthodon", "brace", "aligner", "crown",
        "filling", "extraction", "root", "canal", "wisdom", "broken", "chip", "crack",
        "loose", "electric", "manual", "soft", "medium", "hard", "bristle", "head",
        "tongue", "scraper", "xylitol", "peroxide", "baking", "soda", "mint", "spearmint",
        "peppermint", "natural", "herbal", "organic", "kids", "children", "adult", "pro",
        "professional", "clinical", "dentist", "recommended", "clean", "deep", "clean",
        "interdental", "pick", "water", "flosser", "irrigator", "gel", "foam", "strip",
        "tray", "night", "guard", "grind", "jaw", "tmj", "remineraliz", "strengthen",
        "protect", "prevent", "treat", "repair", "restore", "rebuild", "sealant",
        "varnish", "rinse", "antiseptic", "chlorhexidine", "cetylpyridinium", "zinc",
        "calcium", "phosphate", "potassium", "nitrate", "arginine", "novamin",
        "hydroxyapatite", "nano", "micro", "ultra", "max", "complete", "total",
        "advanced", "sensitive", "original", "classic", "fresh", "cool", "ice",
        "extra", "plus", "pro", "elite", "premium", "budget", "value", "pack",
        "travel", "portable", "rechargeable", "battery", "sonic", "ultrasonic",
        "timer", "pressure", "sensor", "smart", "connected", "app", "bluetooth",
        "tongue", "cheek", "lip", "saliva", "xerostomia", "ulcer", "sore", "canker",
        "abscess", "infection", "bacteria", "fungal", "viral", "immune",
    ]
    text_lower = text.lower()
    vec = [1.0 if word in text_lower else 0.0 for word in VOCAB]
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)
