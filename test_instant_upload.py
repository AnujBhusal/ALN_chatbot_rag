#!/usr/bin/env python3
"""Test instant upload with full background processing."""
import requests
from pathlib import Path
import time

BASE_URL = "https://aln-chatbot-rag.onrender.com/api"
pdf_path = Path("Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf")

print("⏳ Waiting 90s for Render deployment...\n")
time.sleep(90)

print("=" * 70)
print("✅ TESTING INSTANT UPLOAD WITH BACKGROUND PROCESSING")
print("=" * 70)

# Step 1: Upload should be INSTANT
print("\n📤 Step 1: Uploading PDF (should be instant)...\n")

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
        r = requests.post(f"{BASE_URL}/ingest/upload", files=files, data=data, timeout=10)
        elapsed = time.time() - start
        
        print(f"   ⏱️  Upload took {elapsed:.1f}s (should be <2s)")
        print(f"   📊 Status: {r.status_code}\n")
        
        if r.status_code == 200:
            result = r.json()
            doc_id = result.get('document_id')
            status = result.get('status')
            
            print(f"   ✅ SUCCESS!")
            print(f"      - Document ID: {doc_id}")
            print(f"      - Status: {status}")
            print(f"      - Message: {result.get('message')}")
            
            # Step 2: Check documents list
            print(f"\n⏳ Step 2: Waiting 5s for background processing to start...")
            time.sleep(5)
            
            print(f"   Checking document list...")
            r = requests.get(f"{BASE_URL}/chat/documents", timeout=10)
            if r.status_code == 200:
                docs = r.json()
                for doc in docs:
                    if doc['id'] == doc_id:
                        print(f"   ✅ Document found in database!")
                        print(f"      - Title: {doc['title']}")
                        print(f"      - Chunk count: {doc.get('chunk_count', 'N/A')}")
            
            # Step 3: Wait for background processing and test query
            print(f"\n⏳ Step 3: Waiting 60s for background embedding/upsert to complete...")
            for i in range(12):
                print(f"   {(i+1)*5}s / 60s...", end="\r")
                time.sleep(5)
            
            print(f"\n   Testing document mode query...")
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
                result = r.json()
                answer = result.get('answer', 'No response')
                print(f"\n   ✅ Query successful!")
                print(f"      Response: {answer[:150]}...")
            else:
                print(f"\n   ❌ Query failed: {r.status_code}")
                
        else:
            print(f"   ❌ Upload failed: {r.status_code}")
            print(f"      {r.text[:300]}")
            
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("✅ TEST COMPLETE")
print("=" * 70)
