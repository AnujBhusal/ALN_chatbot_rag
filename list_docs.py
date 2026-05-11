#!/usr/bin/env python3
import json
import urllib.request

url = "https://aln-chatbot-rag.onrender.com/api/ingest/documents"

try:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read())
        print("📚 Documents in database:")
        print(json.dumps(data, indent=2)[:500])
except Exception as e:
    print(f"❌ Error: {e}")
