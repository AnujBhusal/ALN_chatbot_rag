# Transactional Ingestion Architecture

## Goal

All ingestion flows now use one centralized transactional pipeline: uploads, folder scans, scripts, and future jobs. The pipeline owns checksum validation, state transitions, chunk persistence, vector upserts, verification, rollback, and cleanup.

## Central service

The single implementation lives in `app/services/ingestion_service.py`.

It is called by:
- Upload API: `app/api/ingest.py`
- Folder ingestion wrapper: `app/services/folder_ingestion.py`
- Local job runner: `scripts/run_ingestion_job.py`
- Future batch jobs or schedulers

## Ingestion trigger points

1. Upload API receives a file.
2. Folder startup scan enumerates `data/pdfs` when explicitly enabled.
3. Script runner ingests a single PDF or folder.
4. Future jobs should call `IngestionService` directly.

## Transaction model

The pipeline uses two phases:

1. Durable document state phase
- Create or reuse the `Document` row.
- Set `ingestion_state` to `pending` and then `processing`.
- Commit that state so the job is observable even if later stages fail.

2. Protected chunk/vector phase
- Remove stale chunks only inside the protected transaction.
- Insert `DocumentChunk` rows.
- Flush to get deterministic chunk ids.
- Generate embeddings.
- Upsert vectors using deterministic ids.
- Verify vector count, metadata integrity, and retrieval health.
- Commit only after verification passes.

If any step fails:
- Roll back chunk DB changes.
- Delete any vectors already upserted for that job.
- Mark the document `rolled_back` or `failed`.

## Deterministic identifiers

Vector point ids use the format:

`{document_id}_{chunk_id}`

This means:
- The same document chunk always maps to the same vector id.
- Upsert is idempotent.
- Deletion can be exact and safe.
- Duplicate vectors are prevented at the point-id level.

## Checksum strategy

Every PDF is hashed with SHA256.

Checksum rules:
- Store checksum in `Document.file_checksum`.
- If the checksum already exists and the document completed previously, skip ingestion.
- If the checksum exists with `failed` or `rolled_back`, reuse the same document row and retry safely.
- This makes repeated uploads retry-safe and non-duplicating.

## Upsert logic

- Chunk rows are inserted first so chunk ids are stable.
- Metadata for each vector includes:
  - `document_id`
  - `chunk_id`
  - `title`
  - `document_type`
  - `year`
  - `source`
- Vectors are upserted in Pinecone with deterministic point ids.

Because the id is deterministic, re-running the same ingestion does not create new vectors; it replaces the old ones.

## Verification after ingestion

The service verifies:
- Expected chunk count matches inserted chunk rows.
- Pinecone fetch by point id returns the same vector count.
- Metadata `document_id` and `chunk_id` match the DB ids.
- A retrieval smoke test returns results for the ingested document.

If verification fails, the pipeline rolls back and records diagnostics.

## Deployment safeguards

- `ENABLE_FOLDER_INGESTION` defaults to `false`.
- `ENABLE_FOLDER_INGESTION_ALLOW_PRODUCTION` must be explicitly enabled for production startup ingestion.
- Folder ingestion uses a DB-backed singleton lock so only one worker/container can run the scan at a time.
- Scripts should call the centralized service, not duplicate ingestion logic.

## Pinecone persistence behavior

Pinecone vectors persist across restarts and deployments.

That means:
- Restarting the app does not delete vectors.
- Re-running ingestion with random ids causes duplication.
- Re-running ingestion with deterministic ids is safe.
- Deleting DB rows alone does not remove vectors; explicit vector deletion is required.

## DB and vector synchronization

The database is the source of truth for:
- document existence
- chunk ids
- document states
- checksum identity

The vector store mirrors the DB chunk graph.

Synchronization rules:
- DB chunk rows must exist before vector ids are built.
- Vector upsert must succeed before the job is marked completed.
- Any failed job must remove temporary vectors and update state.
- Deleting a document must delete both DB chunks and vectors.

## Retrieval dependency on metadata consistency

Retrieval assumes vector metadata is correct.

If metadata is wrong:
- `document_id` filters fail
- grouped results can mis-order
- deleted documents may still appear in references
- all-documents mode can be polluted by stale vectors

That is why the pipeline verifies metadata immediately after ingestion.
