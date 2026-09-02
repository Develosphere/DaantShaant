"""Retrieval service for RAG pipeline."""

import logging
import time
from typing import List, Dict, Any, Optional
import asyncio

from orchestrator.rag.embeddings import embedding_service
from orchestrator.rag.vector_store import vector_store

logger = logging.getLogger(__name__)


import re

class RetrievalService:
    """Handles document retrieval for RAG pipeline."""
    
    def __init__(self, top_k: int = 2, similarity_threshold: float = 0.45):
        """Initialize retrieval service with conservative settings."""
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        logger.info(f"[RETRIEVAL] Initialized with top_k={top_k}, threshold={similarity_threshold}")
    
    def _keyword_score(self, text: str, query: str) -> float:
        """Calculate word overlap score between query and text."""
        query_words = set(re.findall(r'\b\w{3,}\b', query.lower()))
        if not query_words:
            return 0.0
        text_lower = text.lower()
        matches = sum(1 for word in query_words if word in text_lower)
        return matches / len(query_words)

    async def retrieve_relevant_chunks(
        self, 
        query: str, 
        active_issue: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant document chunks using hybrid search and issue priority."""
        logger.info(f"[RETRIEVAL] Retrieving chunks for query: '{query[:50]}' with active_issue: '{active_issue}'")
        
        # Early return if vector store is empty — skip all embedding work.
        if not vector_store.metadata:
            logger.info("[RETRIEVAL] Vector store empty, skipping embedding generation")
            return []
        
        _retrieve_t0 = time.perf_counter()
        
        candidates = []
        try:
            # 1. Semantic search with user query
            semantic_results = []
            _emb_t0 = time.perf_counter()
            try:
                query_embedding = embedding_service.generate_embedding(query)
                if query_embedding is not None:
                    semantic_results = vector_store.search(query_embedding, self.top_k * 2)
            except Exception as e:
                logger.warning(f"[RETRIEVAL] Semantic embedding failed: {e}. Falling back to degraded keyword search.")
            _embedding_ms = (time.perf_counter() - _emb_t0) * 1000
            logger.info("[CHAT_TIMING] embedding_ms=%.1f vector_search_count=%d", _embedding_ms, 1 if semantic_results else 0)
            
            # 2. Semantic search with active issue if present
            issue_results = []
            if active_issue:
                _issue_emb_t0 = time.perf_counter()
                try:
                    issue_embedding = embedding_service.generate_embedding(active_issue)
                    if issue_embedding is not None:
                        issue_results = vector_store.search(issue_embedding, self.top_k)
                except Exception as e:
                    logger.warning(f"[RETRIEVAL] Issue embedding failed: {e}")
                _issue_embedding_ms = (time.perf_counter() - _issue_emb_t0) * 1000
                logger.info("[CHAT_TIMING] issue_embedding_ms=%.1f", _issue_embedding_ms)
            
            # Combine semantic results
            all_semantic = {chunk["vector_id"]: chunk for chunk in (semantic_results + issue_results)}
            
            # 3. Hybrid scoring (Semantic + Keyword)
            search_terms = query
            if active_issue:
                search_terms += " " + active_issue
                
            # If semantic is available, score them
            if all_semantic:
                for chunk in all_semantic.values():
                    sem_score = chunk.get("similarity_score", 0.0)
                    kw_score = self._keyword_score(chunk["text"], search_terms)
                    hybrid_score = 0.7 * sem_score + 0.3 * kw_score
                    
                    # Boost if matches active issue directly
                    if active_issue and active_issue.lower() in chunk["text"].lower():
                        hybrid_score = min(hybrid_score + 0.15, 1.0)
                        
                    chunk["hybrid_score"] = hybrid_score
                    candidates.append(chunk)
            
            # 4. Pure keyword search fallback/complement
            if vector_store.metadata:
                kw_candidates = []
                for chunk in vector_store.metadata:
                    if chunk["vector_id"] in all_semantic:
                        continue
                        
                    kw_score = self._keyword_score(chunk["text"], search_terms)
                    if kw_score >= 0.4:  # Medium-high keyword match
                        chunk_copy = dict(chunk)
                        chunk_copy["similarity_score"] = 0.4
                        chunk_copy["hybrid_score"] = 0.4 * 0.7 + kw_score * 0.3
                        
                        if active_issue and active_issue.lower() in chunk["text"].lower():
                            chunk_copy["hybrid_score"] = min(chunk_copy["hybrid_score"] + 0.15, 1.0)
                            
                        kw_candidates.append(chunk_copy)
                
                kw_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
                candidates.extend(kw_candidates[:self.top_k])
            
            # Deduplicate by vector_id
            seen_ids = set()
            deduped = []
            for c in candidates:
                if c["vector_id"] not in seen_ids:
                    seen_ids.add(c["vector_id"])
                    deduped.append(c)
            
            # Sort by hybrid score
            deduped.sort(key=lambda x: x.get("hybrid_score", 0.0), reverse=True)
            
            # Filter by threshold (using hybrid score now)
            filtered = [
                c for c in deduped 
                if c.get("hybrid_score", 0.0) >= self.similarity_threshold
            ]
            
            logger.info(f"[RETRIEVAL] Retrieved and retrieved {len(filtered)} chunks (after dedup/threshold)")
            _retrieve_total_ms = (time.perf_counter() - _retrieve_t0) * 1000
            logger.info("[CHAT_TIMING] vector_search_total_ms=%.1f", _retrieve_total_ms)
            return filtered[:self.top_k]
            
        except Exception as e:
            logger.error(f"[RETRIEVAL] Failed in retrieve_relevant_chunks: {e}", exc_info=True)
            return []
    
    def summarize_context(self, chunks: List[Dict[str, Any]]) -> str:
        """Summarize retrieved chunks into concise context."""
        if not chunks:
            return ""
        
        # Deduplicate content
        seen_sentences = set()
        key_points = []
        for chunk in chunks:
            text = chunk["text"]
            sentences = text.split('. ')
            if sentences:
                key_point = sentences[0].strip()
                if key_point.lower() not in seen_sentences:
                    seen_sentences.add(key_point.lower())
                    if len(key_point) > 150:
                        key_point = key_point[:150] + "..."
                    key_points.append(key_point)
        
        if not key_points:
            return ""
        
        # Create extremely concise summary
        summary = "Key dental info: " + " | ".join(key_points[:2])
        return summary
    
    async def get_enhanced_prompt(self, user_query: str, base_prompt: str, conversation_id: Optional[str] = None) -> str:
        """Enhance a prompt with summarized RAG context."""
        logger.info(f"[RETRIEVAL] Enhancing prompt with RAG context")
        
        active_issue = None
        if conversation_id:
            try:
                from orchestrator import conversation_state as cs
                state = cs.get_state(str(conversation_id))
                if state and state.active_dental_issue:
                    active_issue = state.active_dental_issue
            except Exception as e:
                logger.warning(f"[RETRIEVAL] Failed to get conversation state: {e}")
        
        # Retrieve relevant chunks
        chunks = await self.retrieve_relevant_chunks(user_query, active_issue)
        
        if not chunks:
            logger.info(f"[RETRIEVAL] No relevant context found, using base prompt")
            return base_prompt
        
        # Summarize context instead of dumping raw chunks
        context_summary = self.summarize_context(chunks)
        
        if not context_summary:
            logger.info(f"[RETRIEVAL] No useful context extracted, using base prompt")
            return base_prompt
        
        # Inject summarized context naturally into the prompt
        enhanced_prompt = f"{base_prompt}\n\nRelevant context: {context_summary}"
        
        logger.info(f"[RETRIEVAL] Enhanced prompt with {len(chunks)} chunks (summarized)")
        return enhanced_prompt
    
    def get_stats(self) -> Dict[str, Any]:
        """Get retrieval service statistics."""
        vector_stats = vector_store.get_stats()
        return {
            "top_k": self.top_k,
            "similarity_threshold": self.similarity_threshold,
            "vector_store": vector_stats
        }


# Global retrieval service instance with conservative settings
retrieval_service = RetrievalService(top_k=2, similarity_threshold=0.5)


async def test_retrieval():
    """Test function for retrieval service."""
    # Load vector store
    vector_store.load()
    
    test_queries = [
        "Why do gums bleed while brushing?",
        "How often should I brush my teeth?",
        "What causes tooth decay?",
        "How to prevent plaque buildup?"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        chunks = await retrieval_service.retrieve_relevant_chunks(query)
        
        if chunks:
            print(f"Found {len(chunks)} relevant chunks:")
            for i, chunk in enumerate(chunks, 1):
                source = chunk["source_file"].split("/")[-1]
                score = chunk["similarity_score"]
                text = chunk["text"][:100] + "..."
                print(f"  {i}. {source} (score: {score:.3f}): {text}")
        else:
            print("No relevant chunks found")


if __name__ == "__main__":
    asyncio.run(test_retrieval())