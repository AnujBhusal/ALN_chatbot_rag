# ALN Chatbot — Document Mode (Architecture & Debug Guide)

This document explains how Document Mode works, the tech stack, and step-by-step instructions to run, reproduce, and debug multi-document vs single-document behavior.

**Overview**

- Document Mode allows users to ask questions scoped to one PDF or across all PDFs.
- Frontend sends `mode='documents'` and either `document_id` (specific) or `null` (all PDFs) to the backend `/api/chat/query` endpoint.
- Backend runs retrieval (embeddings + vector search), assembles document context, and calls the LLM to produce an answer with cited sources.

**Tech Stack & Key Files**

- Frontend: React + Vite (TypeScript)
  - `frontend/src/App.tsx` — UI, document selector, `handleSubmit()` (sends requests to backend)

- Backend: FastAPI (Python)
  - `app/api/chat.py` — main chat flow and query handler (`/api/chat/query`)
  - `app/api/ingest.py` — upload & ingestion endpoint
  - `app/services/retrieval.py` — grouping + building source items
  - `app/services/vectorstore.py` — vector DB wrapper (Pinecone)
  - `app/services/embeddings.py` — embedding logic
  - `app/services/llm.py` — LLM calls and prompt building
  - `app/services/query_rewriter.py` — optional query rewriting
  - `app/db/models.py`, `app/db/session.py` — database models/sessions

- Data store / infra
  - Vector DB: Pinecone (or other vector store)
  - RDBMS: SQLAlchemy-backed DB for `Document` and `DocumentChunk`
  - LLM provider: configured in `app/services/llm.py` (Groq/HF/GPT-like)

**Document Mode Request Flow (concise)**

1. Frontend `handleSubmit()` sends JSON to `/api/chat/query`:
   - `session_id`, `query`, `mode='documents'`
   - `document_id`: number or `null`
   - `document_type`: optional
   - `use_latest_document`: (we now send `false` by default)

2. Backend `chat_query` does: intent detection, optional rewrite, then builds retrieval filters.
   - If `document_id` present → `target_document_ids=[id]` and backend restricts results to that doc (strict).
   - If `document_id` is `null` → search across all documents.

3. Query embedding via `EmbeddingService`.
4. Vector query via `VectorStoreService.query(...)` with metadata filter (if any).
5. If no results with strict filter, backend retries unfiltered and filters in-app.
6. If still empty and `target_document_ids` set, DB chunks are queried and ranked via `_rank_database_chunks_for_query`.
7. Results transformed to grouped-by-document context via `group_results_by_document` → `_build_context_blocks`.
8. LLM prompt is built with `context` and chat history and LLM is called; answer + sources returned to frontend.

**Where mistakes often occur**

- Frontend selected `document_id` different from what you expect.
- Vectorstore metadata has wrong `document_id` or `title` (causes wrong grouping/citation).
- Pinecone query filter excludes the correct document (e.g., year/type/role mismatch).
- Query rewriting changes intent and prioritizes other docs.
- Grouping/ordering previously preserved input ordering — low-relevance docs could appear earlier (we now sum scores and sort groups; we also added title-boosting).

**What changed in this repo**

- Frontend: `frontend/src/App.tsx`
  - Added "All Documents" option; stopped auto-selecting first PDF.
  - Adjusted placeholder and disabled logic so users can ask across all PDFs.
  - `use_latest_document` set to `false` in payload.

- Backend: `app/services/retrieval.py`
  - `group_results_by_document` now aggregates per-result scores and sorts documents by total score.

- Backend: `app/api/chat.py`
  - Added title-boosting logic that prefers documents whose `title` tokens appear in the user query when building final document ordering.

**How to run locally (quick)**

- Backend (venv recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:LOG_LEVEL='info'
uvicorn app.main:app --reload --port 8000
```

- Frontend:

```bash
cd frontend
npm install
npm run dev
# Open the displayed Vite URL (default http://localhost:5173)
```

**Debugging checklist & commands**

1) List documents (IDs + titles):

```bash
curl -s 'http://localhost:8000/api/chat/documents?role=staff' | jq
```

2) Reproduce `all documents` query and inspect returned JSON (answer + sources):

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

3) Reproduce single-document query (replace ID):

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

4) If results look wrong: enable debug logs and inspect intermediate variables.

- Edit `app/main` or run with env var `LOG_LEVEL=debug` and check console logs:

```powershell
$env:LOG_LEVEL='debug'; uvicorn app.main:app --reload --port 8000
```

- Add temporary logging in `app/api/chat.py` around `results = vectorstore.query(...)` and before `llm.call_llm(prompt)` to print `results` and `context`.

5) Inspect DB chunks for a document to ensure chunks exist:

```bash
python - <<'PY'
from app.db.session import get_db
from app.db import models
db = next(get_db())
docs = db.query(models.Document).filter(models.Document.title.ilike('%Integrity Icon%')).all()
print([(d.id,d.title) for d in docs])
if docs:
    chunks = db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id==docs[0].id).limit(5).all()
    print([c.chunk_text[:200] for c in chunks])
PY
```

6) Inspect raw Pinecone matches (in `app/services/vectorstore.py`): log the `matches` list and metadata to confirm `document_id`/`title` values.

**Verification steps for your reported issue**

- Step A: Run the `all-docs` curl (step 2) with your problematic query and save the JSON.
- Step B: Verify `sources` array — do the titles include the ALN Annual Report? If not, examine `results` printed from vectorstore to see whether the report matched at all.
- Step C: If the report appears in `results` but not in top grouped contexts, check the aggregated score and title-boost logic to see why it was outranked.
- Step D: If `document_id` mapping is wrong or missing, confirm the embedding/ingest pipeline assigned correct metadata (`document_id` in Pinecone vectors).

**Unit test idea (optional)**

Add a small test that simulates `results` from Pinecone (fake metadata + scores) and asserts `group_results_by_document` returns groups ordered by aggregated relevance. See `app/services/retrieval.py`.

**Next steps I can do for you**

- Run the reproduction `curl` against your local or deployed backend and analyze the returned JSON.
- Add temporary debug logging and run a single test to capture `results`/`context` so we can see which document was used.
- Add a unit test for `group_results_by_document` to guard against regressions.

---

If you'd like, I can also commit this README into the repo as `README-DOCUMENT-MODE.md` for your convenience. Would you like me to add it now?