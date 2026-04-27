#!/usr/bin/env python3
"""Call the cleanup endpoint on the backend."""

import requests
import time

BACKEND_URL = "https://aln-chatbot-rag.onrender.com/api/ingest/cleanup-duplicates"

print("⏳ Waiting 20 seconds for Render to complete deployment...")
time.sleep(20)

print("\n🧹 Calling cleanup endpoint...\n")

try:
    response = requests.delete(BACKEND_URL, timeout=30)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Cleanup successful!")
        print(f"   - Deleted documents: {result.get('total_deleted')}")
        print(f"   - IDs deleted: {result.get('deleted_documents')}")
        print(f"   - Chunks deleted: {result.get('total_chunks_deleted')}")
    else:
        print(f"❌ Failed: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"❌ Error: {e}")
