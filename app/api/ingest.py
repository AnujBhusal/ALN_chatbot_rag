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
import io
from pathlib import Path

from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingService
from app.services.vectorstore import VectorStoreService
from app.services.ingestion_service import IngestionService
from app.services.metadata import build_document_metadata, metadata_to_dict
from app.db.session import get_db
from app.db import models
from PyPDF2 import PdfReader

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["Ingestion"])

# Services
chunker = ChunkingService()
embedder = EmbeddingService()
vectorstore = VectorStoreService()
ingestion_service = IngestionService()


def extract_text_from_file(file: UploadFile) -> str:
    """
    Extract text from .pdf or .txt file with robust handling for multi-page PDFs.
    
    For PDFs:
    - Uses PyPDF2 as primary method with full page logging
    - Falls back to pdfplumber for complex/scanned PDFs
    - Ensures file pointer is reset before reading
    - Logs extraction progress for all pages
    """
    if file.filename.endswith(".txt"):
        return file.file.read().decode("utf-8")

    elif file.filename.endswith(".pdf"):
        # Read entire PDF into bytes to avoid file pointer issues
        file.file.seek(0)  # Reset to beginning
        pdf_bytes = file.file.read()
        
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="PDF file is empty")
        
        return _extract_text_from_pdf_bytes(pdf_bytes, file.filename)

    else:
        raise HTTPException(status_code=400, detail="Only .pdf and .txt files are supported.")


def _extract_text_from_pdf_bytes(pdf_bytes: bytes, filename: str) -> str:
    """
    Extract text from PDF bytes with multiple fallback strategies.
    
    PRIMARY: PyPDF2 with detailed page logging
    FALLBACK: pdfplumber (if available) for complex PDFs
    FALLBACK: Simple text extraction without structure
    """
    text = ""
    
    # Strategy 1: PyPDF2 (primary method)
    try:
        logger.info(f"📄 Extracting PDF '{filename}' using PyPDF2...")
        pdf_file = io.BytesIO(pdf_bytes)
        pdf_reader = PdfReader(pdf_file)
        
        total_pages = len(pdf_reader.pages)
        logger.info(f"   📋 Total pages detected: {total_pages}")
        
        if total_pages == 0:
            logger.warning(f"   ⚠️  PDF has 0 pages, trying pdfplumber fallback...")
            return _extract_text_with_pdfplumber(pdf_bytes, filename)
        
        extracted_pages = []
        for page_idx, page in enumerate(pdf_reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
                char_count = len(page_text.strip())
                extracted_pages.append(char_count)
                
                if char_count > 0:
                    logger.debug(f"   ✓ Page {page_idx}/{total_pages}: {char_count} chars extracted")
                    text += page_text
                else:
                    logger.warning(f"   ⚠️  Page {page_idx}/{total_pages}: No text extracted (may be scanned/image-based)")
                    
            except Exception as page_error:
                logger.error(f"   ❌ Page {page_idx}/{total_pages}: Error - {page_error}")
                # Continue to next page instead of failing
                continue
        
        if not text.strip():
            logger.warning(f"   ⚠️  PyPDF2 extracted 0 characters total, trying pdfplumber...")
            return _extract_text_with_pdfplumber(pdf_bytes, filename)
        
        logger.info(f"   ✅ PyPDF2 Success: Extracted {len(text):,} chars from {len(extracted_pages)} pages")
        return text
        
    except Exception as e:
        logger.error(f"   ❌ PyPDF2 failed: {e}")
        logger.info(f"   📄 Falling back to pdfplumber...")
        return _extract_text_with_pdfplumber(pdf_bytes, filename)


def _extract_text_with_pdfplumber(pdf_bytes: bytes, filename: str) -> str:
    """
    Fallback PDF extraction using pdfplumber (more robust for complex PDFs).
    Better at handling scanned PDFs, complex layouts, and non-standard encoding.
    """
    if not PDFPLUMBER_AVAILABLE:
        logger.warning(f"   ⚠️  pdfplumber not installed (pip install pdfplumber)")
        return ""
    
    try:
        logger.info(f"📄 Extracting PDF '{filename}' using pdfplumber...")
        pdf_file = io.BytesIO(pdf_bytes)
        
        text = ""
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"   📋 Total pages detected: {total_pages}")
            
            for page_idx, page in enumerate(pdf.pages, start=1):
                try:
                    page_text = page.extract_text() or ""
                    char_count = len(page_text.strip())
                    
                    if char_count > 0:
                        logger.debug(f"   ✓ Page {page_idx}/{total_pages}: {char_count} chars extracted")
                        text += page_text
                    else:
                        logger.warning(f"   ⚠️  Page {page_idx}/{total_pages}: No text extracted")
                        
                except Exception as page_error:
                    logger.error(f"   ❌ Page {page_idx}/{total_pages}: Error - {page_error}")
                    continue
        
        if text.strip():
            logger.info(f"   ✅ pdfplumber Success: Extracted {len(text):,} chars from {total_pages} pages")
        else:
            logger.error(f"   ❌ pdfplumber: No text extracted from any page (likely scanned image PDF)")
        
        return text
        
    except Exception as e:
        logger.error(f"   ❌ pdfplumber failed: {e}")
        return ""


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
    """Clean noisy whitespace and encoding issues from PDF extraction."""
    # Handle UTF-8 encoding errors first
    try:
        # Encode as UTF-8 and decode to fix mojibake
        if isinstance(text, str):
            text = text.encode('utf-8', errors='ignore').decode('utf-8', errors='replace')
    except Exception:
        pass
    
    # Common UTF-8 mojibake replacements
    replacements = {
        "\u00e2\u0080\u0099": "'",  # â€™ → '
        "\u00e2\u0080\u009c": '"',  # â€œ → "
        "\u00e2\u0080\u009d": '"',  # â€ → "
        "\u00e2\u0080\u0093": "-",  # â€" → - (en dash)
        "\u00e2\u0080\u0094": "-",  # â€" → - (em dash)
        "\u00e2\u0080\u0098": "'",  # â€˜ → '
        "\u00e2": "",               # Remove stray â
        "\u009f": "",               # Remove stray control chars
        "\u0092": "'",              # Windows smart quote
        "\u0091": "'",              # Windows smart quote
        "\u0093": '"',              # Windows smart quote
        "\u0094": '"',              # Windows smart quote
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    
    # Fix patterns like "Nepalâs" → "Nepal's"
    text = re.sub(r"([a-zA-Z])â([a-zA-Z])", r"\1'\2", text)
    
    # Remove remaining invalid unicode characters (replace with space)
    text = ''.join(c if ord(c) < 128 or ord(c) > 127 and c.isprintable() else ' ' for c in text)
    
    # Normalize whitespace
    text = re.sub(r"\n\s*\n+", " ", text)  # Multiple newlines → space
    text = re.sub(r"\s+", " ", text)       # Multiple spaces → single space
    
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
    
    temp_file = None
    try:
        # Save uploaded file to temp location first
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        shutil.copyfileobj(file.file, temp_file)
        temp_file.close()
        logger.info(f"   📁 Temp file: {temp_file.name}")
        outcome = ingestion_service.ingest_pdf_path(
            Path(temp_file.name),
            chunk_strategy=chunk_strategy,
            document_type=document_type,
            title=title,
            year=_parse_optional_int(year),
            program_name=program_name,
            donor_name=donor_name,
            source="upload",
            filename=file.filename,
            filetype=file.content_type or "application/pdf",
        )

        logger.info(f"   ✅ Upload ingestion finished: {outcome.status}")
        return outcome.to_dict()

    except Exception as e:
        logger.error(f"   ❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            if temp_file is not None:
                os.remove(temp_file.name)
        except Exception:
            pass


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
    
    # Group by checksum first (strong dedupe), fallback to normalized title
    by_title = defaultdict(list)
    for doc in documents:
        if doc.file_checksum:
            dedupe_key = f"checksum:{doc.file_checksum.strip().lower()}"
        else:
            normalized_title = re.sub(r"\s+", " ", (doc.title or "").strip().lower())
            dedupe_key = f"title:{normalized_title}"
        by_title[dedupe_key].append(doc)
    
    # Find and delete duplicates
    deleted_doc_ids = []
    deleted_chunk_count = 0
    # Track which docs were cleaned via id-based deletion
    pinecone_deleted_docs: List[int] = []
    
    for dedupe_key, docs in by_title.items():
        if len(docs) > 1:
            logger.info(f"   ⚠️  Found {len(docs)} duplicates for '{dedupe_key}'")
            # Prefer keeping the latest completed document; otherwise keep latest overall
            sorted_docs = sorted(
                docs,
                key=lambda d: (
                    1 if getattr(d, "ingestion_state", None) == "completed" else 0,
                    d.uploaded_at or 0,
                    d.id,
                ),
                reverse=True,
            )
            keep_doc = sorted_docs[0]
            for old_doc in sorted_docs[1:]:
                logger.info(f"      Deleting ID {old_doc.id}")
                deleted_doc_ids.append(old_doc.id)
                # Collect chunk ids to remove from vectorstore (use deterministic point ids)
                chunks = db.query(models.DocumentChunk).filter(
                    models.DocumentChunk.document_id == old_doc.id
                ).all()
                chunk_ids = [c.id for c in chunks]
                deleted_chunk_count += len(chunks)
                # Delete chunk rows and document row from DB
                for chunk in chunks:
                    db.delete(chunk)
                db.delete(old_doc)
                # After DB deletion, attempt to remove vectors by explicit ids
                try:
                    point_ids = [f"{old_doc.id}_{cid}" for cid in chunk_ids]
                    vectorstore.delete_by_ids(point_ids)
                    logger.info(f"   ✅ Deleted Pinecone vectors for document {old_doc.id} by ids")
                    pinecone_deleted_docs.append(old_doc.id)
                except Exception as e:
                    logger.warning(
                        f"   ⚠️  Pinecone id-based deletion failed for document {old_doc.id}: {e}"
                    )

            logger.info(f"      Keeping ID {keep_doc.id} for key '{dedupe_key}'")
    
    db.commit()
    
    # 🔥 NEW: Delete vectors from Pinecone for all deleted documents
    logger.info(f"📤 Cleaning up Pinecone vectors for {len(deleted_doc_ids)} documents...")
    # For any documents that were NOT cleaned by id-based deletion, try metadata-based deletion
    fallback_attempts = 0
    for doc_id in deleted_doc_ids:
        if doc_id in pinecone_deleted_docs:
            continue
        try:
            vectorstore.delete_by_document_id(doc_id)
            pinecone_deleted_docs.append(doc_id)
            fallback_attempts += 1
            logger.info(f"   ✅ Fallback-deleted Pinecone vectors for document {doc_id}")
        except Exception as e:
            logger.warning(f"   ⚠️  Pinecone fallback deletion failed for document {doc_id}: {e}")

    pinecone_deleted_count = len(pinecone_deleted_docs)
    
    logger.info(f"✅ Cleanup complete: Deleted {len(deleted_doc_ids)} documents, {deleted_chunk_count} chunks, {pinecone_deleted_count} Pinecone syncs")
    
    return {
        "message": "Duplicate cleanup complete (database + Pinecone)",
        "deleted_documents": deleted_doc_ids,
        "total_deleted": len(deleted_doc_ids),
        "total_chunks_deleted": deleted_chunk_count,
        "pinecone_cleaned": pinecone_deleted_count,
        "pinecone_sync_status": "complete" if pinecone_deleted_count == len(deleted_doc_ids) else "partial"
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
        
        # Delete chunks first (collect chunk ids for vector deletion)
        chunks = db.query(models.DocumentChunk).filter(
            models.DocumentChunk.document_id == document_id
        ).all()

        chunk_ids = [c.id for c in chunks]
        chunk_count = len(chunks)
        for chunk in chunks:
            db.delete(chunk)

        # Delete document
        db.delete(document)
        db.commit()

        # Try id-based Pinecone deletion first (deterministic)
        logger.info(f"📤 Cleaning up Pinecone vectors for document {document_id} by ids...")
        try:
            point_ids = [f"{document_id}_{cid}" for cid in chunk_ids]
            vectorstore.delete_by_ids(point_ids)
            logger.info(f"   ✅ Deleted Pinecone vectors for document {document_id} by explicit ids")
            pinecone_status = "cleaned"
        except Exception as e:
            logger.warning(f"   ⚠️  Pinecone id-based deletion failed: {e}, falling back to metadata filter")
            try:
                vectorstore.delete_by_document_id(document_id)
                logger.info(f"   ✅ Deleted Pinecone vectors for document {document_id} via filter")
                pinecone_status = "cleaned"
            except Exception as e:
                logger.warning(f"   ⚠️  Pinecone deletion failed: {e}")
                pinecone_status = "failed"
        
        logger.info(f"✅ Deleted document {document_id} ({chunk_count} chunks removed) - Pinecone: {pinecone_status}")
        
        return {
            "message": f"Document {document_id} deleted from both database and Pinecone",
            "document_id": document_id,
            "title": document.title,
            "chunks_deleted": chunk_count,
            "pinecone_cleaned": pinecone_status
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"   ❌ Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))
