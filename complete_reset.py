#!/usr/bin/env python3
"""
Complete cleanup and re-ingest workflow:
1. Delete all documents from database and Pinecone
2. Re-upload PDFs from project directory
3. Test with queries
"""

import requests
import os
import time
from pathlib import Path

BACKEND_URL = "https://aln-chatbot-rag.onrender.com/api/ingest"

# PDF files to upload
PDFS = [
    {"file": "Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf", "title": "Assessment Brief CMP6230", "type": "general", "year": 2024},
]

print("=" * 70)
print("🔧 DOCUMENT RESET & RE-INGEST WORKFLOW")
print("=" * 70)

# Step 1: Cleanup
print("\n🧹 Step 1: Cleaning up old documents...")
try:
    response = requests.delete(f"{BACKEND_URL}/cleanup-duplicates", timeout=30)
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ Cleanup successful!")
        print(f"      - Deleted {result.get('total_deleted')} documents")
        print(f"      - Deleted {result.get('total_chunks_deleted')} chunks")
    else:
        print(f"   ❌ Cleanup failed: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Wait a moment
time.sleep(2)

# Step 2: Re-upload PDFs
print("\n📤 Step 2: Re-uploading PDFs...")
project_root = Path.cwd()
success = 0
failed = 0

for pdf_info in PDFS:
    file_path = project_root / pdf_info["file"]
    
    if not file_path.exists():
        print(f"   ❌ Not found: {pdf_info['file']}")
        failed += 1
        continue
    
    print(f"\n   📄 Uploading: {pdf_info['file']}")
    print(f"      - Title: {pdf_info['title']}")
    
    try:
        with open(file_path, "rb") as f:
            files = {"file": (pdf_info["file"], f, "application/pdf")}
            data = {
                "chunk_strategy": "sliding",
                "title": pdf_info["title"],
                "document_type": pdf_info["type"],
                "year": str(pdf_info["year"]),
            }
            
            response = requests.post(f"{BACKEND_URL}/upload", files=files, data=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                print(f"      ✅ Success! Doc ID: {result.get('document_id')}")
                success += 1
            else:
                print(f"      ❌ Failed: {response.status_code}")
                print(f"         {response.text[:200]}")
                failed += 1
    except Exception as e:
        print(f"      ❌ Error: {e}")
        failed += 1

# Summary
print("\n" + "=" * 70)
print(f"✅ Uploaded: {success} | ❌ Failed: {failed}")
print("=" * 70)

# Step 3: Test
print("\n🧪 Step 3: Testing...")
time.sleep(2)

test_queries = [
    "What is this document about?",
    "What is academic misconduct?",
]

for query in test_queries:
    print(f"\n   📝 Query: '{query}'")
    try:
        response = requests.post(
            "https://aln-chatbot-rag.onrender.com/api/chat/query",
            json={
                "session_id": "test-session",
                "query": query,
                "mode": "documents",
                "role": "staff"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get("answer", "")[:100]
            print(f"      ✅ Response: {answer}...")
        else:
            print(f"      ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"      ❌ Error: {e}")

print("\n✅ Workflow complete! Check logs at:")
print("   https://dashboard.render.com → your service → Logs tab")
print("\nLook for:")
print("   - '📤 Upserting X vectors to Pinecone'")
print("   - '✅ Successfully upserted'")
print("   - '📊 Retrieved X results from Pinecone'")
