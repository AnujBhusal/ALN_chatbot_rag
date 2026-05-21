# PDF Ingestion Workflow & Duplication Issue Analysis

## Complete Workflow: PDF Ingestion to Deployment

### Phase 1: Application Startup (Auto-Ingestion)

**File:** `app/main.py` (startup event handler)

```
1. Application starts
   ↓
2. Check if LOCAL_MODE=true AND ENABLE_FOLDER_INGESTION=true
   ↓
3. If true: Trigger FolderIngestionService.ingest_folder()
   ↓
4. Scan data/pdfs folder for all .pdf files
   ↓
5. For each PDF:
   a. Check if Document with same title exists in PostgreSQL database
   b. If exists: SKIP (already ingested)
   c. If new:
      - Extract text using PyPDF2 (with pdfplumber fallback)
      - Normalize extracted text (encoding fixes)
      - Chunk text using ChunkingService (sentence or sliding window)
      - Generate embeddings for each chunk
      - Store chunks in PostgreSQL (DocumentChunk table)
      - Upsert embeddings to Pinecone vector database
      - Store document metadata in PostgreSQL (Document table)
```

**Files Involved:**
- `app/services/folder_ingestion.py` - Handles folder-based ingestion
- `app/db/models.py` - Document & DocumentChunk schemas
- `app/services/chunking.py` - Text chunking
- `app/services/embeddings.py` - Embedding generation
- `app/services/vectorstore.py` - Pinecone operations

---

### Phase 2: Manual PDF Upload via API

**Endpoint:** `POST /api/ingest/upload`

**File:** `app/api/ingest.py` (upload_document route)

```
1. Client sends multipart form with:
   - file (PDF or TXT)
   - chunk_strategy (sliding or sentence)
   - document_type, title, year, program_name, donor_name

2. Validation:
   - Check chunk_strategy is valid
   - Build document metadata

3. Database Registration:
   - Create Document record in PostgreSQL
   - Return instantly with document ID (non-blocking)

4. Background Processing (ThreadPool):
   a. Extract text from PDF
   b. Normalize text (encoding, whitespace cleanup)
   c. Chunk text based on strategy
   d. Save chunks to PostgreSQL (DocumentChunk table)
   e. Generate embeddings (batched, 50 chunks per batch)
   f. Upsert embeddings to Pinecone with metadata:
      - document_id
      - chunk_id
      - title, document_type, year, filename, filetype
      - text content
   g. Clean up temporary files

5. Return response immediately (processing happens in background)
```

**Key Components:**
- Text extraction: `extract_text_from_file()`, `_extract_text_from_pdf_bytes()`
- Text normalization: `normalize_extracted_text()`
- Embedding storage: Pinecone vector IDs = `{document_id}_{chunk_id}`

---

### Phase 3: Document Retrieval & Chat Queries

**Endpoint:** `POST /api/chat/query`

**File:** `app/api/chat.py` (query route)

```
1. Receive user query
   ↓
2. Generate embedding for the query
   ↓
3. Query Pinecone with:
   - Query embedding vector
   - top_k = 5 (top 5 matching chunks)
   - Optional filters (document_id, document_type, year)
   - Namespace = "default"
   
4. Receive results from Pinecone:
   - Returns chunks with scores
   - Each result includes metadata (document_id, chunk_id, title, text)
   
5. Post-process results:
   - Group by document using group_results_by_document()
   - Deduplicate chunks by chunk_id
   - Sort by relevance score
   - Compute document-level scores (average of top 3 chunks)
   
6. Build context from grouped results:
   - Format retrieved chunks with document headers
   - Create RAG prompt with retrieved context
   
7. Call LLM (Groq):
   - Feed query + context to LLM
   - Get answer
   
8. Return response with:
   - answer (LLM response)
   - sources (list of referenced documents/chunks)
   - document_context (metadata)
```

**Key Files:**
- `app/services/retrieval.py` - group_results_by_document(), deduplication logic
- `app/services/vectorstore.py` - query() method for Pinecone
- `app/services/llm.py` - LLM prompt generation & calling

---

### Phase 4: Document Management

#### 4A: List Documents

**Endpoint:** `GET /api/ingest/documents`

**File:** `app/api/ingest.py`

```
1. Query PostgreSQL for all Document records
2. For each document:
   - Get document metadata (id, title, filetype, uploaded_at)
   - Count chunks in DocumentChunk table
3. Return full list of documents with chunk counts
```

---

#### 4B: Delete Document

**Endpoint:** `DELETE /api/ingest/documents/{document_id}`

**File:** `app/api/ingest.py`

```
⚠️  CRITICAL ISSUE FOUND:

1. Delete DocumentChunk records from PostgreSQL
2. Delete Document record from PostgreSQL
3. Commit transaction
4. ❌ MISSING: Call vectorstore.delete_by_document_id(document_id)
   → Pinecone vectors are NOT deleted!
   → Orphaned chunks remain in Pinecone
   → Future queries may return results from deleted documents
```

---

#### 4C: Cleanup Duplicates

**Endpoint:** `DELETE /api/ingest/cleanup-duplicates`

**File:** `app/api/ingest.py`

```
⚠️  MAJOR ISSUE FOUND:

1. Get all Document records from PostgreSQL
2. Group by title
3. For each title with multiple documents:
   - Keep the LATEST (by upload time)
   - Delete older ones:
     a. Delete DocumentChunk records
     b. Delete Document record
     c. Commit to database
4. ❌ MISSING: Call vectorstore.delete_by_document_id() for each deleted doc
   → Pinecone vectors for deleted documents remain!
   → This is the ROOT CAUSE of duplication!
```

---

### Phase 5: Deployment

**Files Involved:**
- `Dockerfile` - Containerization
- `docker-compose.yml` - Local Docker setup
- `fly.toml` - Fly.io deployment config
- `upload_all_pdfs.py` - Deployment upload script

**Deployment Flow:**

```
1. Build Docker image with app code
2. Deploy to Fly.io (or similar)
3. On startup (container init):
   - Environment variables loaded (PINECONE_API_KEY, DB_URL, etc.)
   - Database initialized
   - Folder ingestion triggered (if ENABLE_FOLDER_INGESTION=true)
   - PDFs from data/pdfs folder are ingested
   
4. Production runs with folder ingestion checking:
   - Checks for existing documents by title
   - Skips already-ingested PDFs
   - BUT: If previous deployment had orphaned Pinecone vectors,
     they won't be cleaned up
```

---

## 🔴 ROOT CAUSE OF DUPLICATION ISSUE

### The Problem: 3 PDFs → 21+ PDFs

Your deployed chatbot is showing **7x duplication** of documents. Here's why:

### Scenario Analysis:

**Initial Deployment (Day 1):**
```
data/pdfs folder contains: doc1.pdf, doc2.pdf, doc3.pdf
↓
Folder ingestion runs:
  - PostgreSQL: 3 Document records created
  - Pinecone: 3 × N chunks stored (N = chunks per document)
```

**Problem Occurs During:**
1. **API uploads** → Documents added without checking Pinecone
2. **Deployments restart** → Folder ingestion runs again
   - Checks PostgreSQL for existing titles
   - Finds them (assumes skip)
   - But doesn't verify Pinecone state
3. **Database cleanup** → Chunks removed from PostgreSQL
   - BUT vectors remain in Pinecone
4. **Re-upload via API** → New Document record created (different ID)
   - Pinecone still has old vectors
   - New query returns BOTH old and new chunks

### Example Timeline:

```
T=0: Upload doc1.pdf
     PostgreSQL: Document ID=1
     Pinecone: Vectors 1_1, 1_2, 1_3, ... (chunks from doc1)

T=1: Delete document ID=1 from database
     PostgreSQL: Document ID=1 REMOVED
     Pinecone: Vectors 1_1, 1_2, 1_3 REMAIN (orphaned!)

T=2: Re-upload same doc1.pdf
     PostgreSQL: Document ID=2 (new ID!)
     Pinecone: Vectors 2_1, 2_2, 2_3 + orphaned 1_1, 1_2, 1_3

T=3: Query for doc1 content
     Pinecone returns: 2_1, 2_2, 2_3, 1_1, 1_2, 1_3 (6 chunks)
     
T=N (multiply this across PDFs):
     3 PDFs × 7 lifecycle cycles = 21+ entries
```

---

## 🔧 ROOT CAUSE LOCATIONS IN CODE

### Issue #1: Missing Pinecone Deletion in Delete Endpoint

**File:** `app/api/ingest.py` (delete_document function)

**Current Code (Lines 502-545):**
```python
@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    # ... validation ...
    
    # Delete from database
    for chunk in chunks:
        db.delete(chunk)
    db.delete(document)
    db.commit()
    
    # ❌ MISSING: vectorstore.delete_by_document_id(document_id)
    
    return { "message": "...", ... }
```

**Impact:** When documents are deleted, Pinecone vectors remain indefinitely

---

### Issue #2: Missing Pinecone Deletion in Cleanup Duplicates

**File:** `app/api/ingest.py` (cleanup_duplicates function)

**Current Code (Lines 420-467):**
```python
@router.delete("/cleanup-duplicates")
async def cleanup_duplicates(db: Session = Depends(get_db)) -> dict:
    # ... find duplicates ...
    
    for old_doc in docs[:-1]:  # Delete all but latest
        # Delete from database
        for chunk in chunks:
            db.delete(chunk)
        db.delete(old_doc)
    
    db.commit()
    
    # ❌ MISSING: vectorstore.delete_by_document_id(old_doc.id)
    
    return { "message": "...", ... }
```

**Impact:** Cleanup removes duplicates from database but leaves Pinecone orphaned

---

### Issue #3: Retrieval Returns Orphaned Vectors

**File:** `app/services/retrieval.py` (group_results_by_document)

The grouping and deduplication happens AFTER Pinecone retrieval:
```python
# Pinecone returns all matching chunks, including orphaned ones
matches = vectorstore.query(embedding, top_k=5)

# Deduplication only happens by chunk_id within results
# But if chunk_ids don't match (different doc_id), both are included
grouped = group_results_by_document(results)
```

**Impact:** Orphaned vectors from old documents are still retrieved

---

### Issue #4: No State Consistency Between PostgreSQL & Pinecone

**Core Design Flaw:**

PostgreSQL is treated as the source of truth:
- Document deletes only remove from PostgreSQL
- Folder ingestion only checks PostgreSQL for existing titles
- No synchronization with Pinecone state

This creates inconsistency:
- PostgreSQL says: 3 documents
- Pinecone contains: 21+ orphaned + current chunks

---

## 📋 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INTERACTION LAYER                      │
│  (Web UI, API calls, manual uploads)                           │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                    INGESTION ENDPOINTS                          │
│  POST /upload  →  POST /cleanup-duplicates  →  DELETE /docs/{id}
└────────────────┬────────────────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        ↓                 ↓
   ┌─────────────┐   ┌──────────────────┐
   │  PostgreSQL │   │ Pinecone Vector  │
   │             │   │ Database         │
   │ Documents   │   │                  │
   │ Chunks      │   │ Embeddings +     │
   │             │   │ Metadata         │
   │ ✅ Proper   │   │ ⚠️ NOT SYNCED   │
   │   cleanup   │   │ (orphans remain) │
   └──────┬──────┘   └─────────┬────────┘
          │                    │
          └────────┬───────────┘
                   ↓
        ┌─────────────────────┐
        │  RETRIEVAL ENGINE    │
        │  (Query Embedding)   │
        │  → Pinecone search   │
        │  → Returns all       │
        │    matching chunks   │
        │    (including orphans)
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │  POST-PROCESSING    │
        │  Grouping           │
        │  Deduplication      │
        │  (Too late - orphans│
        │   already included) │
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │  LLM PROMPT BUILDING│
        │  + RESPONSE         │
        └─────────────────────┘
```

---

## 🛠️ Summary of Issues

| # | Component | Issue | Line Reference |
|---|-----------|-------|-----------------|
| 1 | `ingest.py` | Delete endpoint doesn't delete from Pinecone | 502-545 |
| 2 | `ingest.py` | Cleanup-duplicates doesn't delete from Pinecone | 420-467 |
| 3 | `retrieval.py` | Deduplication happens after Pinecone retrieval | N/A |
| 4 | `vectorstore.py` | delete_by_document_id exists but not called | Never called |
| 5 | `main.py` | Folder ingestion doesn't check Pinecone state | Startup |

---

## 🔑 Key Takeaways

1. **PostgreSQL and Pinecone are out of sync**
   - PostgreSQL: Single source of truth for document metadata
   - Pinecone: Contains orphaned vectors from deleted documents

2. **Deletions are incomplete**
   - Database cleanup works
   - Vector cleanup is skipped

3. **Duplicates accumulate over time**
   - Each redeployment, API upload, or database cleanup
   - Leaves Pinecone in an inconsistent state

4. **Retrieval returns unwanted results**
   - Old deleted PDFs still appear in search results
   - Multiple "versions" of same document appear

---

## Required Fixes

See [PDF_INGESTION_FIX.md](PDF_INGESTION_FIX.md) for detailed solutions:

1. ✅ Add Pinecone deletion to delete_document endpoint
2. ✅ Add Pinecone deletion to cleanup_duplicates endpoint
3. ✅ Implement full Pinecone cleanup utility
4. ✅ Add state consistency checks on startup
5. ✅ Add metrics for tracking PostgreSQL vs Pinecone state
