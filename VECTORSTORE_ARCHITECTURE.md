# Vector Store Architecture

Overview
- Vector store: Pinecone (configurable via `VECTOR_STORE` env var).
- Index name: configured by `PINECONE_INDEX` / `PINECONE_NAMESPACE` in `app/config.py`.
- Point ID strategy: deterministic IDs in the form `{document_id}_{chunk_id}` where `chunk_id` is the DB `DocumentChunk.id`.

Key code
- `app/services/vectorstore.py` — wraps Pinecone client, provides `upsert_embeddings()`, `query()`, `delete_by_document_id()`, and `delete_by_ids()`.

Upsert logic
- `upsert_embeddings()` builds point IDs from metadata: `f"{doc_id}_{chunk_id}"` and calls `index.upsert(vectors=vectors, namespace=...)`.
- Upsert guarantees idempotency if the same point ID is used — older vectors are replaced.

Deletion workflow
- Preferred path: delete by explicit point IDs using `delete(ids=[...])` to ensure deterministic removal.
- Fallback: delete by metadata filter `filter={"document_id":{"$eq": document_id}}` when id-based deletion is not possible.

Persistence
- Pinecone stores vectors outside the app lifecycle; vectors persist across app restarts, but cleaning up requires explicit deletion.
- Ensure metadata types align (ints vs strings) — we coerce to strings for point IDs and keep `document_id` numeric in metadata.

Best practices
- Always persist DB chunk rows before embedding to obtain deterministic `chunk_id` values.
- Use `file_checksum` on `Document` to avoid re-ingestion and duplicate vectors.
- Use id-based deletion whenever possible to avoid metadata-type mismatches.
