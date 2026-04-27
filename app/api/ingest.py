from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import re
import threading
import time
import logging
import tempfile
import shutil

from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingService
from app.services.vectorstore import VectorStoreService
from app.services.metadata import build_document_metadata, metadata_to_dict
from app.db.session import get_db
from app.db import models
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["Ingestion"])

# Services
chunker = ChunkingService()
embedder = EmbeddingService()
vectorstore = VectorStoreService()


def extract_text_from_file(file: UploadFile) -> str:
    """Extract text from .pdf or .txt file."""
    if file.filename.endswith(".txt"):
        return file.file.read().decode("utf-8")

    elif file.filename.endswith(".pdf"):
        pdf_reader = PdfReader(file.file)
        text: str = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text

    else:
        raise HTTPException(status_code=400, detail="Only .pdf and .txt files are supported.")


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    if not cleaned.isdigit():
        raise HTTPException(status_code=400, detail="year must be a valid integer")

    return int(cleaned)


def normalize_extracted_text(text: str) -> str:
    """Clean noisy whitespace produced by PDF extraction."""
    # Repair common UTF-8 -> Latin-1 mojibake sequences (e.g., â€™).
    try:
        repaired = text.encode("latin-1", errors="ignore").decode("utf-8", errors="replace")
        if repaired and repaired.count("â") < text.count("â"):
            text = repaired
    except Exception:
        pass

    replacements = {
        "\u00e2\u0080\u0099": "'",  # â€™
        "\u00e2\u0080\u009c": '"',  # â€œ
        "\u00e2\u0080\u009d": '"',  # â€
        "\u00e2\u0080\u0093": "-",  # â€" (en dash)
        "\u00e2\u0080\u0094": "-",  # â€" (em dash)
        "\u00e2\u0080": '"',        # â€
        "\u00e2": "",               # â
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    # Fix remaining patterns like Nepalâs -> Nepal's.
    text = re.sub(r"â([A-Za-z])", r"'\1", text)
    text = re.sub(r"\sâ\s", " - ", text)

    text = re.sub(r"\n\s*\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _background_process_document(
    document_id: int, 
    temp_file_path: str, 
    chunk_strategy: str,
    metadata_dict: dict,
    filename: str,
    filetype: str
):
    """
    Background thread: Extract, chunk, embed, and upsert entire document.
    This runs completely in background to avoid HTTP timeout.
    """
    from app.db.session import SessionLocal
    
    db = SessionLocal()
    try:
        logger.info(f"\n📄 [BG] Processing document {document_id}: {filename}")
        start_time = time.time()
        
        # Step 1: Extract text
        logger.info(f"   [BG] Step 1: Extracting text...")
        class FakeFile:
            def __init__(self, path):
                self.file = open(path, 'rb')
                self.filename = filename
                self.content_type = filetype
            def read(self):
                return self.file.read()
            def seek(self, pos):
                self.file.seek(pos)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.file.close()
        
        fake_file = FakeFile(temp_file_path)
        raw_text = extract_text_from_file(fake_file)
        fake_file.__exit__(None, None, None)
        
        logger.info(f"   [BG]   - Raw text: {len(raw_text):,} chars")
        
        # Step 2: Normalize
        text = normalize_extracted_text(raw_text)
        logger.info(f"   [BG]   - Normalized: {len(text):,} chars")
        
        if not text.strip():
            logger.error(f"   [BG] ❌ Document is empty!")
            db.close()
            return
        
        # Step 3: Chunk
        logger.info(f"   [BG] Step 2: Chunking with strategy '{chunk_strategy}'...")
        if chunk_strategy == "sliding":
            chunks = chunker.sliding_window_chunk(text)
        elif chunk_strategy == "sentence":
            chunks = chunker.sentence_chunk(text)
        else:
            logger.error(f"   [BG] ❌ Invalid chunk strategy")
            db.close()
            return
        
        logger.info(f"   [BG]   - Created {len(chunks)} chunks")
        
        # Step 4: Save chunks to DB
        logger.info(f"   [BG] Step 3: Saving {len(chunks)} chunks to database...")
        chunk_records: List[models.DocumentChunk] = []
        for chunk in chunks:
            chunk_record = models.DocumentChunk(document_id=document_id, chunk_text=chunk)
            db.add(chunk_record)
            chunk_records.append(chunk_record)
        db.commit()
        logger.info(f"   [BG]   - Saved {len(chunk_records)} chunks")
        
        # Step 5: Generate embeddings and upsert (batched)
        logger.info(f"   [BG] Step 4: Generating embeddings ({len(chunks)} chunks, batched)...")
        batch_size = 50
        
        for batch_idx in range(0, len(chunks), batch_size):
            batch_end = min(batch_idx + batch_size, len(chunks))
            batch_texts = [chunks[i] for i in range(batch_idx, batch_end)]
            batch_chunk_ids = [chunk_records[i].id for i in range(batch_idx, batch_end)]
            
            batch_num = batch_idx // batch_size + 1
            logger.info(f"   [BG]   Batch {batch_num}: Embedding {len(batch_texts)} chunks...")
            
            embeddings = embedder.embed_texts(batch_texts)
            
            # Prepare metadata
            batch_metadatas = [
                {
                    "document_id": document_id,
                    "chunk_id": batch_chunk_ids[i],
                    "text": batch_texts[i],
                    **metadata_dict,
                    "filename": filename,
                    "filetype": filetype,
                }
                for i in range(len(batch_texts))
            ]
            
            logger.info(f"   [BG]   Batch {batch_num}: Upserting to Pinecone...")
            vectorstore.upsert_embeddings(embeddings, batch_metadatas)
        
        elapsed = time.time() - start_time
        logger.info(f"   [BG] ✅ Complete! {len(chunks)} chunks in {elapsed:.1f}s")
        
    except Exception as e:
        logger.error(f"   [BG] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
        # Clean up temp file
        try:
            os.remove(temp_file_path)
        except:
            pass


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    chunk_strategy: str = Form(..., description="Choose 'sliding' or 'sentence'"),
    document_type: str | None = Form(None, description="Optional document_type override"),
    title: str | None = Form(None, description="Optional document title"),
    year: str | None = Form(None, description="Optional year"),
    program_name: str | None = Form(None, description="Optional program name"),
    donor_name: str | None = Form(None, description="Optional donor name"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Upload a document immediately.
    All processing (extraction, chunking, embedding) happens in background.
    Returns instantly without blocking.
    """
    logger.info(f"\n📄 Starting document upload: {file.filename}")
    
    # Only validate chunk_strategy upfront
    if chunk_strategy not in ["sliding", "sentence"]:
        raise HTTPException(status_code=400, detail="chunk_strategy must be 'sliding' or 'sentence'")
    
    try:
        # Create metadata template
        metadata = build_document_metadata(
            filename=file.filename,
            text="",  # Not available yet
            document_type=document_type,
            title=title,
            year=_parse_optional_int(year),
            program_name=program_name,
            donor_name=donor_name,
        )

        # Create document record with "processing" status
        document = models.Document(
            filename=file.filename,
            filetype=file.content_type,
            title=metadata.title,
            document_type=metadata.document_type,
            year=metadata.year,
            program_name=metadata.program_name,
            donor_name=metadata.donor_name,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        
        logger.info(f"   ✅ Document registered (ID: {document.id})")

        # Save uploaded file to temp location
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        shutil.copyfileobj(file.file, temp_file)
        temp_file.close()
        logger.info(f"   📁 Temp file: {temp_file.name}")

        # Start background processing thread
        metadata_dict = metadata_to_dict(metadata)
        bg_thread = threading.Thread(
            target=_background_process_document,
            args=(document.id, temp_file.name, chunk_strategy, metadata_dict, file.filename, file.content_type),
            daemon=True
        )
        bg_thread.start()
        logger.info(f"   ✅ Background processing started")

        return {
            "message": "Document uploaded and processing in background",
            "document_id": document.id,
            "status": "processing",
            "metadata": {
                "title": document.title,
                "document_type": document.document_type,
                "year": document.year,
                "program_name": document.program_name,
                "donor_name": document.donor_name,
            },
        }
        
    except Exception as e:
        logger.error(f"   ❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cleanup-duplicates")
async def cleanup_duplicates(db: Session = Depends(get_db)) -> dict:
    """
    Remove duplicate documents, keeping only the latest one.
    Admin endpoint for database maintenance.
    """
    from collections import defaultdict
    
    # Get all documents ordered by upload time
    documents = db.query(models.Document).order_by(models.Document.uploaded_at).all()
    logger.info(f"🔍 Found {len(documents)} total documents")
    
    # Group by title
    by_title = defaultdict(list)
    for doc in documents:
        by_title[doc.title].append(doc)
    
    # Find and delete duplicates
    deleted_doc_ids = []
    deleted_chunk_count = 0
    
    for title, docs in by_title.items():
        if len(docs) > 1:
            logger.info(f"   ⚠️  Found {len(docs)} duplicates for '{title}'")
            # Keep the latest, delete older ones
            for old_doc in docs[:-1]:
                logger.info(f"      Deleting ID {old_doc.id}")
                deleted_doc_ids.append(old_doc.id)
                # Delete chunks first
                chunks = db.query(models.DocumentChunk).filter(
                    models.DocumentChunk.document_id == old_doc.id
                ).all()
                deleted_chunk_count += len(chunks)
                for chunk in chunks:
                    db.delete(chunk)
                db.delete(old_doc)
    
    db.commit()
    logger.info(f"✅ Cleanup complete: Deleted {len(deleted_doc_ids)} documents, {deleted_chunk_count} chunks")
    
    return {
        "message": "Duplicate cleanup complete",
        "deleted_documents": deleted_doc_ids,
        "total_deleted": len(deleted_doc_ids),
        "total_chunks_deleted": deleted_chunk_count,
    }


@router.get("/documents")
async def list_documents(db: Session = Depends(get_db)) -> dict:
    """
    Get list of all uploaded documents.
    Used by sync script to check which PDFs already exist.
    """
    try:
        documents = db.query(models.Document).order_by(models.Document.id.desc()).all()
        
        doc_list = []
        for doc in documents:
            chunk_count = db.query(models.DocumentChunk).filter(
                models.DocumentChunk.document_id == doc.id
            ).count()
            
            doc_list.append({
                "id": doc.id,
                "title": doc.title,
                "filetype": doc.filetype,
                "chunks": chunk_count,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            })
        
        logger.info(f"📋 Listed {len(doc_list)} documents")
        return {
            "total": len(doc_list),
            "documents": doc_list
        }
    
    except Exception as e:
        logger.error(f"   ❌ Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    """
    Delete a specific document and its chunks.
    Used by cleanup script to remove old duplicates.
    """
    try:
        document = db.query(models.Document).filter(models.Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
        
        logger.info(f"🗑️  Deleting document {document_id}: {document.title}")
        
        # Delete chunks first
        chunks = db.query(models.DocumentChunk).filter(
            models.DocumentChunk.document_id == document_id
        ).all()
        
        chunk_count = len(chunks)
        for chunk in chunks:
            db.delete(chunk)
        
        # Delete document
        db.delete(document)
        db.commit()
        
        logger.info(f"✅ Deleted document {document_id} ({chunk_count} chunks removed)")
        
        return {
            "message": f"Document {document_id} deleted",
            "document_id": document_id,
            "title": document.title,
            "chunks_deleted": chunk_count
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"   ❌ Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))
