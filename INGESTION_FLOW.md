# Ingestion Flow

1. Upload endpoint (/api/ingest/upload)
   - Saves uploaded file to a temp file.
   - Computes SHA256 checksum of file.
   - If checksum exists in DB, skip ingestion and return existing document id.
   - Creates `Document` row with `file_checksum`.
   - Starts background thread `_background_process_document`.

2. Background processing (`_background_process_document`)
   - Extract text from PDF (`PyPDF2` then `pdfplumber` fallback).
   - Normalize text.
   - Chunk text using `ChunkingService`.
   - Persist `DocumentChunk` rows to DB and commit to obtain `chunk.id` values.
   - Generate embeddings in batches (`EmbeddingService`) and upsert to vectorstore with point IDs `{document_id}_{chunk_id}`.

3. Folder ingestion (`app/services/folder_ingestion.py`)
   - Scans `data/pdfs`.
   - Computes checksum for each PDF and skips if checksum or filename exists.
   - Uses DB-based ingestion lock (`ingestion_locks` table) to prevent concurrent runs.
   - Persists Document and DocumentChunk rows before embedding/upsert.

4. Deletion
   - Delete DB Document and DocumentChunk rows.
   - Delete vectors by explicit point IDs if chunk ids are available; otherwise fallback to metadata-based deletion.

Notes
- Deterministic IDs and committed DB chunk ids are essential for idempotent upsert and reliable deletion.
- Ensure `ENABLE_FOLDER_INGESTION` is disabled in production unless explicitly enabled.
