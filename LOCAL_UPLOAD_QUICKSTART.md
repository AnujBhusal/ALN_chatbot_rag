# Quick Start: Local PDF Upload

## Problem Solved ✅

✅ **No more direct server uploads** - Use folder-based ingestion  
✅ **No server crashes** - Background processing handles everything  
✅ **Works locally AND in production** - Different methods per environment  
✅ **Automatic duplicate detection** - Already-processed PDFs are skipped  

---

## For Local Development (Fastest Way)

### Step 1: Enable Local Mode
Edit `.env`:
```env
LOCAL_MODE=true
ENABLE_FOLDER_INGESTION=true
```

### Step 2: Add PDFs
Copy your PDFs to this folder:
```
Rag-Backend/data/pdfs/
```

### Step 3: Run Backend
```bash
python -m uvicorn app.main:app --reload
```

**That's it!** On startup, the backend will:
- ✅ Scan `./data/pdfs` for PDFs
- ✅ Extract text automatically
- ✅ Generate embeddings & chunks
- ✅ Store in database & Pinecone
- ✅ Skip duplicates

You'll see this in the logs:
```
================================================================================
📚 LOCAL MODE DETECTED - Auto-ingesting PDFs from ./data/pdfs
================================================================================
📚 Found 7 PDFs in ./data/pdfs

📄 Processing: Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf...
   ✓ Extracted 45623 chars
   ✓ Created document record (ID: 1)
   ✓ Generated 127 chunks
   ✓ Generated embeddings (127 vectors)
   ✓ Stored chunks in database
   ✓ Upserted to Pinecone
   ✅ Success

[... more PDFs ...]

✅ Successful: 7
❌ Failed: 0
```

### Step 4: Query Your PDFs
```bash
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test",
    "query": "What is the governance framework?",
    "mode": "documents",
    "role": "staff"
  }'
```

**That's all!** No HTTP uploads, no server crashes, just drop & run.

---

## For Production (Render)

The HTTP upload endpoint is automatically enabled:

```python
import requests

url = 'https://aln-chatbot-rag.onrender.com/api/ingest/upload'

with open('your-pdf.pdf', 'rb') as f:
    response = requests.post(
        url,
        files={'file': (f.name, f, 'application/pdf')},
        data={'chunk_strategy': 'sentence'},
        timeout=45
    )
    print(response.json())
```

Response:
```json
{
  "message": "Document uploaded and processing in background",
  "document_id": 35,
  "status": "processing"
}
```

Backend processes in background - no crashes!

---

## How It Works (Under the Hood)

### Architecture

```
Local Development                    Production (Render)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
data/pdfs/                           HTTP POST Upload
    ↓                                    ↓
Auto-ingest on startup      →      Fast HTTP response
    ↓                                    ↓
Extract text                →      Background thread
    ↓                                    ↓
Chunk & embed               →      Extract, chunk, embed
    ↓                                    ↓
Store in DB + Pinecone      →      Store in DB + Pinecone
    ↓                                    ↓
Ready to query              →      Ready to query (2-3 min)
```

### Key Features

1. **Background Processing**
   - HTTP returns immediately
   - Processing happens in background threads
   - No server crashes even with large PDFs

2. **Duplicate Detection**
   - Already-processed PDFs skipped
   - Uses document title as key
   - Prevents duplicate ingestion

3. **Error Handling**
   - Failed PDFs don't crash server
   - Errors logged for debugging
   - Graceful fallback on embeddings issues

4. **Batched Embeddings**
   - 50 chunks per batch
   - Manages memory efficiently
   - ~5 chunks/sec processing speed

---

## Environment Variables

```env
# Local Mode (auto-detected if not on Render)
LOCAL_MODE=true                    # Set false for production
ENABLE_FOLDER_INGESTION=true      # Enable folder processing

# Embeddings (saves RAM on Render)
USE_HASH_EMBEDDINGS=true          # Use lightweight embeddings

# Database & Services
DB_URL=postgresql://...
PINECONE_API_KEY=...
GROQ_API_KEY=...
```

---

## Cleanup & Management

### Remove Duplicates
```bash
curl -X DELETE https://aln-chatbot-rag.onrender.com/api/ingest/cleanup-duplicates
```

### Check Documents
```bash
curl http://localhost:8000/api/ingest/list-documents
```

### Delete a Document
```bash
curl -X DELETE http://localhost:8000/api/ingest/delete/1
```

---

## What Changed in Code

### New Files
- `app/services/folder_ingestion.py` - Folder-based ingestion service
- `data/pdfs/README.md` - Instructions for PDF folder
- `PDF_UPLOAD_GUIDE.md` - Complete upload guide

### Modified Files
- `app/config.py` - Added LOCAL_MODE & ENABLE_FOLDER_INGESTION flags
- `app/main.py` - Added startup event for auto-ingestion
- `.env.template` - Added local mode documentation

### New Endpoints
- `DELETE /api/ingest/cleanup-duplicates` - Remove duplicates

---

## Troubleshooting

### Local: PDFs not auto-ingesting?

Check:
```bash
# 1. LOCAL_MODE enabled?
grep LOCAL_MODE .env

# 2. PDFs in right folder?
ls -la data/pdfs/

# 3. Check server logs
# Look for "📚 LOCAL MODE DETECTED"
```

### Production: Upload timing out?

Use 45-60s timeout:
```python
requests.post(url, ..., timeout=60)
```

Server returns immediately; processing happens in background (2-3 min).

### Queries returning generic responses?

Wait 2-3 minutes after upload/ingest, then query again.

---

## Summary

### ✅ What You Get

1. **Local Development**
   - Drop PDFs in `data/pdfs/` folder
   - Run server
   - PDFs auto-ingested on startup
   - No HTTP uploads needed

2. **Production (Render)**
   - Use HTTP upload endpoint
   - Backend processes in background
   - No server crashes

3. **Both Environments**
   - Automatic duplicate detection
   - Background processing (no crashes)
   - Query while processing
   - Comprehensive error logging

### 🚀 Next Steps

1. **Local**: Copy PDFs to `data/pdfs/`, set `LOCAL_MODE=true`, run server
2. **Test**: Query with `mode: "documents"`
3. **Production**: Render auto-detects production mode, use HTTP uploads
4. **Optional**: Clean duplicates with cleanup endpoint

**No more server crashes. Simple. Fast. Works everywhere.**
