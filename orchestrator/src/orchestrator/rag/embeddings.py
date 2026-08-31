"""Local embedding generation using sentence-transformers."""

import logging
from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Local embedding service using sentence-transformers."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize embedding service with specified model."""
        self.model_name = model_name
        self.model = None
        logger.info(f"[EMBEDDINGS] Initializing with model: {model_name}")
    
    def _load_model(self):
        """Lazy load the embedding model."""
        if self.model is None:
            logger.info(f"[EMBEDDINGS] Loading model: {self.model_name}")
            try:
                self.model = SentenceTransformer(self.model_name)
                logger.info(f"[EMBEDDINGS] Model loaded successfully")
            except Exception as e:
                logger.warning(f"[EMBEDDINGS] Failed to load model: {e}. Embedding service will be unavailable.")
                self.model = None
    
    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for a single text, returning None if service is unavailable."""
        try:
            self._load_model()
            if self.model is None:
                return None
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding
        except Exception as e:
            logger.warning(f"[EMBEDDINGS] Failed to generate embedding: {e}. Degrading gracefully.")
            return None
    
    def generate_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """Generate embeddings for multiple texts, returning None on failure."""
        try:
            self._load_model()
            if self.model is None:
                return None
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return embeddings
        except Exception as e:
            logger.warning(f"[EMBEDDINGS] Failed to generate batch embeddings: {e}. Degrading gracefully.")
            return None
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings from this model."""
        try:
            self._load_model()
            if self.model is None:
                return 384  # Default for all-MiniLM-L6-v2
            return self.model.get_sentence_embedding_dimension()
        except Exception:
            return 384


# Global embedding service instance
embedding_service = EmbeddingService()