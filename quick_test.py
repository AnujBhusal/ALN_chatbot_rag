#!/usr/bin/env python3
import json
import urllib.request
import urllib.error

url = "https://aln-chatbot-rag.onrender.com/api/chat/query"
payload = {
    "session_id": "test-123",
    "query": "Who were nominees in 2018?",
    "mode": "general",
    "role": "staff"
}

try:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read())
        print("✅ Response received")
        answer = data.get("answer", "")
        print(f"Answer length: {len(answer)} chars")
        
        if "Not available" in answer:
            print("❌ FAILED: Still showing 'Not available'")
        else:
            print("✅ SUCCESS: Got data!")
            print(f"Preview: {answer[:300]}...")
        
        print(f"Sources: {len(data.get('sources', []))} found")
except Exception as e:
    print(f"❌ Error: {e}")
