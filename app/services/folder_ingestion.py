"""
Folder-based PDF ingestion service for local development.
Automatically processes PDFs from ./data/pdfs folder on startup.
"""
import os
import logging
from pathlib import Path
from typing import List, Dict
from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingService
from app.services.vectorstore import VectorStoreService
from app.db.models import Document, DocumentChunk
from app.db.session import SessionLocal
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


class FolderIngestionService:
    """Handle batch PDF ingestion from a local folder."""
    
    def __init__(self):
        self.chunker = ChunkingService()
        self.embedder = EmbeddingService()
        self.vectorstore = VectorStoreService()
        self.data_folder = Path(__file__).parent.parent.parent / "data" / "pdfs"
    
    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract text from PDF file."""
        try:
            pdf_reader = PdfReader(str(pdf_path))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() or ""
            return text.strip()
        except Exception as e:
            logger.error(f"❌ Failed to extract PDF {pdf_path.name}: {e}")
            raise
    
    def normalize_text(self, text: str) -> str:
        """Clean extracted text from mojibake and artifacts."""
        import re
        
        # Repair UTF-8 mojibake
        try:
            repaired = text.encode("latin-1", errors="ignore").decode("utf-8", errors="replace")
            if repaired and repaired.count("â") < text.count("â"):
                text = repaired
        except Exception:
            pass
        
        replacements = {
            "\u00e2\u0080\u0099": "'",
            "\u00e2\u0080\u009c": '"',
            "\u00e2\u0080\u009d": '"',
            "\u00e2\u0080\u0093": "-",
            "\u00e2\u0080\u0094": "-",
            "\u00e2\u0080": '"',
            "\u00e2": "",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        
        text = re.sub(r"â([A-Za-z])", r"'\1", text)
        text = re.sub(r"\sâ\s", " - ", text)
        text = re.sub(r"\n\s*\n+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    
    def ingest_folder(self) -> Dict[str, any]:
        """
        Process all PDFs in ./data/pdfs folder.
        Returns: {
            'total': int,
            'successful': int,
            'failed': int,
            'documents': List[dict with id, title, chunks]
        }
        """
        if not self.data_folder.exists():
            logger.info(f"📁 Data folder not found: {self.data_folder}")
            return {
                'total': 0,
                'successful': 0,
                'failed': 0,
                'documents': []
            }
        
        pdf_files = list(self.data_folder.glob("*.pdf"))
        if not pdf_files:
            logger.info(f"📁 No PDFs found in {self.data_folder}")
            return {
                'total': 0,
                'successful': 0,
                'failed': 0,
                'documents': []
            }
        
        logger.info(f"📚 Found {len(pdf_files)} PDFs in {self.data_folder}")
        
        db = SessionLocal()
        results = {
            'total': len(pdf_files),
            'successful': 0,
            'failed': 0,
            'documents': []
        }
        
        try:
            for pdf_path in pdf_files:
                try:
                    logger.info(f"\n📄 Processing: {pdf_path.name}...")
                    
                    # Check if already ingested
                    existing = db.query(Document).filter_by(title=pdf_path.stem).first()
                    if existing:
                        logger.info(f"   ⏭️  Already ingested (ID: {existing.id})")
                        results['documents'].append({
                            'id': existing.id,
                            'title': existing.title,
                            'chunks': db.query(DocumentChunk).filter_by(document_id=existing.id).count(),
                            'status': 'already_ingested'
                        })
                        continue
                    
                    # Extract text
                    text = self.extract_text_from_pdf(pdf_path)
                    text = self.normalize_text(text)
                    
                    logger.info(f"   ✓ Extracted {len(text)} chars")
                    
                    # Create document record
                    doc = Document(
                        title=pdf_path.stem,
                        file_path=str(pdf_path),
                        file_type="pdf"
                    )
                    db.add(doc)
                    db.commit()
                    db.refresh(doc)
                    
                    logger.info(f"   ✓ Created document record (ID: {doc.id})")
                    
                    # Chunk text
                    chunks = self.chunker.sentence_chunk(text)
                    logger.info(f"   ✓ Generated {len(chunks)} chunks")
                    
                    # Embed chunks
                    embeddings = self.embedder.embed_texts(chunks)
                    logger.info(f"   ✓ Generated embeddings ({len(embeddings)} vectors)")
                    
                    # Store chunks in DB
                    for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                        chunk = DocumentChunk(
                            document_id=doc.id,
                            chunk_index=idx,
                            text=chunk_text,
                            embedding=embedding
                        )
                        db.add(chunk)
                    
                    db.commit()
                    logger.info(f"   ✓ Stored chunks in database")
                    
                    # Upsert to Pinecone
                    try:
                        metadatas = [{
                            'document_id': doc.id,
                            'chunk_index': idx,
                            'title': doc.title,
                            'source': 'local_folder'
                        } for idx in range(len(embeddings))]
                        
                        self.vectorstore.upsert_embeddings(embeddings, metadatas)
                        logger.info(f"   ✅ Upserted to Pinecone")
                    except Exception as e:
                        logger.warning(f"   ⚠️  Pinecone upsert failed: {e}")
                    
                    results['successful'] += 1
                    results['documents'].append({
                        'id': doc.id,
                        'title': doc.title,
                        'chunks': len(chunks),
                        'status': 'ingested'
                    })
                    
                except Exception as e:
                    logger.error(f"   ❌ Failed: {str(e)[:100]}")
                    results['failed'] += 1
        
        finally:
            db.close()
        
        return results
