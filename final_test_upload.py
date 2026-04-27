#!/usr/bin/env python3
"""Final test of upload with background embedding."""
import requests
from pathlib import Path
import time

BASE_URL = "https://aln-chatbot-rag.onrender.com/api"
pdf_path = Path("Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf")

print("📤 Uploading PDF with background embedding...\n")

with open(pdf_path, "rb") as f:
    files = {"file": (pdf_path.name, f, "application/pdf")}
    data = {
        "title": "Assessment Brief CMP6230",
        "document_type": "general",
        "year": "2024",
        "chunk_strategy": "sentence"
    }
    
    start = time.time()
    r = requests.post(f"{BASE_URL}/ingest/upload", files=files, data=data, timeout=60)
    elapsed = time.time() - start
    
    print(f"⏱️  Completed in {elapsed:.1f}s")
    print(f"📊 Status: {r.status_code}\n")
    
    if r.status_code == 200:
        result = r.json()
        print("✅ Upload successful!")
        print(f"   - Document ID: {result.get('document_id')}")
        print(f"   - Chunks: {result.get('chunk_count')}")
        print(f"   - Embedding: {result.get('embedding_status')}")
        print("\n💡 Background processing started")
        print("   Embeddings will be generated and upserted to Pinecone")
        print("   Check back in ~2 minutes for vector search to work")
    else:
        print(f"❌ Upload failed: {r.status_code}")
        print(f"   {r.text[:300]}")
