# Recovery and Rollback

## What rollback protects

The ingestion pipeline is designed so that a failed job does not leave behind:
- partial DB chunk rows
- stale Pinecone vectors for the failed document
- ambiguous ingestion state

## Rollback sequence

1. Start with a `pending` document row.
2. Move to `processing`.
3. Insert chunks in a transaction.
4. Upsert vectors using deterministic ids.
5. Verify counts and metadata.
6. If any step fails:
   - rollback DB chunk changes
   - delete any vectors already upserted for this job
   - update document state to `rolled_back` or `failed`
   - record the error message in `ingestion_error`

## When `rolled_back` is used

Use `rolled_back` when:
- the job reached chunk/vector work
- vector cleanup was attempted
- the DB transaction was reverted

This indicates a compensated failure, not a silent crash.

## When `failed` is used

Use `failed` when:
- the job could not safely begin transactional work
- the error happened before chunk/vector work could complete
- the document should remain retryable

## Recovery steps after a failure

1. Inspect `ingestion_error` and logs.
2. Verify whether the PDF checksum already exists.
3. Check whether the document is `failed` or `rolled_back`.
4. Re-run the same PDF through the centralized service.
5. Confirm the document becomes `completed`.

## Recovery after deployment issues

If deployment created duplicates or stale vectors:

1. Disable folder auto-ingestion.
2. Run the audit tool.
3. Delete orphan or duplicate vectors using deterministic ids.
4. Backfill checksums if needed.
5. Re-run ingestion only through the centralized service.

## Safe cleanup rules

- Never delete DB rows without deleting corresponding vectors.
- Never rely on metadata-only vector deletion when deterministic ids are available.
- Never re-ingest a completed checksum unless the document content changed.
- Always verify retrieval after recovery.

## Recommended emergency procedure

If a deployment went bad:

1. Turn off `ENABLE_FOLDER_INGESTION`.
2. Stop any duplicate worker processes.
3. Run the vectorstore audit in dry-run mode.
4. Use safe delete only for confirmed orphan vectors.
5. Rebuild ingestion from the DB source of truth if the namespace is contaminated.
