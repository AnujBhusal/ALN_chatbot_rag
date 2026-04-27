#!/usr/bin/env python3
"""Upload PDF with detailed timing and error handling."""
import requests
import time
from pathlib import Path

BASE_URL = "https://aln-chatbot-rag.onrender.com/api"

print("📤 UPLOADING PDF WITH DETAILED TIMING\n")

pdf_path = Path("Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf")

if not pdf_path.exists():
    print(f"❌ File not found: {pdf_path}")
    exit(1)

print(f"📄 File: {pdf_path.name}")
print(f"📊 Size: {pdf_path.stat().st_size:,} bytes\n")

try:
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        data = {
            "title": "Assessment Brief CMP6230",
            "document_type": "general",
            "year": "2024",
            "chunk_strategy": "sentence"
        }
        
        print(f"🚀 Uploading to {BASE_URL}/ingest/upload")
        print(f"   Timeout: 180 seconds\n")
        
        start = time.time()
        r = requests.post(
            f"{BASE_URL}/ingest/upload",
            files=files,
            data=data,
            timeout=180
        )
        elapsed = time.time() - start
        
        print(f"⏱️  Request took {elapsed:.1f} seconds")
        print(f"📊 Response status: {r.status_code}\n")
        
        if r.status_code == 200:
            result = r.json()
            print(f"✅ Upload successful!")
            print(f"   - Document ID: {result.get('document_id')}")
            print(f"   - Metadata: {result.get('metadata')}")
        else:
            print(f"❌ Upload failed!")
            try:
                err = r.json()
                print(f"   Error: {err}")
            except:
                print(f"   Response: {r.text[:500]}")
            
except requests.exceptions.Timeout:
    print(f"❌ Request timed out after 180 seconds")
    print(f"   (Embedding generation may still be in progress on server)")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
