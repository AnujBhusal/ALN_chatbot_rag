# Vectorstore Audit Tool

The `scripts/vectorstore_audit.py` script audits consistency across:
- PostgreSQL / MySQL document tables
- Document chunks
- Pinecone vectors
- Vector metadata
- Uploaded PDF files

It generates:
- `audit_report.json`
- `duplicate_report.json`
- `orphan_vectors.json`
- `missing_vectors.json`
- `per_document_stats.json`
- `retrieval_health.json`

## What it checks

- Duplicate vectors
- Duplicate checksums
- Orphan vectors with no DB document
- DB documents with missing vectors
- Deleted PDFs still present in Pinecone
- Vector metadata mismatches
- Invalid document_id values
- Duplicate chunk IDs
- Namespace contamination
- Chunk count mismatches
- Retrieval health diagnostics

## How it works

The tool uses the repository's deterministic vector ID scheme:
- `point_id = "{document_id}_{chunk_id}"`

It compares:
- DB documents and chunks
- Expected vector IDs from DB chunk rows
- Pinecone vectors fetched by ID
- Metadata stored with each vector

## Run it

```powershell
& .\.venv\Scripts\Activate.ps1
python scripts\vectorstore_audit.py --output-dir .\audit_reports --dry-run
```

## Safe cleanup mode

Use this when you want the tool to delete only verified orphan vectors.

```powershell
python scripts\vectorstore_audit.py --output-dir .\audit_reports --safe-delete --confirm
```

- `--safe-delete` enables deletion logic.
- `--confirm` is required to actually delete.
- Without `--confirm`, the script stays in dry-run mode.

## Rebuild recommendation mode

If the tool reports:
- many missing vectors
- widespread metadata mismatches
- namespace contamination
- duplicate checksums across active documents

then the recommended remediation is:
1. Stop auto-ingestion.
2. Back up DB and Pinecone state.
3. Rebuild vectors from the DB source of truth.
4. Delete stale vectors in the contaminated namespace.
5. Re-run the audit tool.

## Deployment usage

Run the audit after:
- deploying a new release
- re-enabling ingestion
- bulk uploads
- cleanup jobs
- deleting documents
- migrating DB schema

Suggested maintenance workflow:
1. Run in dry-run mode.
2. Review `audit_report.json` and `duplicate_report.json`.
3. If safe, run `--safe-delete --confirm`.
4. Re-run the audit to confirm the namespace is clean.

## Notes and limitations

- Pinecone does not expose a simple "list all vector IDs" operation in a way that is portable across all clients. This tool therefore validates the known deterministic IDs derived from DB rows.
- If a namespace was polluted by a previous non-deterministic ingestion process, a full rebuild may be faster than attempting piecemeal cleanup.
- Retrieval health checks sample a few documents and query them back to ensure the vectorstore still returns the expected docs.
