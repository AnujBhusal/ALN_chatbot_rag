# ALL documents mode — Diagnostic Guide

Purpose
- A single reference to reproduce, debug, and fix issues with "All Documents" (document-mode across every ingested PDF).

Quick reproduction
1) All-docs (search across all PDFs):

```bash
curl -s -X POST 'http://localhost:8000/api/chat/query' \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id":"debug-session",
    "query":"tell me about integrity icon",
    "mode":"documents",
    "document_id": null,
    "use_latest_document": false,
    "role": "staff"
  }' | jq
```

2) Single-doc (compare results):

```bash
curl -s -X POST 'http://localhost:8000/api/chat/query' \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id":"debug-session",
    "query":"tell me about integrity icon",
    "mode":"documents",
    "document_id": 13,
    "use_latest_document": false,
    "role": "staff"
  }' | jq
```

Expected behavior
- When `document_id` is null, the backend queries the vector store across all documents (subject to `document_type`, `year`, and role access filters), groups matches by `document_id`, builds context blocks, and returns an answer with `sources` drawn from multiple documents.

Where the logic lives (inspect these files)
- app/api/chat.py — main query handler, filtering, grouping, fallback ranking, prompt construction.
- app/services/retrieval.py — `group_results_by_document()` and `build_source_items()` (dedupe + per-doc ordering).
- app/services/vectorstore.py — vector DB wrapper; check `query()` implementation and how metadata is returned.
- frontend/src/App.tsx — UI: `mode` selector and `document_id` null "All Documents" option and request payload.
- README-DOCUMENT-MODE.md — existing architecture & debug guide with examples.

Common failure symptoms
- Returned `sources` are empty or missing expected documents.
- Results contain documents but wrong titles/IDs (metadata mismatch).
- Excessive irrelevant documents appear (filtering/boosting broken).
- No results when a specific document should match (metadata type mismatch with vectorstore filters).

Step-by-step debug checklist
1) Confirm frontend payload
- Verify frontend sends `mode: "documents"` and `document_id: null` when "All Documents" is selected.
- Inspect network in browser / reproduce with the curl above.

2) Enable debug logging
- Run backend with `LOG_LEVEL=debug`:

```powershell
$env:LOG_LEVEL='debug'; uvicorn app.main:app --reload --port 8000
```

- Watch console for logs around `🔍 Query:` and `🔎 Raw vector matches` printed in `app/api/chat.py`.

3) Inspect vectorstore raw results
- Add a temporary log around the call to `vectorstore.query(...)` in `app/api/chat.py` to print the full `results` list (metadata keys and types). Example snippet to add above or after the call:

```python
logger.debug(f"RAW VECTOR RESULTS: {results}")
```

- Verify each `result` metadata contains: `document_id`, `chunk_id`, `text`, `title`, `document_type`, `year`.
- Confirm `document_id` values are numeric (or convertable) and consistent with DB `Document.id`.

4) Check filter behavior
- If a `query_filter` was built (document_type/year/document_id), and `results` is empty, the handler will retry without the filter — check logs for the warning `No results with Pinecone filter, retrying unfiltered...` and the subsequent unfiltered results.
- If filters are too strict (wrong `year` or `document_type`), reproduce by constructing queries with and without those values.

5) Verify grouping & source building
- `group_results_by_document()` deduplicates by `chunk_id` or text prefix, sorts by chunk score, and computes per-document order. If grouping seems wrong, create a small python unit test that feeds fake `results` (with `metadata` and `score`) into `group_results_by_document()` and assert ordering.

6) Database fallback
- When `target_document_ids` is set and vector results are empty, the code falls back to DB chunk ranking (`_rank_database_chunks_for_query`) and builds synthetic `results`. Check that branch by forcing an empty vector result (e.g., temporarily set `query_filter` that excludes everything) and confirm DB fallback behavior.

7) Inspect DB and ingestion metadata
- Run `python check_docs.py` or `python check_documents.py` to list documents and chunk counts.
- Confirm that ingestion pipeline stored `document_id` metadata on each vector entry in Pinecone. If missing, re-run ingestion or fix metadata mapping in `app/services/folder_ingestion.py` or `app/services/embeddings.py`.

8) Pinecone/Vectorstore type mismatches
- Pinecone metadata sometimes stores numbers as floats or strings. Backend uses `_coerce_document_id()` to normalize. If vectorstore `query()` returns `document_id` as `'13'` or `13.0`, `_coerce_document_id()` should coerce to int. If not, inspect `vectorstore` wrapper for post-processing.

9) Title-boosting effects
- The code boosts documents whose titles (or title tokens) appear in the query. If the title boost is too aggressive or titles are malformed, unexpected ordering can happen. Inspect the `favored_doc_ids` logic in `app/api/chat.py` and test queries containing title words.

Practical fixes to try
- Ensure vectorstore `query()` returns consistent metadata keys (`document_id`, `title`, `text`, `chunk_id`).
- If metadata keys vary, normalize them in `vectorstore.query()` before returning to the handler.
- If filters use the wrong types, convert (e.g., ints -> floats) or update `_build_query_filter()` to accept string ids.
- Add defensive logging printing `type(md.get('document_id'))` for first N matches.

Minimal temporary debug patch (example)
- Add immediately after the vectorstore call in `app/api/chat.py`:

```python
try:
    for i, r in enumerate(results[:8]):
        md = r.get('metadata', {}) or {}
        logger.debug(f"MATCH {i}: docid={md.get('document_id')} (type={type(md.get('document_id'))}), title={md.get('title')}, score={r.get('score')}")
except Exception:
    logger.debug('Could not log matches')
```

Unit / regression test ideas
- Add a test for `group_results_by_document()` that sends synthetic `results` with duplicated chunk ids and asserts groups are deduped and ordered by average top-3 scores.
- Test `_coerce_document_id()` with `None`, `"13"`, `13.0`, `'13.0'`, and invalid values.

How to run locally (commands)

```powershell
# Activate venv (Windows PowerShell)
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:LOG_LEVEL='debug'
uvicorn app.main:app --reload --port 8000
```

Then run the curl reproduction from above.

How to analyze returned JSON
- `answer` — the LLM response text.
- `sources` — list of documents returned by `build_source_items(results)`. Each source contains `document_id`, `title`, `type`, `year`, `snippet`.
- If `sources` is empty, check `context` construction and the `results` list printed in debug logs.

Checklist to rule out common causes
- [ ] Frontend is sending `document_id: null` correctly for All Documents.
- [ ] Vectorstore returns vectors with `metadata.document_id` present and coercible to int.
- [ ] `query_filter` is not unintentionally overconstraining results (year/type mismatch).
- [ ] Title boosting isn't wrongly promoting irrelevant docs.
- [ ] Fallback DB chunk ranking is reachable and returns sensible content when vectors fail.

If you'd like, next I can:
- Run a live sample query against your local server and show the raw `results` JSON.
- Add the temporary debug logging to `app/api/chat.py` and run a single test query, capturing logs.
- Add the unit test for `group_results_by_document` and run it.

---

Notes
- This guide is intentionally actionable and ordered: reproduce → inspect vector results → inspect grouping → inspect fallback → fix metadata/types.
- Save this file as `ALL documents mode.md` at the repo root for quick reference.
