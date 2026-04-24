#!/usr/bin/env python3
"""Check what documents are ingested in the backend."""

import requests

BACKEND_URL = "https://aln-chatbot-rag.onrender.com/api/chat/documents"

try:
    response = requests.get(f"{BACKEND_URL}?role=staff", timeout=10)
    
    if response.status_code == 200:
        documents = response.json()
        print(f"\n✅ Documents ingested: {len(documents)}")
        for doc in documents:
            print(f"   - ID: {doc.get('id')}, Title: {doc.get('title')}, Type: {doc.get('type')}")
    else:
        print(f"❌ Failed to fetch documents: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"❌ Error: {e}")
