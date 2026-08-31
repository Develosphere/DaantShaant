"""Text chunking utilities for RAG pipeline."""

import logging
from typing import List, Dict, Any
import re

logger = logging.getLogger(__name__)


class TextChunker:
    """Handles text chunking with overlap for RAG pipeline."""
    
    def __init__(self, chunk_size: int = 500, overlap: int = 100):
        """Initialize chunker with specified parameters."""
        self.chunk_size = chunk_size
        self.overlap = overlap
        logger.info(f"[CHUNKER] Initialized with chunk_size={chunk_size}, overlap={overlap}")
    
    def chunk_text(self, text: str, source_file: str) -> List[Dict[str, Any]]:
        """Chunk text into overlapping segments."""
        logger.info(f"[CHUNKER] Chunking text from {source_file}, length: {len(text)}")
        
        # Clean and normalize text
        text = self._clean_text(text)
        
        if len(text) <= self.chunk_size:
            logger.info(f"[CHUNKER] Text fits in single chunk")
            return [{
                "text": text,
                "source_file": source_file,
                "chunk_index": 0,
                "start_char": 0,
                "end_char": len(text)
            }]
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            # Calculate end position
            end = min(start + self.chunk_size, len(text))
            
            # Try to break at sentence boundary if possible
            if end < len(text):
                # Look for sentence endings within the last 100 characters
                search_start = max(end - 100, start)
                sentence_end = self._find_sentence_boundary(text, search_start, end)
                if sentence_end > start:
                    end = sentence_end
            
            chunk_text = text[start:end].strip()
            
            if chunk_text:  # Only add non-empty chunks
                chunks.append({
                    "text": chunk_text,
                    "source_file": source_file,
                    "chunk_index": chunk_index,
                    "start_char": start,
                    "end_char": end
                })
                chunk_index += 1
            
            # Move start position with overlap
            start = max(start + self.chunk_size - self.overlap, end)
        
        logger.info(f"[CHUNKER] Created {len(chunks)} chunks from {source_file}")
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters that might interfere
        text = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)]', ' ', text)
        # Remove multiple spaces
        text = re.sub(r' +', ' ', text)
        return text.strip()
    
    def _find_sentence_boundary(self, text: str, start: int, end: int) -> int:
        """Find the best sentence boundary within the range."""
        # Look for sentence endings (., !, ?)
        sentence_endings = ['.', '!', '?']
        
        # Search backwards from end
        for i in range(end - 1, start - 1, -1):
            if text[i] in sentence_endings:
                # Make sure it's not an abbreviation (simple check)
                if i + 1 < len(text) and text[i + 1] == ' ':
                    return i + 1
        
        # If no sentence boundary found, look for other boundaries
        other_boundaries = ['\n', ';', ',']
        for i in range(end - 1, start - 1, -1):
            if text[i] in other_boundaries:
                return i + 1
        
        # No good boundary found, return original end
        return end


# Global chunker instance
text_chunker = TextChunker()