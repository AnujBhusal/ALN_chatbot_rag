# Duplication Prevention

Strategies implemented

1. File checksum
- Each uploaded PDF is hashed with SHA256 and stored on `Document.file_checksum`.
- Upload and folder ingestion check `file_checksum` before creating a new `Document`.

2. Deterministic vector IDs
- Vector point IDs are `"{document_id}_{chunk_id}"` — based on DB primary keys.
- Upserts replace existing vectors with same point ID, preventing duplicate vectors for the same chunk.

3. DB-based ingestion lock
- Folder ingestion acquires an entry in `ingestion_locks` table with `name='folder_ingest'` to prevent concurrent ingestion runs across multiple workers/containers.

4. Startup safeguards
- `ENABLE_FOLDER_INGESTION` default is `false`.
- Folder ingestion will only run automatically if `ENABLE_FOLDER_INGESTION=true` and (local mode OR `ENABLE_FOLDER_INGESTION_ALLOW_PRODUCTION=true`).

5. Deletion workflow
- Delete vectors by explicit point IDs derived from DB chunk ids when removing a Document.
- Fallback to metadata-based deletion only if id-based deletion fails.

Operational guidance
- Re-ingestion should be performed only after deleting the existing document (DB + vectors) or by explicitly forcing a re-upload with a new checksum (e.g., modified file).
- Monitor logs for `🔐 File checksum` and Pinecone upsert/delete confirmations.

If duplicates persist
- Inspect DB for multiple Documents with identical `file_checksum` values — this should not happen with the unique constraint.
- Run `scripts/add_file_checksum.py` to backfill checksums for existing docs, then run `DELETE /api/ingest/cleanup-duplicates` to remove older duplicates.
