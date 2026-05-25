# Ingestion Lifecycle & Duplication Root Cause Analysis

Summary
- This report traces the full ingestion lifecycle (upload → chunk → embed → vectorstore → retrieval → deletion → startup) and identifies why duplicate PDFs and vectors were appearing.
- I applied immediate fixes (see patches section) to make ingestion deterministic and deletion reliable.

1) Complete ingestion lifecycle (concise flow)

- Upload (API): `POST /api/ingest/upload` handled by `app/api/ingest.py` — creates a `Document` DB row, writes a temp file, then starts `_background_process_document` in a background thread which:
  - Extracts text (`_extract_text_from_pdf_bytes`) and normalizes it
  - Chunks text via `ChunkingService` (`app/services/chunking.py`)
  - Persists `DocumentChunk` rows (column `chunk_text`) to DB
  - Generates embeddings via `EmbeddingService` (`app/services/embeddings.py`)
  - Upserts vectors to Pinecone using `VectorStoreService.upsert_embeddings` (`app/services/vectorstore.py`) with metadata that includes `chunk_id` (DB chunk id) — thus vector IDs are deterministic: `"{document_id}_{chunk_id}"`.
  See: `app/api/ingest.py` (`/upload` + `_background_process_document`) and `app/services/vectorstore.py` (`upsert_embeddings`).

- Folder ingestion (startup/auto): `app/services/folder_ingestion.py` — scans `./data/pdfs` and previously used inconsistent fields and logic (this caused duplication). It ran on startup from `app/main.py` when `LOCAL_MODE` and `ENABLE_FOLDER_INGESTION` are enabled.
  See: `app/main.py` (startup) and `app/services/folder_ingestion.py`.

- Retrieval: `app/api/chat.py` queries the vectorstore via `vectorstore.query(...)`, groups results in `app/services/retrieval.py`, builds context and calls LLM.

- Deletion / Cleanup: `app/api/ingest.py` exposes `DELETE /api/ingest/documents/{document_id}` and `DELETE /api/ingest/cleanup-duplicates` which remove DB rows and call `vectorstore.delete_by_document_id(document_id)`.

2) Key findings — why duplication occurred

- Multiple ingestion entrypoints ran for the same PDFs:
  - Startup folder ingestion runs automatically by default (configuration issue: `ENABLE_FOLDER_INGESTION` defaulted to true and `LOCAL_MODE` detection made startup ingest run on many deployments).
  - Deployment scripts (e.g., `upload_all_pdfs.py`, `ingest_pdfs.py`) or manual uploads via UI may also re-upload the same PDF.

- Inconsistent ingestion code paths:
  - `app/services/folder_ingestion.py` originally used different DB field names (`file_path`, `file_type`, `text`, `chunk_index`, `embedding`) compared to the DB model (`filename`, `filetype`, `chunk_text`) and compared documents by `title` rather than `filename`. These mismatches prevented reliable duplicate detection and produced inconsistent metadata pushed to Pinecone.

- Non-deterministic or mismatched vector deletion:
  - Deletion used metadata-based filter `{'document_id': {'$eq': document_id}}` via `vectorstore.delete_by_document_id()`. If vectors' metadata types (string vs int vs float) did not match the filter type, Pinecone filter deletion could silently fail and vectors remain.

- Auto-reingestion on restart:
  - `app/main.py` invoked `FolderIngestionService.ingest_folder()` on startup when `LOCAL_MODE` and `ENABLE_FOLDER_INGESTION` were true. On container/restart, this re-scanned `data/pdfs` and created new DB documents when filename/title normalization didn't match prior entries.

3) Evidence / exact files & functions involved

- Startup trigger: `app/main.py` — `startup_event()` → `FolderIngestionService.ingest_folder()`
  - [app/main.py](app/main.py#L57-L90)

- Folder ingestion (problematic implementation): `app/services/folder_ingestion.py` — `ingest_folder()` used non-matching fields and performed embedding before persisting DB chunk ids
  - [app/services/folder_ingestion.py](app/services/folder_ingestion.py#L1-L220)

- Upload + background ingestion (correct path): `app/api/ingest.py` — `upload_document()` and `_background_process_document()` persist DB chunks then embed using DB chunk ids
  - [app/api/ingest.py](app/api/ingest.py#L220-L360)

- Vectorstore upsert + query + delete: `app/services/vectorstore.py` — `upsert_embeddings()`, `query()`, `delete_by_document_id()`
  - [app/services/vectorstore.py](app/services/vectorstore.py#L1-L220)

- Cleanup & deletion endpoints: `app/api/ingest.py` — `cleanup_duplicates()` and `delete_document()` which call Pinecone deletion
  - [app/api/ingest.py](app/api/ingest.py#L420-L560)

4) Root-cause summary

- Primary root causes:
  1. Auto-start folder ingestion enabled by default, causing re-ingestion on deploy/restart.
  2. `FolderIngestionService` used inconsistent DB fields and metadata keys, producing vectors with mismatched metadata (e.g., `chunk_index` vs `chunk_id`) which led to ineffective duplicate checks and deletion mismatches.
  3. Metadata-based Pinecone deletion is brittle when metadata types or keys don't match; there was no id-based deletion fallback.
  4. Some ingestion scripts and processes could re-upload the same files (e.g., `upload_all_pdfs.py`, CI hooks) without idempotent checks.

- Secondary contributors:
  - Filename/title normalization differences (underscores, hyphens, spaces) caused duplicate detection by `title` to fail.
  - Default config values (`ENABLE_FOLDER_INGESTION=true`) were unsafe for production deployments.

5) Changes applied (what I patched)

- Added deterministic id-based vector deletion: `VectorStoreService.delete_by_ids(ids)` to delete explicit point IDs (safer than metadata filter).
  - [app/services/vectorstore.py](app/services/vectorstore.py#L1-L220)

- Updated duplicate cleanup and delete endpoints to use id-based deletion (build `"{document_id}_{chunk_id}"` for each DB chunk) and fallback to metadata-based deletion only when id-based fails. (See `cleanup_duplicates()` and `delete_document()` in `app/api/ingest.py`.)
  - [app/api/ingest.py](app/api/ingest.py#L420-L560)

- Reworked `FolderIngestionService.ingest_folder()` to:
  - Check existing documents by `filename` instead of `title`.
  - Persist `DocumentChunk` rows first to obtain deterministic DB chunk ids.
  - Batch-embed chunk texts and upsert to Pinecone using metadata `chunk_id` (DB id) so vector point IDs are deterministic (`"{document_id}_{chunk_id}"`).
  - [app/services/folder_ingestion.py](app/services/folder_ingestion.py#L1-L220)

- Disabled automatic folder ingestion by default: set `ENABLE_FOLDER_INGESTION` default to `false` in `app/config.py` so production deployments don't auto-ingest unless explicitly enabled.
  - [app/config.py](app/config.py#L1-L40)

6) Exact code patches (high level)

- `app/services/vectorstore.py`:
  - Added `delete_by_ids(self, ids: List[str])` method which calls `self.index.delete(ids=ids, namespace=...)`.

- `app/api/ingest.py`:
  - In `cleanup_duplicates()`, collect DB chunk ids for each duplicate document, delete DB rows, then call `vectorstore.delete_by_ids(["{doc_id}_{chunk_id}"])`; fall back to `delete_by_document_id` when id-based deletion fails. Track per-document deletion status.
  - In `delete_document()`, collect chunk ids before removing DB rows and attempt id-based deletion first, fallback to metadata filter.

- `app/services/folder_ingestion.py`:
  - Use `filename=pdf_path.name` for doc lookup and creation.
  - Persist chunk rows (`DocumentChunk(document_id=..., chunk_text=...)`) then commit and refresh to obtain `chunk.id`.
  - Embed in batches and upsert using `{'document_id': doc.id, 'chunk_id': chunk_id, ...}` metadata.

- `app/config.py`:
  - Changed `ENABLE_FOLDER_INGESTION` default to `false`.

7) Recommended safe ingestion lifecycle (design)

- Idempotent document detection
  - Use a deterministic key to identify a PDF: e.g. SHA256(file_bytes) or `filename + file_size + mtime` canonicalized. Store this as `file_checksum` or `source_id` in `documents` table. Use the checksum to skip re-ingestion.

- Deterministic vector IDs
  - Always create vector point IDs deterministically as `"{document_id}_{chunk_id}"` where `chunk_id` is the DB `DocumentChunk.id` (autoincrement). Ensure every ingestion path persists chunks first and uses DB ids in metadata.

- Upsert-only writes
  - Use Pinecone `upsert` (already in `upsert_embeddings`) to replace old vectors for the same point id.
  - Avoid generating random ids or letting external tools create separate vector namespaces unless intentionally versioned.

- Robust deletion
  - When deleting a document, fetch its chunk ids from the DB and call `index.delete(ids=["{doc}_{chunk}"...])` (deterministic). Optionally also run metadata-based deletion as a fallback.

- Startup/deploy safeguards
  - Default `ENABLE_FOLDER_INGESTION=false` in production.
  - Require explicit env var `ENABLE_FOLDER_INGESTION=true` for local development.
  - Optionally store a `last_ingested` marker (DB or lock file) so that auto-ingest runs only once per host unless forced.

- Prevent double-processing
  - When starting an ingestion job, create a short-lived lock (DB row `ingestion_tasks` or file lock) to prevent parallel or repeated ingestion runs from multiple processes.

8) Recommended exact code changes (summary)

- Ensure all ingestion code paths:
  - Persist `Document` then `DocumentChunk` rows first, commit, refresh to get chunk ids.
  - Use `EmbeddingService.embed_texts()` on chunk texts in batches.
  - Upsert embeddings with metadata that includes `chunk_id` and `document_id` and let `VectorStoreService.upsert_embeddings()` construct point ids using `"{document_id}_{chunk_id}"`.

- Update deletion endpoints to delete vectors by explicit IDs (constructed from DB chunk ids) and fallback to metadata-based deletion only when needed.

- Make folder ingestion idempotent by checking `filename` or `file_checksum` before creating a Document row; prefer a checksum approach for robustness.

9) Next steps I can take for you

- Add `file_checksum` column to `Document` model and migration script, then update both upload and folder ingestion to compute checksum and use it for duplicate detection.
- Add a small unit test to assert `VectorStoreService.upsert_embeddings()` produces deterministic point IDs and that `delete_by_ids()` removes them.
- Add an optional one-time marker/lock to `app/main.py` so auto-ingest runs only once per deployment unless forced.

10) Quick remediation commands (run locally)

```powershell
# 1) Rebuild and restart backend (after pulling patches)
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:LOG_LEVEL='debug'
uvicorn app.main:app --reload --port 8000

# 2) Manually run duplicate cleanup
curl -X DELETE 'http://localhost:8000/api/ingest/cleanup-duplicates'

# 3) Verify documents
curl 'http://localhost:8000/api/ingest/documents' | jq
```

11) Files I modified during this analysis
- [app/services/vectorstore.py](app/services/vectorstore.py#L1-L220)
- [app/api/ingest.py](app/api/ingest.py#L1-L220)
- [app/services/folder_ingestion.py](app/services/folder_ingestion.py#L1-L220)
- [app/config.py](app/config.py#L1-L40)

---

If you want, I can now:
- Add `file_checksum` to `app/db/models.py` and implement a small DB migration script.
- Add a safe startup lock to stop repeated folder ingestion on container restarts.
- Run a test ingestion locally (I can run the upload endpoint against a sample PDF and show the Pinecone ids logged). 

Which next step do you want me to take?