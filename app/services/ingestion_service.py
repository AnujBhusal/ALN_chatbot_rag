from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import io
from sqlalchemy import text
from PyPDF2 import PdfReader

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except Exception:
    PDFPLUMBER_AVAILABLE = False

from app.db import models
from app.db.session import SessionLocal
from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingService
from app.services.metadata import build_document_metadata
from app.services.vectorstore import VectorStoreService

logger = logging.getLogger(__name__)


@dataclass
class IngestionOutcome:
    document_id: Optional[int]
    checksum: str
    status: str
    source: str
    message: str
    chunk_count: int = 0
    vector_count: int = 0
    timing_ms: Dict[str, float] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "checksum": self.checksum,
            "status": self.status,
            "source": self.source,
            "message": self.message,
            "chunk_count": self.chunk_count,
            "vector_count": self.vector_count,
            "timing_ms": self.timing_ms,
            "diagnostics": self.diagnostics,
        }


class IngestionService:
    """Single transactional ingestion pipeline for uploads, folder scans, and jobs."""

    def __init__(self) -> None:
        self.chunker = ChunkingService()
        self.embedder = EmbeddingService()
        self.vectorstore = VectorStoreService()

    def _now(self) -> datetime:
        return datetime.utcnow()

    def _sha256_file(self, path: Path) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(8192), b""):
                hasher.update(block)
        return hasher.hexdigest()

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        raw = b""
        with open(pdf_path, "rb") as handle:
            raw = handle.read()

        text = ""
        try:
            pdf_file = io.BytesIO(raw)
            reader = PdfReader(pdf_file)
            for page in reader.pages:
                text += page.extract_text() or ""
            if text.strip():
                return text.strip()
        except Exception as error:
            logger.warning(f"PyPDF2 extraction failed for {pdf_path.name}: {error}")

        if not PDFPLUMBER_AVAILABLE:
            return ""

        try:
            pdf_file = io.BytesIO(raw)
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
            return text.strip()
        except Exception as error:
            logger.error(f"pdfplumber extraction failed for {pdf_path.name}: {error}")
            return ""

    def _normalize_text(self, text: str) -> str:
        import re

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

    def _state_update(self, db, document: models.Document, state: str, error: Optional[str] = None) -> None:
        document.ingestion_state = state
        if error:
            document.ingestion_error = error[:2000]
        if state == "processing":
            document.ingestion_started_at = self._now()
        elif state == "completed":
            document.ingestion_completed_at = self._now()
        elif state in {"failed", "rolled_back"}:
            document.rolled_back_at = self._now()
        db.add(document)
        db.commit()
        db.refresh(document)

    def _verify_ingestion(self, document: models.Document, chunk_ids: List[int], expected_chunk_count: int, chunk_texts: List[str]) -> Dict[str, Any]:
        point_ids = [f"{document.id}_{chunk_id}" for chunk_id in chunk_ids]
        fetched = self.vectorstore.fetch_by_ids(point_ids)
        fetched_count = len(fetched)

        metadata_issues: List[Dict[str, Any]] = []
        for point_id, vector in fetched.items():
            metadata = (vector or {}).get("metadata", {}) if isinstance(vector, dict) else {}
            try:
                meta_doc_id = int(float(metadata.get("document_id"))) if metadata.get("document_id") is not None else None
            except Exception:
                meta_doc_id = None
            try:
                meta_chunk_id = int(float(metadata.get("chunk_id"))) if metadata.get("chunk_id") is not None else None
            except Exception:
                meta_chunk_id = None

            expected_doc_id, expected_chunk_id = point_id.split("_")
            expected_doc_id = int(expected_doc_id)
            expected_chunk_id = int(expected_chunk_id)

            if meta_doc_id != expected_doc_id or meta_chunk_id != expected_chunk_id:
                metadata_issues.append({
                    "point_id": point_id,
                    "expected": {"document_id": expected_doc_id, "chunk_id": expected_chunk_id},
                    "found": metadata,
                })

        retrieval_ok = False
        retrieval_count = 0
        if chunk_texts:
            try:
                embedding = self.embedder.embed_texts([chunk_texts[0]])[0]
                results = self.vectorstore.query(embedding, top_k=5, query_filter={"document_id": {"$eq": document.id}})
                retrieval_count = len(results)
                retrieval_ok = retrieval_count > 0
            except Exception as error:
                metadata_issues.append({"issue": "retrieval_test_failed", "error": str(error)})

        return {
            "vector_fetch_count": fetched_count,
            "expected_chunk_count": expected_chunk_count,
            "metadata_issues": metadata_issues,
            "retrieval_ok": retrieval_ok,
            "retrieval_count": retrieval_count,
            "vector_ids": point_ids,
        }

    def ingest_pdf_path(
        self,
        pdf_path: Path,
        *,
        chunk_strategy: str = "sentence",
        document_type: Optional[str] = None,
        title: Optional[str] = None,
        year: Optional[int] = None,
        program_name: Optional[str] = None,
        donor_name: Optional[str] = None,
        source: str = "upload",
        filename: Optional[str] = None,
        filetype: str = "application/pdf",
    ) -> IngestionOutcome:
        start = time.perf_counter()
        db = SessionLocal()
        checksum = self._sha256_file(pdf_path)
        point_ids: List[str] = []
        document: Optional[models.Document] = None
        temp_error: Optional[str] = None

        try:
            logger.info(f"📥 Ingestion started from {source}: {pdf_path.name}")
            logger.info(f"🔐 Checksum: {checksum}")

            existing = db.query(models.Document).filter(models.Document.file_checksum == checksum).first()
            if existing and existing.ingestion_state == "completed":
                chunk_count = db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == existing.id).count()
                elapsed = (time.perf_counter() - start) * 1000
                return IngestionOutcome(
                    document_id=existing.id,
                    checksum=checksum,
                    status="skipped_duplicate",
                    source=source,
                    message="Document already ingested",
                    chunk_count=chunk_count,
                    vector_count=chunk_count,
                    timing_ms={"total": round(elapsed, 2)},
                    diagnostics={"existing_state": existing.ingestion_state},
                )

            raw_text = self._extract_text_from_pdf(pdf_path)
            text = self._normalize_text(raw_text)
            if not text.strip():
                raise ValueError("No text extracted from PDF")

            metadata = build_document_metadata(
                filename=filename or pdf_path.name,
                text=text,
                document_type=document_type,
                title=title,
                year=year,
                program_name=program_name,
                donor_name=donor_name,
            )

            if existing:
                document = existing
                document.filename = filename or pdf_path.name
                document.filetype = filetype
                document.title = metadata.title
                document.document_type = metadata.document_type
                document.year = metadata.year
                document.program_name = metadata.program_name
                document.donor_name = metadata.donor_name
                document.file_checksum = checksum
            else:
                document = models.Document(
                    filename=filename or pdf_path.name,
                    filetype=filetype,
                    title=metadata.title,
                    document_type=metadata.document_type,
                    year=metadata.year,
                    program_name=metadata.program_name,
                    donor_name=metadata.donor_name,
                    file_checksum=checksum,
                    ingestion_state="pending",
                )
                db.add(document)

            db.commit()
            db.refresh(document)
            self._state_update(db, document, "processing")

            chunk_start = time.perf_counter()
            if chunk_strategy == "sliding":
                chunk_texts = self.chunker.sliding_window_chunk(text)
            else:
                chunk_texts = self.chunker.sentence_chunk(text)

            if not chunk_texts:
                raise ValueError("No chunks were generated from document text")

            try:
                with db.begin():
                    # Remove any stale chunks for a retrying document in the same transaction
                    db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == document.id).delete(synchronize_session=False)

                    chunk_rows: List[models.DocumentChunk] = []
                    for chunk_text in chunk_texts:
                        chunk = models.DocumentChunk(document_id=document.id, chunk_text=chunk_text)
                        db.add(chunk)
                        chunk_rows.append(chunk)

                    db.flush()
                    chunk_ids = [chunk.id for chunk in chunk_rows]
                    embeddings = self.embedder.embed_texts(chunk_texts)
                    if len(embeddings) != len(chunk_rows):
                        raise RuntimeError("Embedding count does not match chunk count")

                    metadatas = [
                        {
                            "document_id": document.id,
                            "chunk_id": chunk.id,
                            "text": chunk.chunk_text,
                            "title": document.title,
                            "document_type": document.document_type,
                            "year": document.year,
                            "source": source,
                        }
                        for chunk in chunk_rows
                    ]

                    self.vectorstore.upsert_embeddings(embeddings, metadatas)
                    point_ids = [f"{document.id}_{chunk_id}" for chunk_id in chunk_ids]
                    verification = self._verify_ingestion(document, chunk_ids, len(chunk_rows), chunk_texts)
                    if verification["vector_fetch_count"] != len(chunk_rows):
                        raise RuntimeError(
                            f"Vector count mismatch: expected {len(chunk_rows)} got {verification['vector_fetch_count']}"
                        )
                    if verification["metadata_issues"]:
                        raise RuntimeError(f"Metadata verification failed: {verification['metadata_issues'][:3]}")
                    if not verification["retrieval_ok"]:
                        raise RuntimeError("Retrieval verification failed")

                    document.ingestion_state = "completed"
                    document.ingestion_error = None
                    document.ingestion_completed_at = self._now()
                    db.add(document)
                    db.flush()

                db.commit()
                elapsed = (time.perf_counter() - start) * 1000
                chunk_elapsed = (time.perf_counter() - chunk_start) * 1000
                logger.info(
                    f"✅ Ingestion completed for document {document.id} | chunks={len(chunk_texts)} | vectors={len(point_ids)} | total_ms={elapsed:.2f}"
                )
                return IngestionOutcome(
                    document_id=document.id,
                    checksum=checksum,
                    status="completed",
                    source=source,
                    message="Ingestion completed successfully",
                    chunk_count=len(chunk_texts),
                    vector_count=len(point_ids),
                    timing_ms={"total": round(elapsed, 2), "chunking+vector": round(chunk_elapsed, 2)},
                    diagnostics={
                        "vector_ids": point_ids[:50],
                        "metadata_verified": True,
                        "retrieval_verified": True,
                    },
                )
            except Exception as error:
                temp_error = str(error)
                db.rollback()
                if point_ids:
                    try:
                        self.vectorstore.delete_by_ids(point_ids)
                    except Exception as cleanup_error:
                        logger.warning(f"Vector cleanup after failure also failed: {cleanup_error}")
                rollback_doc = db.query(models.Document).filter(models.Document.id == document.id).first()
                if rollback_doc:
                    rollback_doc.ingestion_state = "rolled_back"
                    rollback_doc.ingestion_error = temp_error[:2000]
                    rollback_doc.rolled_back_at = self._now()
                    db.add(rollback_doc)
                    db.commit()
                elapsed = (time.perf_counter() - start) * 1000
                logger.error(f"❌ Ingestion rolled back for document {document.id if document else 'n/a'}: {error}")
                return IngestionOutcome(
                    document_id=document.id if document else None,
                    checksum=checksum,
                    status="rolled_back",
                    source=source,
                    message=str(error),
                    chunk_count=0,
                    vector_count=0,
                    timing_ms={"total": round(elapsed, 2)},
                    diagnostics={"error": str(error), "cleaned_vectors": len(point_ids)},
                )

        except Exception as error:
            elapsed = (time.perf_counter() - start) * 1000
            temp_error = str(error)
            db.rollback()
            if document and document.id:
                rollback_doc = db.query(models.Document).filter(models.Document.id == document.id).first()
                if rollback_doc:
                    rollback_doc.ingestion_state = "failed"
                    rollback_doc.ingestion_error = temp_error[:2000]
                    rollback_doc.rolled_back_at = self._now()
                    db.add(rollback_doc)
                    db.commit()
            logger.error(f"❌ Ingestion failed for {pdf_path.name}: {error}")
            return IngestionOutcome(
                document_id=document.id if document else None,
                checksum=checksum,
                status="failed",
                source=source,
                message=str(error),
                timing_ms={"total": round(elapsed, 2)},
                diagnostics={"error": str(error)},
            )
        finally:
            db.close()

    def ingest_folder(self, folder: Path) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "documents": [],
            "vector_count": 0,
            "chunk_count": 0,
            "timing_ms": {},
        }
        if not folder.exists():
            return results

        pdf_files = sorted(folder.glob("*.pdf"))
        results["total"] = len(pdf_files)
        start = time.perf_counter()
        lock_db = SessionLocal()
        lock_acquired = False
        try:
            lock_db.execute(text("""
                CREATE TABLE IF NOT EXISTS ingestion_locks (
                    name TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            lock_db.commit()
            try:
                lock_db.execute(text("INSERT INTO ingestion_locks(name) VALUES (:name)"), {"name": "folder_ingest"})
                lock_db.commit()
                lock_acquired = True
            except Exception:
                lock_db.rollback()
                logger.info("⏭️  Folder ingestion already running elsewhere; skipping")
                results["timing_ms"] = {"total": round((time.perf_counter() - start) * 1000, 2)}
                return results

            for pdf_path in pdf_files:
                outcome = self.ingest_pdf_path(pdf_path, source="folder")
                results["documents"].append(outcome.to_dict())
                if outcome.status in {"completed", "skipped_duplicate"}:
                    results["successful"] += 1
                else:
                    results["failed"] += 1
                results["vector_count"] += outcome.vector_count
                results["chunk_count"] += outcome.chunk_count
        finally:
            if lock_acquired:
                try:
                    lock_db.execute(text("DELETE FROM ingestion_locks WHERE name = :name"), {"name": "folder_ingest"})
                    lock_db.commit()
                except Exception:
                    lock_db.rollback()
                lock_db.close()
        results["timing_ms"] = {"total": round((time.perf_counter() - start) * 1000, 2)}
        return results
