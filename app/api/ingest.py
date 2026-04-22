from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import re

from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingService
from app.services.vectorstore import VectorStoreService
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
    db: Session = Depends(get_db),
) -> dict:
    """
    Upload a document, chunk it, generate embeddings, and store in DB + Qdrant.
    """
    # Step 1: Extract text
    text: str = normalize_extracted_text(extract_text_from_file(file))
    if not text.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Step 2: Chunking
    if chunk_strategy == "sliding":
        chunks: List[str] = chunker.sliding_window_chunk(text)
    elif chunk_strategy == "sentence":
        chunks: List[str] = chunker.sentence_chunk(text)
    else:
        raise HTTPException(status_code=400, detail="Invalid chunk strategy. Use 'sliding' or 'sentence'.")

    # Step 3: Save document metadata in Postgres
    document = models.Document(filename=file.filename, filetype=file.content_type)
    db.add(document)
    db.commit()
    db.refresh(document)

    # Step 4: Save chunks in Postgres
    chunk_records: List[models.DocumentChunk] = []
    for chunk in chunks:
        chunk_record = models.DocumentChunk(document_id=document.id, chunk_text=chunk)
        db.add(chunk_record)
        chunk_records.append(chunk_record)
    db.commit()

    # Step 5: Generate embeddings
    embeddings: List[List[float]] = embedder.embed_texts(chunks)

    # Step 6: Store embeddings in Qdrant with metadata
    metadatas = [
        {"document_id": document.id, "chunk_id": chunk.id, "text": chunk.chunk_text}
        for chunk in chunk_records
    ]
    vectorstore.upsert_embeddings(embeddings, metadatas)

    return {"message": "Document uploaded and processed successfully", "document_id": document.id}
