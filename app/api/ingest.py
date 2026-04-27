from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import re

from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingService
from app.services.vectorstore import VectorStoreService
from app.services.metadata import build_document_metadata, metadata_to_dict
from app.db.session import get_db
from app.db import models
from PyPDF2 import PdfReader

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
        "â€™": "'",
        "â€œ": '"',
        "â€\x9d": '"',
        "â€“": "-",
        "â€”": "-",
        "â€": '"',
        "â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    # Fix remaining patterns like Nepalâs -> Nepal's.
    text = re.sub(r"â([A-Za-z])", r"'\1", text)
    text = re.sub(r"\sâ\s", " - ", text)

    text = re.sub(r"\n\s*\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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
    Upload a document, chunk it, generate embeddings, and store in DB + Pinecone.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"\n📄 Starting document upload: {file.filename}")
    
    # Step 1: Extract text
    logger.info(f"   Step 1: Extracting text...")
    raw_text: str = extract_text_from_file(file)
    logger.info(f"   - Raw text length: {len(raw_text)} chars")
    
    text: str = normalize_extracted_text(raw_text)
    logger.info(f"   - Normalized text length: {len(text)} chars")
    
    if not text.strip():
        logger.error(f"   ❌ Uploaded file is empty!")
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    
    logger.info(f"   ✅ Text extracted successfully")

    # Step 2: Chunking
    logger.info(f"   Step 2: Chunking with strategy '{chunk_strategy}'...")
    if chunk_strategy == "sliding":
        chunks: List[str] = chunker.sliding_window_chunk(text)
    elif chunk_strategy == "sentence":
        chunks: List[str] = chunker.sentence_chunk(text)
    else:
        logger.error(f"   ❌ Invalid chunk strategy")
        raise HTTPException(status_code=400, detail="Invalid chunk strategy. Use 'sliding' or 'sentence'.")
    
    logger.info(f"   - Created {len(chunks)} chunks")
    logger.info(f"   - Sample chunk 1: {chunks[0][:100] if chunks else 'N/A'}...")
    logger.info(f"   ✅ Chunking complete")

    metadata = build_document_metadata(
        filename=file.filename,
        text=text,
        document_type=document_type,
        title=title,
        year=_parse_optional_int(year),
        program_name=program_name,
        donor_name=donor_name,
    )

    # Step 3: Save document metadata in Postgres
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

    # Step 4: Save chunks in Postgres
    logger.info(f"   Step 4: Saving chunks to database...")
    chunk_records: List[models.DocumentChunk] = []
    for chunk in chunks:
        chunk_record = models.DocumentChunk(document_id=document.id, chunk_text=chunk)
        db.add(chunk_record)
        chunk_records.append(chunk_record)
    db.commit()
    logger.info(f"   - Saved {len(chunk_records)} chunks")
    logger.info(f"   ✅ Document saved (ID: {document.id})")

    # Step 5: Generate embeddings
    logger.info(f"   Step 5: Generating embeddings for {len(chunks)} chunks...")
    embeddings: List[List[float]] = embedder.embed_texts(chunks)
    logger.info(f"   - Generated {len(embeddings)} embeddings")
    logger.info(f"   - Embedding dimension: {len(embeddings[0]) if embeddings else 0}")
    logger.info(f"   ✅ Embeddings generated")

    # Step 6: Store embeddings in Pinecone with metadata
    logger.info(f"   Step 6: Storing embeddings in Pinecone...")
    metadatas = [
        {
            "document_id": document.id,
            "chunk_id": chunk.id,
            "text": chunk.chunk_text,
            **metadata_to_dict(metadata),
            "filename": file.filename,
            "filetype": file.content_type,
        }
        for chunk in chunk_records
    ]
    vectorstore.upsert_embeddings(embeddings, metadatas)
    logger.info(f"   - Upserted {len(metadatas)} vectors to Pinecone")
    logger.info(f"   ✅ Upload complete!")

    return {
        "message": "Document uploaded and processed successfully",
        "document_id": document.id,
        "metadata": {
            "title": document.title,
            "document_type": document.document_type,
            "year": document.year,
            "program_name": document.program_name,
            "donor_name": document.donor_name,
        },
    }


@router.delete("/cleanup-duplicates")
async def cleanup_duplicates(db: Session = Depends(get_db)) -> dict:
    """
    Remove duplicate documents, keeping only the latest one.
    Admin endpoint for database maintenance.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    from collections import defaultdict
    
    # Get all documents ordered by upload time
    documents = db.query(models.Document).order_by(models.Document.uploaded_at).all()
    logger.info(f"🔍 Found {len(documents)} total documents")
    
    # Group by title
    by_title = defaultdict(list)
    for doc in documents:
        by_title[doc.title].append(doc)
    
    deleted_docs = []
    deleted_chunks = 0
    
    # Find and remove duplicates
    for title, docs in by_title.items():
        if len(docs) > 1:
            logger.info(f"⚠️  Found {len(docs)} duplicates of '{title}'")
            
            # Keep the latest, delete others
            latest = max(docs, key=lambda d: d.uploaded_at)
            logger.info(f"   ✅ Keeping ID {latest.id}")
            
            for old_doc in docs:
                if old_doc.id != latest.id:
                    logger.info(f"   ❌ Deleting ID {old_doc.id}")
                    
                    # Delete chunks first
                    chunk_count = db.query(models.DocumentChunk).filter(
                        models.DocumentChunk.document_id == old_doc.id
                    ).count()
                    
                    db.query(models.DocumentChunk).filter(
                        models.DocumentChunk.document_id == old_doc.id
                    ).delete()
                    
                    deleted_chunks += chunk_count
                    logger.info(f"      └─ Deleted {chunk_count} chunks")
                    
                    # Delete document
                    db.delete(old_doc)
                    deleted_docs.append(old_doc.id)
    
    db.commit()
    
    return {
        "message": "Duplicate cleanup complete",
        "deleted_documents": deleted_docs,
        "total_deleted": len(deleted_docs),
        "total_chunks_deleted": deleted_chunks,
    }
