"""FAISS-based vector store for local RAG."""

import logging
import os
import pickle
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import faiss
from datetime import datetime

logger = logging.getLogger(__name__)


class VectorStore:
    """FAISS-based vector store for document chunks."""
    
    def __init__(self, index_path: str = "data/rag/faiss_index"):
        """Initialize vector store."""
        self.index_path = index_path
        self.index = None
        self.metadata = []  # Store chunk metadata
        self.dimension = None
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        
        logger.info(f"[VECTOR] Initialized vector store at {index_path}")
    
    def _initialize_index(self, dimension: int):
        """Initialize FAISS index with given dimension."""
        if self.index is None:
            logger.info(f"[VECTOR] Creating new FAISS index with dimension {dimension}")
            # Use IndexFlatIP for cosine similarity (after normalization)
            self.index = faiss.IndexFlatIP(dimension)
            self.dimension = dimension
    
    def add_chunks(self, chunks: List[Dict[str, Any]], embeddings: np.ndarray):
        """Add chunks and their embeddings to the vector store."""
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings")
        
        if len(chunks) == 0:
            logger.warning("[VECTOR] No chunks to add")
            return
        
        # Initialize index if needed
        if self.index is None:
            self._initialize_index(embeddings.shape[1])
        
        # Normalize embeddings for cosine similarity
        normalized_embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        
        # Add to FAISS index
        self.index.add(normalized_embeddings.astype(np.float32))
        
        # Store metadata
        for chunk in chunks:
            chunk_metadata = {
                **chunk,
                "added_at": datetime.utcnow().isoformat(),
                "vector_id": len(self.metadata)  # Current index position
            }
            self.metadata.append(chunk_metadata)
        
        logger.info(f"[VECTOR] Added {len(chunks)} chunks to vector store. Total: {len(self.metadata)}")
    
    def search(self, query_embedding: np.ndarray, top_k: int = 4) -> List[Dict[str, Any]]:
        """Search for similar chunks."""
        if self.index is None or len(self.metadata) == 0:
            logger.warning("[VECTOR] No vectors in store for search")
            return []
        
        # Normalize query embedding
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        query_embedding = query_embedding.reshape(1, -1).astype(np.float32)
        
        # Search
        scores, indices = self.index.search(query_embedding, min(top_k, len(self.metadata)))
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self.metadata):  # Valid index
                result = {
                    **self.metadata[idx],
                    "similarity_score": float(score)
                }
                results.append(result)
        
        logger.info(f"[VECTOR] Found {len(results)} similar chunks")
        for i, result in enumerate(results):
            logger.info(f"[VECTOR] Result {i+1}: {result['source_file']} (score: {result['similarity_score']:.3f})")
        
        return results
    
    def save(self):
        """Save index and metadata to disk."""
        if self.index is None:
            logger.warning("[VECTOR] No index to save")
            return
        
        try:
            # Save FAISS index
            faiss.write_index(self.index, f"{self.index_path}.faiss")
            
            # Save metadata
            with open(f"{self.index_path}.metadata", "wb") as f:
                pickle.dump({
                    "metadata": self.metadata,
                    "dimension": self.dimension
                }, f)
            
            logger.info(f"[VECTOR] Saved index with {len(self.metadata)} vectors")
        except Exception as e:
            logger.error(f"[VECTOR] Failed to save index: {e}")
            raise
    
    def load(self):
        """Load index and metadata from disk."""
        faiss_path = f"{self.index_path}.faiss"
        metadata_path = f"{self.index_path}.metadata"
        
        if not os.path.exists(faiss_path) or not os.path.exists(metadata_path):
            logger.info("[VECTOR] No existing index found")
            return
        
        try:
            # Load FAISS index
            self.index = faiss.read_index(faiss_path)
            
            # Load metadata
            with open(metadata_path, "rb") as f:
                data = pickle.load(f)
                self.metadata = data["metadata"]
                self.dimension = data["dimension"]
            
            logger.info(f"[VECTOR] Loaded index with {len(self.metadata)} vectors")
        except Exception as e:
            logger.error(f"[VECTOR] Failed to load index: {e}")
            # Reset to empty state
            self.index = None
            self.metadata = []
            self.dimension = None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics."""
        return {
            "total_chunks": len(self.metadata),
            "dimension": self.dimension,
            "index_size": self.index.ntotal if self.index else 0,
            "sources": list(set(chunk["source_file"] for chunk in self.metadata))
        }
    
    def clear(self):
        """Clear all data from vector store."""
        self.index = None
        self.metadata = []
        self.dimension = None
        
        # Remove files if they exist
        for ext in [".faiss", ".metadata"]:
            path = f"{self.index_path}{ext}"
            if os.path.exists(path):
                os.remove(path)
        
        logger.info("[VECTOR] Cleared vector store")


# Global vector store instance
vector_store = VectorStore()