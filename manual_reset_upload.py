#!/usr/bin/env python3
"""Manually reset database and upload one PDF with error logging."""
import requests
import json
from pathlib import Path

BASE_URL = "https://aln-chatbot-rag.onrender.com/api"

print("🔧 MANUAL RESET & UPLOAD WITH ERROR LOGGING\n")

# Step 1: Delete all documents
print("Step 1: Deleting all documents from database...")
try:
    # First, get all documents
    r = requests.get(f"{BASE_URL}/chat/documents", timeout=10)
    if r.status_code == 200:
        docs = r.json()  # Returns a list directly
        print(f"   Found {len(docs)} documents")
        
        for doc in docs:
            doc_id = doc["id"]
            r = requests.delete(f"{BASE_URL}/chat/documents/{doc_id}?role=admin", timeout=10)
            print(f"   Deleted document {doc_id}: {r.status_code}")
    else:
        print(f"   Could not list documents: {r.status_code}")
except Exception as e:
    print(f"   Error: {e}")

print("\nStep 2: Verify cleanup...")
try:
    r = requests.get(f"{BASE_URL}/chat/documents", timeout=10)
    if r.status_code == 200:
        docs = r.json()  # Returns a list directly
        print(f"   ✅ Documents remaining: {len(docs)}")
        for doc in docs:
            print(f"      - ID {doc['id']}: {doc['title']}")
    else:
        print(f"   Error checking documents: {r.status_code}")
except Exception as e:
    print(f"   Error: {e}")

# Step 3: Upload one PDF
print("\nStep 3: Uploading Assessment Brief PDF...")
pdf_path = Path("Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf")

if not pdf_path.exists():
    print(f"   ❌ File not found: {pdf_path}")
    exit(1)

print(f"   📄 File: {pdf_path.name}")
print(f"   📊 Size: {pdf_path.stat().st_size:,} bytes")

try:
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        data = {
            "title": "Assessment Brief CMP6230",
            "document_type": "general",
            "year": "2024",
            "chunk_strategy": "sentence"  # Required: 'sliding' or 'sentence'
        }
        
        print(f"   🚀 Uploading (timeout=120s)...")
        r = requests.post(
            f"{BASE_URL}/ingest/upload",
            files=files,
            data=data,
            timeout=120
        )
        
        print(f"   Response status: {r.status_code}")
        
        if r.status_code == 200:
            result = r.json()
            print(f"   ✅ Upload successful!")
            print(f"      - Document ID: {result.get('document_id')}")
            print(f"      - Chunks: {result.get('chunk_count')}")
            print(f"      - Vectors: {result.get('embeddings_generated')}")
            print(f"      - Pinecone: {result.get('pinecone_status')}")
        else:
            print(f"   ❌ Upload failed!")
            print(f"      Response: {r.text[:500]}")
            
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Step 4: Test queries
print("\nStep 4: Testing document mode queries...")
test_queries = [
    "What is this document about?",
    "What is academic misconduct?",
]

for query in test_queries:
    print(f"\n   📝 Query: '{query}'")
    try:
        r = requests.post(
            f"{BASE_URL}/chat/query",
            json={
                "query": query,
                "mode": "documents",
                "session_id": "test_session"
            },
            timeout=30
        )
        
        if r.status_code == 200:
            result = r.json()
            response = result.get("response", "No response")
            print(f"   ✅ Response: {response[:200]}...")
        else:
            print(f"   ❌ Error: {r.status_code}")
            print(f"      {r.text[:200]}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")

print("\n✅ Manual reset complete!")
