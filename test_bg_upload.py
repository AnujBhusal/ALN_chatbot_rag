#!/usr/bin/env python3
"""Test upload with new background embedding."""
import requests
import time
from pathlib import Path

BASE_URL = "https://aln-chatbot-rag.onrender.com/api"

print("⏳ Waiting for Render deployment (3 minutes)...")
time.sleep(180)

print("\n✅ Testing new background embedding upload...\n")

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
        
        print(f"📤 Uploading PDF (should be fast now)...\n")
        
        start = time.time()
        r = requests.post(
            f"{BASE_URL}/ingest/upload",
            files=files,
            data=data,
            timeout=30  # Should complete much faster
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
            print(f"\n💡 Embeddings are now being generated in background...")
            print(f"   Check Render logs for: '[BG] Starting embedding' and '[BG] Upserting'")
        else:
            print(f"❌ Upload failed")
            print(f"   Response: {r.text[:500]}")
            
except requests.exceptions.Timeout:
    print(f"❌ Request timed out (embedding might still succeed in background)")
except Exception as e:
    print(f"❌ Error: {e}")
