"""Document ingestion pipeline for RAG."""

import logging
import os
from typing import List, Dict, Any
from pathlib import Path
import asyncio

# PDF processing
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# Document processing
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from orchestrator.rag.chunker import text_chunker
from orchestrator.rag.embeddings import embedding_service
from orchestrator.rag.vector_store import vector_store

logger = logging.getLogger(__name__)


class DocumentIngester:
    """Handles document ingestion into RAG pipeline."""
    
    def __init__(self):
        """Initialize document ingester."""
        self.supported_extensions = {".txt", ".md"}
        
        if PDF_AVAILABLE:
            self.supported_extensions.add(".pdf")
        
        if DOCX_AVAILABLE:
            self.supported_extensions.add(".docx")
        
        logger.info(f"[INGEST] Initialized with support for: {self.supported_extensions}")
    
    def extract_text_from_file(self, file_path: str) -> str:
        """Extract text from various file formats."""
        path = Path(file_path)
        extension = path.suffix.lower()
        
        logger.info(f"[INGEST] Extracting text from {file_path}")
        
        try:
            if extension == ".txt" or extension == ".md":
                return self._extract_from_text(file_path)
            elif extension == ".pdf" and PDF_AVAILABLE:
                return self._extract_from_pdf(file_path)
            elif extension == ".docx" and DOCX_AVAILABLE:
                return self._extract_from_docx(file_path)
            else:
                raise ValueError(f"Unsupported file format: {extension}")
        
        except Exception as e:
            logger.error(f"[INGEST] Failed to extract text from {file_path}: {e}")
            raise
    
    def _extract_from_text(self, file_path: str) -> str:
        """Extract text from .txt or .md files."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _extract_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF files."""
        if not PDF_AVAILABLE:
            raise ImportError("PyPDF2 not available for PDF processing")
        
        text = ""
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text
    
    def _extract_from_docx(self, file_path: str) -> str:
        """Extract text from DOCX files."""
        if not DOCX_AVAILABLE:
            raise ImportError("python-docx not available for DOCX processing")
        
        doc = docx.Document(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    
    async def ingest_file(self, file_path: str) -> Dict[str, Any]:
        """Ingest a single file into the RAG system."""
        logger.info(f"[INGEST] Starting ingestion of {file_path}")
        
        try:
            # Extract text
            text = self.extract_text_from_file(file_path)
            
            if not text.strip():
                logger.warning(f"[INGEST] No text extracted from {file_path}")
                return {"status": "skipped", "reason": "no_text", "chunks": 0}
            
            # Chunk text
            chunks = text_chunker.chunk_text(text, file_path)
            
            if not chunks:
                logger.warning(f"[INGEST] No chunks created from {file_path}")
                return {"status": "skipped", "reason": "no_chunks", "chunks": 0}
            
            # Generate embeddings
            chunk_texts = [chunk["text"] for chunk in chunks]
            embeddings = embedding_service.generate_embeddings(chunk_texts)
            
            # Add to vector store
            vector_store.add_chunks(chunks, embeddings)
            
            logger.info(f"[INGEST] Successfully ingested {file_path}: {len(chunks)} chunks")
            return {
                "status": "success",
                "chunks": len(chunks),
                "file_path": file_path
            }
        
        except Exception as e:
            logger.error(f"[INGEST] Failed to ingest {file_path}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "file_path": file_path
            }
    
    async def ingest_directory(self, directory_path: str) -> Dict[str, Any]:
        """Ingest all supported files from a directory."""
        logger.info(f"[INGEST] Starting directory ingestion: {directory_path}")
        
        if not os.path.exists(directory_path):
            raise FileNotFoundError(f"Directory not found: {directory_path}")
        
        # Find all supported files
        files_to_ingest = []
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                if Path(file_path).suffix.lower() in self.supported_extensions:
                    files_to_ingest.append(file_path)
        
        logger.info(f"[INGEST] Found {len(files_to_ingest)} files to ingest")
        
        # Ingest files
        results = []
        total_chunks = 0
        
        for file_path in files_to_ingest:
            result = await self.ingest_file(file_path)
            results.append(result)
            if result["status"] == "success":
                total_chunks += result["chunks"]
        
        # Save vector store
        vector_store.save()
        
        summary = {
            "total_files": len(files_to_ingest),
            "successful": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "error"]),
            "skipped": len([r for r in results if r["status"] == "skipped"]),
            "total_chunks": total_chunks,
            "results": results
        }
        
        logger.info(f"[INGEST] Directory ingestion complete: {summary}")
        return summary


# Global ingester instance
document_ingester = DocumentIngester()


async def main():
    """CLI entry point for document ingestion."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m orchestrator.rag.ingest <directory_path>")
        sys.exit(1)
    
    directory_path = sys.argv[1]
    
    # Load existing vector store
    vector_store.load()
    
    # Ingest directory
    result = await document_ingester.ingest_directory(directory_path)
    
    print(f"Ingestion complete:")
    print(f"  Files processed: {result['total_files']}")
    print(f"  Successful: {result['successful']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Skipped: {result['skipped']}")
    print(f"  Total chunks: {result['total_chunks']}")
    
    # Show vector store stats
    stats = vector_store.get_stats()
    print(f"\nVector store stats:")
    print(f"  Total chunks: {stats['total_chunks']}")
    print(f"  Sources: {len(stats['sources'])}")


if __name__ == "__main__":
    asyncio.run(main())