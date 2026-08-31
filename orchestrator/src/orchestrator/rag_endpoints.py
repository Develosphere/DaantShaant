"""RAG management endpoints for DaantShaant orchestrator."""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from orchestrator.rag.ingest import document_ingester
from orchestrator.rag.vector_store import vector_store
from orchestrator.rag.retrieval_service import retrieval_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG"])


class IngestRequest(BaseModel):
    directory_path: str


class QueryRequest(BaseModel):
    query: str
    top_k: int = 4


@router.post("/ingest")
async def ingest_documents(
    request: IngestRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Ingest documents from a directory into the RAG system."""
    logger.info(f"[RAG API] Starting document ingestion from {request.directory_path}")
    
    try:
        # Load existing vector store
        vector_store.load()
        
        # Ingest documents
        result = await document_ingester.ingest_directory(request.directory_path)
        
        return {
            "status": "success",
            "message": f"Ingested {result['successful']} files successfully",
            "details": result
        }
    
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.directory_path}")
    except Exception as e:
        logger.error(f"[RAG API] Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/query")
async def query_knowledge_base(request: QueryRequest) -> Dict[str, Any]:
    """Query the RAG knowledge base."""
    logger.info(f"[RAG API] Querying knowledge base: {request.query[:100]}...")
    
    try:
        # Load vector store if not already loaded
        vector_store.load()
        
        # Retrieve relevant chunks
        chunks = await retrieval_service.retrieve_relevant_chunks(request.query)
        
        return {
            "status": "success",
            "query": request.query,
            "results": chunks,
            "count": len(chunks)
        }
    
    except Exception as e:
        logger.error(f"[RAG API] Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.get("/stats")
async def get_rag_stats() -> Dict[str, Any]:
    """Get RAG system statistics."""
    try:
        # Load vector store to get current stats
        vector_store.load()
        
        # Get stats from retrieval service (includes vector store stats)
        stats = retrieval_service.get_stats()
        
        return {
            "status": "success",
            "stats": stats
        }
    
    except Exception as e:
        logger.error(f"[RAG API] Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.delete("/clear")
async def clear_knowledge_base() -> Dict[str, Any]:
    """Clear the entire RAG knowledge base."""
    logger.warning("[RAG API] Clearing knowledge base")
    
    try:
        vector_store.clear()
        
        return {
            "status": "success",
            "message": "Knowledge base cleared successfully"
        }
    
    except Exception as e:
        logger.error(f"[RAG API] Failed to clear knowledge base: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear knowledge base: {str(e)}")


@router.get("/health")
async def rag_health_check() -> Dict[str, Any]:
    """Check RAG system health."""
    try:
        # Try to load vector store
        vector_store.load()
        stats = vector_store.get_stats()
        
        # Check if embedding service is working
        from orchestrator.rag.embeddings import embedding_service
        test_embedding = embedding_service.generate_embedding("test")
        
        return {
            "status": "healthy",
            "vector_store_loaded": True,
            "total_chunks": stats["total_chunks"],
            "embedding_dimension": len(test_embedding),
            "sources": len(stats["sources"])
        }
    
    except Exception as e:
        logger.error(f"[RAG API] Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }