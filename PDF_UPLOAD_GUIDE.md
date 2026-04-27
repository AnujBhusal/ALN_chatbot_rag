# PDF Upload Processes - Local vs Production

## Overview

The backend now supports **two PDF upload methods** to avoid server crashes and support both local development and production environments:

1. **Local Folder Ingestion** - For development (PDFs auto-ingested from `./data/pdfs` on startup)
2. **HTTP Upload Endpoint** - For production (direct HTTP uploads to Render backend)

---

## Method 1: Local Folder Ingestion (Recommended for Local Development)

### How It Works

When you run the backend **locally**:
1. The server detects LOCAL_MODE is enabled
2. On startup, it automatically scans `./data/pdfs` folder for PDFs
3. Any new PDFs are extracted, chunked, embedded, and stored
4. Already-processed PDFs are skipped (no duplicates)
5. Frontend queries work immediately after startup

### Setup Steps

#### Step 1: Enable Local Mode
Edit your `.env` file:
```env
LOCAL_MODE=true
ENABLE_FOLDER_INGESTION=true
```

Or these will auto-detect (LOCAL_MODE=true if not on Render):
```env
# Leave these unset for auto-detection
# LOCAL_MODE will be true on local machine, false on Render
# ENABLE_FOLDER_INGESTION will be true by default
```

#### Step 2: Add PDFs to Folder
Copy your PDFs to the `./data/pdfs` folder:
```
Rag-Backend/
├── data/
│   └── pdfs/
│       ├── Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf
│       ├── General_Document.pdf
│       ├── Donor_Proposal.pdf
│       ├── Meeting_Notes.pdf
│       ├── Internal_Policy.pdf
│       ├── Integrity_Icon.pdf
│       └── Governance_Weekly.pdf
```

#### Step 3: Run the Server
```bash
python -m uvicorn app.main:app --reload
```

**Expected Output:**
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

...

================================================================================
📊 FOLDER INGESTION SUMMARY
================================================================================
Total PDFs: 7
✅ Successful: 7
❌ Failed: 0

✅ Assessment Brief... (ID: 1, 127 chunks)
✅ General_Document (ID: 2, 89 chunks)
...
================================================================================
```

#### Step 4: Query the Backend
```bash
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session",
    "query": "What is the governance framework?",
    "mode": "documents",
    "role": "staff"
  }'
```

### Advantages
✅ **No HTTP upload needed** - Just drop PDFs in folder  
✅ **Fast iteration** - Add PDFs, restart server, immediately query  
✅ **No server crashes** - Background processing handles all errors  
✅ **No duplicates** - Already-processed PDFs skipped automatically  
✅ **Perfect for testing** - Isolated local environment  

### Disabling Folder Ingestion (if needed)
```env
ENABLE_FOLDER_INGESTION=false
```

---

## Method 2: HTTP Upload Endpoint (For Production)

### How It Works

The production Render backend accepts direct PDF uploads via HTTP:
1. Frontend or script uploads PDF via HTTP POST
2. Backend returns immediately with document ID
3. Background thread processes PDF asynchronously
4. No server crashes even with large PDFs

### Setup in Production

The HTTP upload is already enabled on Render. Ensure:
```env
# On Render (production):
LOCAL_MODE=false        # This is auto-detected
ENABLE_FOLDER_INGESTION=false  # Disable local folder processing
```

### Upload via Python Script

```python
import requests

BASE_URL = 'https://aln-chatbot-rag.onrender.com/api'
PDF_PATH = 'path/to/your/file.pdf'

with open(PDF_PATH, 'rb') as f:
    files = {'file': (f.name, f, 'application/pdf')}
    data = {
        'chunk_strategy': 'sentence',
        'metadata': {'source': 'production'}
    }
    
    response = requests.post(
        f'{BASE_URL}/ingest/upload',
        files=files,
        data=data,
        timeout=45
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Uploaded - ID: {result['document_id']}")
        print(f"   Status: {result['status']}")
        print(f"   Processing in background...")
```

### Upload via cURL

```bash
curl -X POST https://aln-chatbot-rag.onrender.com/api/ingest/upload \
  -F "file=@Assessment Brief.pdf" \
  -F "chunk_strategy=sentence" \
  -F "metadata={\"source\":\"production\"}"
```

### Advantages
✅ **Controlled uploads** - Only upload what's needed  
✅ **Remote access** - Works from anywhere with internet  
✅ **Batch uploads** - Upload multiple PDFs  
✅ **Production-ready** - No folder dependencies  

### Expected Response
```json
{
  "message": "Document uploaded and processing in background",
  "document_id": 35,
  "status": "processing",
  "metadata": {
    "source": "production",
    "uploaded_at": "2024-04-27T15:30:45"
  }
}
```

---

## Comparison: Local vs Production

| Feature | Local Folder | HTTP Upload |
|---------|-------------|------------|
| **Environment** | Local development | Production (Render) |
| **Setup** | Drop PDFs in `./data/pdfs` | Upload via HTTP |
| **Auto-processing** | ✅ On startup | ✅ Background thread |
| **Server crashes** | ❌ No (async processing) | ❌ No (async processing) |
| **Immediate availability** | ✅ Yes | ✅ Yes (while processing) |
| **Duplicates** | ✅ Skipped automatically | ✅ Can use cleanup endpoint |
| **Scaling** | ❌ Limited to local storage | ✅ Unlimited uploads |
| **Remote access** | ❌ No | ✅ Yes |

---

## Cleanup Duplicates

Remove duplicate PDFs from the database:

**Endpoint:** `DELETE /api/ingest/cleanup-duplicates`

```bash
curl -X DELETE https://aln-chatbot-rag.onrender.com/api/ingest/cleanup-duplicates
```

**Response:**
```json
{
  "deleted_count": 2,
  "deleted_documents": ["Assessment Brief (2024-04-25)", "Old Version"],
  "message": "Cleanup complete"
}
```

---

## Troubleshooting

### Local Mode: PDFs Not Being Ingested

1. **Check LOCAL_MODE is enabled:**
   ```bash
   echo $LOCAL_MODE  # Should print "true"
   ```

2. **Verify PDFs are in correct folder:**
   ```bash
   ls data/pdfs/  # Should list your PDFs
   ```

3. **Check server logs for errors:**
   ```
   Look for "📚 LOCAL MODE DETECTED" message on startup
   ```

4. **Manually trigger ingestion** (if needed):
   ```python
   from app.services.folder_ingestion import FolderIngestionService
   service = FolderIngestionService()
   results = service.ingest_folder()
   print(results)
   ```

### Production: Uploads Timing Out

1. **Increase timeout:**
   - Render free tier is slow; use 45-60s timeout
   - Backend returns immediately; processing happens in background

2. **Check server logs:**
   - Go to https://dashboard.render.com → aln-chatbot-rag → Logs
   - Look for "✅ Successfully upserted" messages

3. **Wait for processing:**
   - Give backend 2-3 minutes after upload before querying
   - Background threads process in parallel

### Queries Return Generic Responses

1. **Verify documents were ingested:**
   ```bash
   # Check database for documents
   SELECT * FROM document;
   ```

2. **Check vector store:**
   - Ensure Pinecone upserts succeeded (check logs)
   - Verify embedding dimension is 384

3. **Query with debug:**
   ```json
   {
     "session_id": "debug",
     "query": "test query",
     "mode": "documents"
   }
   ```

---

## Environment Variables Summary

```env
# Local Development Mode
LOCAL_MODE=true|false               # Auto-detected if not set
ENABLE_FOLDER_INGESTION=true|false  # Enable folder-based ingestion

# Both methods use these:
DB_URL=postgresql://...             # Database connection
PINECONE_API_KEY=...                # Vector store
GROQ_API_KEY=...                    # LLM provider
USE_HASH_EMBEDDINGS=true|false      # Use lightweight embeddings (saves RAM on Render)
```

---

## Summary

### For Local Development:
1. Copy PDFs to `./data/pdfs/`
2. Set `LOCAL_MODE=true` in `.env`
3. Run `python -m uvicorn app.main:app --reload`
4. PDFs auto-process on startup ✅
5. Query immediately ✅

### For Production (Render):
1. Use the HTTP upload endpoint
2. Backend auto-detects production mode (`LOCAL_MODE=false`)
3. Upload PDFs via API
4. Query after 2-3 minutes ✅

**No more server crashes! Both methods handle errors gracefully with background processing.**
