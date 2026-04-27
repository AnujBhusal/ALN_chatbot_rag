#!/usr/bin/env python3
"""Test upload with fixed background embedding."""
import requests
import time
from pathlib import Path

BASE_URL = "https://aln-chatbot-rag.onrender.com/api"

print("⏳ Waiting for Render deployment (3 minutes)...")
for i in range(18):
    print(f"   {i*10}s...", end="\r")
    time.sleep(10)

print("\n✅ Testing upload with background embedding...\n")

pdf_path = Path("Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf")

if not pdf_path.exists():
    print(f"❌ File not found")
    exit(1)

try:
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        data = {
            "title": "Assessment Brief CMP6230",
            "document_type": "general",
            "year": "2024",
            "chunk_strategy": "sentence"
        }
        
        print(f"📤 Uploading PDF...\n")
        
        start = time.time()
        r = requests.post(
            f"{BASE_URL}/ingest/upload",
            files=files,
            data=data,
            timeout=30
        )
        elapsed = time.time() - start
        
        print(f"⏱️  Upload completed in {elapsed:.1f}s")
        print(f"📊 Status: {r.status_code}\n")
        
        if r.status_code == 200:
            result = r.json()
            print(f"✅ Upload successful!")
            print(f"   - Document ID: {result.get('document_id')}")
            print(f"   - Chunks: {result.get('chunk_count')}")
            print(f"   - Embedding status: {result.get('embedding_status')}")
            print(f"\n💡 Embeddings generating in background...")
            print(f"   Wait ~2 min for Pinecone upsert to complete")
            print(f"   Then test: 'What is academic misconduct?'")
        else:
            print(f"❌ Upload failed: {r.status_code}")
            print(f"   Response: {r.text[:200]}")
            
except Exception as e:
    print(f"❌ Error: {e}")
