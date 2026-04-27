#!/usr/bin/env python3
"""Test upload with hash embeddings enabled."""
import requests
from pathlib import Path
import time

BASE_URL = "https://aln-chatbot-rag.onrender.com/api"
pdf_path = Path("Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf")

print("⏳ Waiting 60s for Render deployment...\n")
time.sleep(60)

print("✅ Testing upload with hash embeddings...\n")

# First, delete all old documents
print("Step 1: Cleaning up old documents...")
try:
    r = requests.get(f"{BASE_URL}/chat/documents", timeout=10)
    if r.status_code == 200:
        docs = r.json()
        for doc in docs:
            requests.delete(f"{BASE_URL}/chat/documents/{doc['id']}?role=admin", timeout=10)
        print(f"   ✅ Deleted {len(docs)} old documents")
except Exception as e:
    print(f"   ⚠️  Could not clean up: {e}")

# Upload new PDF
print("\nStep 2: Uploading PDF...")
try:
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
        
        print(f"   ⏱️  Upload took {elapsed:.1f}s")
        print(f"   📊 Status: {r.status_code}\n")
        
        if r.status_code == 200:
            result = r.json()
            doc_id = result.get('document_id')
            chunks = result.get('chunk_count')
            status = result.get('embedding_status')
            
            print(f"✅ Upload successful!")
            print(f"   - Document ID: {doc_id}")
            print(f"   - Chunks: {chunks}")
            print(f"   - Embedding: {status}")
            
            # Test document mode query after 10 seconds
            print(f"\nStep 3: Testing document mode query...")
            time.sleep(10)
            
            r = requests.post(
                f"{BASE_URL}/chat/query",
                json={
                    "query": "What is academic misconduct?",
                    "mode": "documents",
                    "session_id": "test_session"
                },
                timeout=30
            )
            
            if r.status_code == 200:
                answer = r.json().get('answer', 'No response')
                print(f"\n✅ Query successful!")
                print(f"   Response: {answer[:200]}...")
            else:
                print(f"\n❌ Query failed: {r.status_code}")
                
        else:
            print(f"❌ Upload failed: {r.status_code}")
            print(f"   {r.text[:300]}")
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
