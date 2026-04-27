#!/usr/bin/env python3
"""
Remote cleanup script - calls backend API to remove duplicates
"""

import requests

BACKEND_URL = "https://aln-chatbot-rag.onrender.com"

# First, let's test with a simple approach - call the document list and inspect
print("🔍 Fetching documents to identify duplicates...\n")

try:
    response = requests.get(f"{BACKEND_URL}/api/chat/documents?role=staff", timeout=10)
    
    if response.status_code == 200:
        documents = response.json()
        print(f"✅ Found {len(documents)} total documents\n")
        
        # Group by title
        by_title = {}
        for doc in documents:
            title = doc.get('title', 'Unknown')
            if title not in by_title:
                by_title[title] = []
            by_title[title].append(doc)
        
        # Find duplicates
        duplicates = {k: v for k, v in by_title.items() if len(v) > 1}
        
        if duplicates:
            print(f"⚠️  Found {len(duplicates)} duplicate titles:\n")
            for title, docs in duplicates.items():
                print(f"📄 '{title}' appears {len(docs)} times:")
                for doc in sorted(docs, key=lambda d: d.get('id', 0)):
                    print(f"   - ID: {doc.get('id')}, Type: {doc.get('type')}, Year: {doc.get('year')}")
                print()
        else:
            print("✅ No duplicates found!")
    else:
        print(f"❌ Failed: {response.status_code}")
        
except Exception as e:
    print(f"❌ Error: {e}")
